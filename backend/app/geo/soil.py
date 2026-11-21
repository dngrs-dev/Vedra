"""SoilInfo assembly and KBW soil category (Dz.U. 2019 poz. 739; table in config/soil_categories.yaml).

Order (PART_A_DATA_GEO.md, adjusted after the CP0 spike):
  1. category from the soil-map texture code (mapa glebowo-rolnicza),
  2. category from SoilGrids WOD (0-100 cm) when the map has no code listed in the regulation.
The IUNG WMS step is skipped: no public URL found (config/geo_sources.yaml). SoilGrids layers are always
attached when available (Part B needs them for TAW).
"""
from __future__ import annotations

import asyncio
import time

from app.contracts.common import SourceResult, SourceStatus
from app.contracts.geo import SoilInfo
from app.contracts.parcel import Parcel
from app.geo import geometry, soil_map, soilgrids
from app.geo.sources import provenance, soil_categories, source


def _type_table() -> dict[str, tuple[str, str]]:
    """soil type code -> (category, Polish name), from the regulation table."""
    out: dict[str, tuple[str, str]] = {}
    for cat, entry in soil_categories()["categories"].items():
        for code, name in entry["soil_types"].items():
            out[code] = (cat, name)
    return out


def category_from_soil_type(code: str | None) -> str | None:
    if not code:
        return None
    hit = _type_table().get(code.strip().lower())
    return hit[0] if hit else None


def soil_type_name_pl(code: str | None) -> str | None:
    hit = _type_table().get((code or "").strip().lower())
    return hit[1] if hit else None


def category_from_wod(mm: float) -> str:
    t = soil_categories()["wod_thresholds_mm"]
    if mm < t["I_below"]:
        return "I"
    if mm < t["II_below"]:
        return "II"
    if mm <= t["III_up_to"]:
        return "III"
    return "IV"


async def soil_info(parcel: Parcel, budget_s: float) -> SourceResult[SoilInfo]:
    """Never raises. budget_s = time this call may take (the provider's remaining deadline)."""
    t0 = time.monotonic()
    lat, lon = geometry.query_point(parcel)
    notes: list[str] = []
    errors: list[str] = []
    prov = []
    info = SoilInfo()

    map_res, sg_res = await asyncio.gather(
        asyncio.wait_for(soil_map.dominant_soil_type(parcel), timeout=max(budget_s, 0.1)),
        soilgrids.soil_layers(lat, lon, budget_s=budget_s),
        return_exceptions=True,
    )

    # ---- soil map
    code = None
    if isinstance(map_res, BaseException):
        errors.append(f"soil_map: {type(map_res).__name__}: {map_res}")
        notes.append("Mapa glebowo-rolnicza nie odpowiedziała; nie ustalono gatunku gleby z mapy.")
    elif map_res is None:
        notes.append("Brak konturu mapy glebowo-rolniczej w obrębie działki (teren nierolniczy "
                     "lub obszar bez opracowania mapy).")
    else:
        hit, code = map_res.hit, map_res.code
        year = (hit.currency_date or "")[:4] or None
        prov.append(provenance("soil_map", source("soil_map")["url"], data_period=year))
        info.soil_type_code = code
        info.soil_type_name_pl = soil_type_name_pl(code)
        if code is None:
            notes.append(f"Mapa glebowo-rolnicza nie podaje gatunku gleby dla tej działki "
                         f"(kompleks: {hit.complex or 'brak'}).")
        elif map_res.share < 1.0:
            k = round(map_res.share * map_res.points_sampled)
            notes.append(f"Na działce występuje kilka gatunków gleb; przyjęto dominujący «{code}» "
                         f"({k} z {map_res.points_sampled} punktów kontrolnych).")
        if year:
            notes.append(f"Mapa glebowo-rolnicza dla tego obszaru: stan na rok {year}.")
        cat = category_from_soil_type(code)
        if cat:
            info.kbw_category, info.category_source = cat, "soil_map"  # type: ignore[assignment]

    # ---- SoilGrids
    if isinstance(sg_res, BaseException):
        errors.append(f"soilgrids: {type(sg_res).__name__}: {sg_res}")
        notes.append("Serwis SoilGrids nie odpowiedział; brak profilu glebowego (uziarnienie, retencja wody).")
    elif sg_res is None:
        notes.append("Profil glebowy SoilGrids nie został pobrany w wyznaczonym czasie; pobieranie trwa w tle "
                     "i dane będą dostępne przy kolejnej analizie tej działki.")
    else:
        info.layers = sg_res.layers
        info.wod_mm = soilgrids.wod_mm(sg_res.layers, info.wod_depth_cm)
        prov.append(provenance("soilgrids_rest", sg_res.url, live=sg_res.live, fetched_at=sg_res.fetched_at,
                               resolution="250 m"))
        if info.category_source == "soil_map" and info.wod_mm is not None:
            wod_cat = category_from_wod(info.wod_mm.mid)
            if wod_cat != info.kbw_category:
                notes.append(f"Niepewność: woda ogólnie dostępna z modelu SoilGrids (≈ {info.wod_mm.mid:.0f} mm, "
                             f"rozdzielczość 250 m) odpowiadałaby kategorii {wod_cat}; przyjęto kategorię "
                             f"{info.kbw_category} z mapy glebowo-rolniczej (skala 1:5000).")
        if info.kbw_category is None and info.wod_mm is not None:
            info.kbw_category = category_from_wod(info.wod_mm.mid)  # type: ignore[assignment]
            info.category_source = "soilgrids_wod"
            why = (f"gatunek «{code}» z mapy nie występuje w tabeli rozporządzenia" if code
                   else "brak gatunku gleby z mapy glebowo-rolniczej")
            notes.append(f"Kategorię gleby wyznaczono z wody ogólnie dostępnej (WOD ≈ {info.wod_mm.mid:.0f} mm "
                         f"w warstwie 0–100 cm, SoilGrids), ponieważ {why}.")

    if info.kbw_category is None and code is not None and category_from_soil_type(code) is None and sg_res is None:
        notes.append(f"Gatunek «{code}» z mapy nie występuje w tabeli kategorii gleb (Dz.U. 2019 poz. 739), "
                     "a profil SoilGrids nie jest jeszcze dostępny – kategorii gleby nie ustalono.")

    has_any = info.kbw_category is not None or info.soil_type_code is not None or bool(info.layers)
    complete = info.kbw_category is not None and bool(info.layers)
    status = SourceStatus.OK if complete else SourceStatus.PARTIAL if has_any else SourceStatus.MISSING
    return SourceResult[SoilInfo](
        status=status,
        data=info if has_any else None,
        provenance=prov,
        notes_pl=notes,
        error="; ".join(errors) or None,
        elapsed_s=round(time.monotonic() - t0, 3),
    )
