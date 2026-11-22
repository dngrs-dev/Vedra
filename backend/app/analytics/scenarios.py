""""What if" scenarios: how farmer actions change the root-zone water balance and drought stress.

The model is the FAO-56 daily root-zone bucket already used for irrigation advice
(water_balance.py), run over the growing season with four optional levers:

* landscape retention - part of the rain surplus that would drain away is held back on or
  next to the field and slowly returned to the root zone;
* soil retention - more soil organic matter raises available water (Saxton & Rawls, 2006);
* cover crops / residues / mulch - lower soil evaporation (FAO-56: about 5% less
  evaporation for each 10% of the surface covered by organic mulch);
* irrigation - a net dose whenever depletion reaches the readily available water (RAW),
  within a seasonal water limit.

The lever coefficients are explicit, documented assumptions for comparing actions,
not field-calibrated values. Every result is shown next to the "do nothing" baseline.
"""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import date, timedelta

from app.analytics import periods, season
from app.analytics.crops import Crop
from app.analytics.evapotranspiration import etp_period
from app.analytics.models import WeatherData
from app.analytics.soil_water import profile_taw, root_profile, what_if_som
from app.analytics.water_balance import CM_PER_METRE, _initial, _ks, _raw
from app.contracts.common import Range
from app.contracts.geo import SoilInfo, SoilLayer
from app.contracts.scenario import (
    RiskLevel, ScenarioLevers, ScenarioOutcome, ScenarioPoint, ScenarioResult, WaterBudget,
)

# --- Lever assumptions (documented in ASSUMPTIONS_PL) ---
# Share of the rain surplus above field capacity that retention structures can catch.
RETENTION_CAPTURE = 0.6
# Maximum daily return of held-back water to the root zone (mm/day): infiltration from
# ponds, ditches with weirs and a raised shallow water table.
RETENTION_RELEASE_MM_DAY = 1.5
# FAO-56 (ch. 11, mulches): soil evaporation falls by ~5% for each 10% of covered surface.
MULCH_EVAPORATION_CUT_PER_COVER = 0.5
# Assumed seasonal share of soil evaporation in crop evapotranspiration (single Kc).
EVAPORATION_SHARE = 0.25

# --- Risk classes from the relative ET deficit and the share of stress days ---
HIGH_DEFICIT_PCT, MEDIUM_DEFICIT_PCT = 15.0, 5.0
HIGH_STRESS_SHARE, MEDIUM_STRESS_SHARE = 0.40, 0.15

ASSUMPTIONS_PL = [
    "Model: dobowy bilans wody w strefie korzeniowej wg FAO-56 (ten sam co przy ocenie nawadniania), "
    "liczony od początku sezonu wegetacyjnego (21 marca).",
    f"Retencja krajobrazowa: zatrzymuje do {round(RETENTION_CAPTURE * 100)}% nadwyżki opadu, która inaczej "
    f"odpłynęłaby poza strefę korzeni, i oddaje ją roślinom w tempie do {RETENTION_RELEASE_MM_DAY:g} mm na dobę.",
    "Próchnica: zmiana wody dostępnej dla roślin liczona z uziarnienia gleby wzorami Saxtona i Rawlsa (2006).",
    f"Międzyplony, resztki i mulcz: ok. 5% mniej parowania z gleby na każde 10% okrytej powierzchni (FAO-56); "
    f"przyjęto, że parowanie z gleby to ok. {round(EVAPORATION_SHARE * 100)}% ewapotranspiracji uprawy.",
    "Nawadnianie: dawka netto, gdy zapas wody spadnie do progu łatwo dostępnej wody (RAW), aż do wyczerpania "
    "sezonowego limitu wody.",
    "To porównanie działań, a nie prognoza plonu. Współczynniki są założeniami modelowymi, "
    "a nie pomiarami z tej działki.",
]
KBW_NOTE_PL = (
    "Ustawowy klimatyczny bilans wodny (KBW = opad - ewapotranspiracja potencjalna) zależy tylko od pogody, "
    "więc działania na polu go nie zmieniają. Scenariusze pokazują, ile wody zostaje w glebie dla rośliny "
    "i jak często roślina cierpi z powodu suszy."
)

PRESETS: tuple[tuple[str, str, str, ScenarioLevers], ...] = (
    ("retention", "Retencja krajobrazowa",
     "Zastawki na rowach, oczka wodne, zatrzymanie spływu - ok. 25 mm wody zatrzymanej na polu.",
     ScenarioLevers(retention_mm=25)),
    ("organic_matter", "Więcej próchnicy",
     "Obornik, resztki, uproszczona uprawa - wzrost materii organicznej o 1 punkt procentowy (efekt wieloletni).",
     ScenarioLevers(organic_matter_pct=1)),
    ("cover", "Międzyplony i mulcz",
     "Pozostawienie resztek lub mulczu z międzyplonu na 60% powierzchni gleby.",
     ScenarioLevers(cover_pct=60)),
    ("irrigation", "Nawadnianie",
     "Dawki po 25 mm, gdy zapas wody spadnie do progu stresu, maksymalnie 100 mm w sezonie.",
     ScenarioLevers(irrigation_limit_mm=100, irrigation_dose_mm=25)),
    ("combined", "Wszystkie działania razem",
     "Retencja, próchnica, mulcz i nawadnianie jednocześnie.",
     ScenarioLevers(retention_mm=25, organic_matter_pct=1, cover_pct=60, irrigation_limit_mm=100,
                    irrigation_dose_mm=25)),
)


# Typical soil used only when the parcel has a KBW soil category but no layer data.
# Available water per 100 cm sits inside the category's WOD range from Dz.U. 2019 poz. 739
# (config/soil_categories.yaml); the texture (for the organic-matter lever) matches its soil types.
TYPICAL_SOIL = {
    # category: (WOD mm per 100 cm, wilting point m3/m3, sand %, clay %)
    "I": (110.0, 0.05, 88, 4),     # piasek luźny / słabo gliniasty
    "II": (150.0, 0.08, 72, 10),   # piasek gliniasty
    "III": (186.0, 0.12, 45, 18),  # glina lekka, pył
    "IV": (225.0, 0.18, 30, 30),   # glina średnia / ciężka, ił
}
TYPICAL_SOC_G_KG = 10.0  # about 1.7% organic matter, common in Polish arable topsoil


def typical_layers(category: str) -> list[SoilLayer]:
    wod, wp, sand, clay = TYPICAL_SOIL[category]
    return [SoilLayer(top_cm=0, bottom_cm=200, sand_pct=Range(mid=sand), clay_pct=Range(mid=clay),
                      soc_g_kg=Range(mid=TYPICAL_SOC_G_KG), theta_wp=Range(mid=wp),
                      theta_fc=Range(mid=wp + wod / 1000))]


@dataclass(frozen=True, slots=True)
class Window:
    start: date
    end: date
    note_pl: str


def window(analysis_date: date) -> Window:
    """The growing-season window that ends at the analysis date (or the last complete season)."""
    year = analysis_date.year
    season_start = periods.for_year(year)[0].start
    season_end = periods.for_year(year)[-1].end
    if season.mode(analysis_date) == "in_season":
        return Window(season_start, analysis_date, "Od początku sezonu do daty analizy.")
    if analysis_date > season_end:
        return Window(season_start, season_end, f"Cały sezon wegetacyjny {year} (data analizy jest po sezonie).")
    previous = periods.for_year(year - 1)
    return Window(previous[0].start, previous[-1].end,
                  f"Poprzedni pełny sezon wegetacyjny {year - 1} (data analizy jest przed sezonem).")


@dataclass(frozen=True, slots=True)
class Field:
    """Crop and soil inputs shared by all scenarios."""

    taw_mm: float
    kc: float
    p: float
    initial_depletion_mm: float
    initial_from_data: bool
    layers: list
    zr_cm: float
    typical_soil: bool = False


def prepare(weather: WeatherData | None, crop: Crop, soil: SoilInfo | None, start: date) -> Field | None:
    if weather is None or soil is None:
        return None
    kc = crop.kc.mid
    low_kc, high_kc = kc if isinstance(kc, tuple) else (kc, kc)
    zr_cm = (crop.zr_m.low + crop.zr_m.high) / 2 * CM_PER_METRE
    layers, typical = soil.layers, False
    profile = root_profile(layers, zr_cm) if layers else None
    if profile is None and soil.kbw_category in TYPICAL_SOIL:
        layers, typical = typical_layers(soil.kbw_category), True
        profile = root_profile(layers, zr_cm)
    if profile is None:
        return None
    taw = profile_taw(profile).mid
    row = weather.days.get(start)
    initial = _initial(profile, row) if row is not None else None
    # Without modelled soil moisture, start the season at field capacity (FAO-56 assumption after winter).
    return Field(taw, (low_kc + high_kc) / 2, crop.p.value, initial or 0.0, initial is not None, layers, zr_cm,
                 typical)


def with_et0(weather: WeatherData, start: date, end: date) -> tuple[WeatherData, bool]:
    """Fill missing daily ET0 from the monthly Doroszewski-Górski ETP used for KBW.

    Station archives (IMGW) have temperature and sunshine but no ET0. The monthly ETP is spread
    evenly over the month's days, which is enough for a seasonal comparison of actions.
    """
    days = dict(weather.days)
    filled = False
    month = start.replace(day=1)
    while month <= end:
        last = month.replace(day=monthrange(month.year, month.month)[1])
        missing = [d for d in (month + timedelta(days=i) for i in range((last - month).days + 1))
                   if start <= d <= end and d in days and days[d].et0_mm is None]
        if missing:
            observed_end = min(last, end)
            total = etp_period(weather, month, observed_end)
            if total is not None:
                daily = max(0.0, total / ((observed_end - month).days + 1))
                for d in missing:
                    days[d] = replace(days[d], et0_mm=daily)
                filled = True
        month = last + timedelta(days=1)
    return (WeatherData(weather.latitude, weather.longitude, days), filled) if filled else (weather, False)


def _risk(deficit_pct: float, stress_share: float) -> RiskLevel:
    if deficit_pct >= HIGH_DEFICIT_PCT or stress_share >= HIGH_STRESS_SHARE:
        return "high"
    if deficit_pct >= MEDIUM_DEFICIT_PCT or stress_share >= MEDIUM_STRESS_SHARE:
        return "medium"
    return "low"


def simulate(weather: WeatherData, field: Field, levers: ScenarioLevers, start: date, end: date
             ) -> tuple[float, ScenarioOutcome, list[ScenarioPoint]] | None:
    som = what_if_som(field.layers, levers.organic_matter_pct, field.zr_cm) if levers.organic_matter_pct else None
    taw = field.taw_mm + (som.mid if som is not None else 0.0)
    et_factor = 1 - EVAPORATION_SHARE * MULCH_EVAPORATION_CUT_PER_COVER * levers.cover_pct / 100

    depletion = min(field.initial_depletion_mm, taw)
    start_depletion = depletion
    stored = 0.0  # water held back by landscape retention, mm over the field
    irrigation_left = levers.irrigation_limit_mm
    totals = dict(rain=0.0, irrigation=0.0, release=0.0, eta=0.0, etc=0.0, losses=0.0, retained=0.0)
    stress_days = events = days = 0
    min_available = 100.0
    series: list[ScenarioPoint] = []

    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        row = weather.days.get(day)
        if row is None or row.precipitation_mm is None or row.et0_mm is None:
            continue
        days += 1
        kc = field.kc * et_factor
        raw = _raw(taw, field.p, kc, row.et0_mm)

        if irrigation_left > 0 and depletion >= raw:
            dose = min(levers.irrigation_dose_mm, irrigation_left, depletion)
            depletion -= dose
            irrigation_left -= dose
            totals["irrigation"] += dose
            events += 1
        if stored > 0 and depletion > 0:
            release = min(stored, RETENTION_RELEASE_MM_DAY, depletion)
            stored -= release
            depletion -= release
            totals["release"] += release

        ks = _ks(depletion, raw, taw)
        eta = ks * kc * row.et0_mm
        # FAO-56 equation (85): rain refills the store, ETa empties it.
        depletion = depletion - row.precipitation_mm + eta
        if depletion < 0:
            surplus = -depletion
            caught = min(surplus * RETENTION_CAPTURE, max(0.0, levers.retention_mm - stored)) if levers.retention_mm else 0.0
            stored += caught
            totals["retained"] += caught
            totals["losses"] += surplus - caught
            depletion = 0.0
        if depletion > taw:
            eta -= depletion - taw
            depletion = taw

        totals["rain"] += row.precipitation_mm
        totals["eta"] += eta
        totals["etc"] += field.kc * row.et0_mm
        stress_days += ks < 1
        available = 100 * (1 - depletion / taw)
        min_available = min(min_available, available)
        series.append(ScenarioPoint(day=day, available_pct=round(available, 1)))

    if not days:
        return None
    deficit_pct = 100 * max(0.0, totals["etc"] * et_factor - totals["eta"]) / totals["etc"] if totals["etc"] else 0.0
    budget = WaterBudget(
        precipitation_mm=round(totals["rain"], 1),
        irrigation_mm=round(totals["irrigation"], 1),
        retention_release_mm=round(totals["release"], 1),
        actual_et_mm=round(totals["eta"], 1),
        potential_et_mm=round(totals["etc"], 1),
        losses_mm=round(totals["losses"], 1),
        retained_mm=round(totals["retained"], 1),
        storage_change_mm=round(start_depletion - depletion, 1),
    )
    outcome = ScenarioOutcome(
        stress_days=stress_days,
        days=days,
        et_deficit_pct=round(deficit_pct, 1),
        min_available_pct=round(min_available, 1),
        end_available_pct=series[-1].available_pct,
        irrigation_events=events,
        risk=_risk(deficit_pct, stress_days / days),
        budget=budget,
    )
    return taw, outcome, series


def result(id_: str, title: str, description: str, weather: WeatherData, field: Field,
           levers: ScenarioLevers, start: date, end: date, with_series: bool = True) -> ScenarioResult | None:
    simulated = simulate(weather, field, levers, start, end)
    if simulated is None:
        return None
    taw, outcome, series = simulated
    return ScenarioResult(id=id_, title_pl=title, description_pl=description, levers=levers,
                          taw_mm=round(taw, 1), outcome=outcome, series=series if with_series else [])


def organic_matter_supported(field: Field) -> bool:
    return what_if_som(field.layers, 1, field.zr_cm) is not None
