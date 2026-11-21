import type {
  Analysis,
  AnalysisRequest,
  Confidence,
  DataSource,
  Recommendation,
  WaterState
} from '@/types/analysis';
import { CROPS } from '@/constants/crops';
import { clamp } from '@/utils/format';
import { seededRng } from '@/utils/rng';
import { sleep } from './http';

/**
 * ДЕМО-расчёт. Детерминирован: один и тот же (участок + культуры + дата) → тот же результат.
 * Нужен только пока нет бэкенда; возвращает объект формата Analysis (см. types/analysis.ts).
 * Цифры НЕ отражают реальность — на экране показывается баннер «dane demonstracyjne».
 */
export async function mockAnalyze(req: AnalysisRequest, signal?: AbortSignal): Promise<Analysis> {
  const rnd = seededRng(`${req.parcelId}|${[...req.cropIds].sort().join(',')}|${req.date}`);
  await sleep(1800 + rnd() * 900, signal); // имитация долгого расчёта (ТЗ: цель ≤ 30 s)

  const crops = CROPS.filter((c) => req.cropIds.includes(c.id));
  const need = crops.length ? crops.reduce((s, c) => s + c.waterNeed, 0) / crops.length : 0.6;
  const baseYear = Number(req.date.slice(0, 4));

  // --- история 10 лет ---
  let m = 55 + rnd() * 20;
  const history = Array.from({ length: 10 }, (_, i) => {
    m = clamp(m + (rnd() - 0.5) * 30, 28, 85);
    const risk = clamp(100 - m + need * 18 + (rnd() - 0.5) * 10, 8, 92);
    return { year: baseYear - 9 + i, moisture: Math.round(m), risk: Math.round(risk) };
  });
  const last = history[history.length - 1]!;
  const avgRisk = history.reduce((s, h) => s + h.risk, 0) / history.length;

  // --- бывает, что данных нет — показываем это честно ---
  const noMoistureData = rnd() < 0.07;
  const moisture = noMoistureData ? null : Math.round(clamp(last.moisture + (rnd() - 0.5) * 10, 20, 90));

  const level = avgRisk < 40 ? 'low' : avgRisk < 58 ? 'moderate' : 'high';
  const state: WaterState =
    moisture === null ? 'attention' : moisture >= 55 ? 'optimal' : moisture >= 40 ? 'attention' : 'critical';

  // --- факторы (то, на чём «стоит» вывод) ---
  const slope = +(0.5 + rnd() * 6).toFixed(1);
  const ditchM = Math.round(80 + rnd() * 900);
  const rain30 = Math.round(10 + rnd() * 70);
  const soilKinds = ['gleby lekkie (piaszczyste)', 'gleby średnie', 'gleby ciężkie (gliniaste)'];
  const soil = soilKinds[Math.floor(rnd() * soilKinds.length)]!;
  const ndvi = (0.3 + rnd() * 0.5).toFixed(2);
  const isLight = soil.includes('lekkie');

  const now = new Date().toISOString();
  const dayAgo = new Date(Date.now() - 86400000).toISOString();

  const sources: DataSource[] = [
    { id: 'sentinel', name: 'Sentinel-2 L2A (Copernicus)', category: 'satellite', period: `${baseYear - 10}–${baseYear}`, fetchedAt: noMoistureData ? null : now, license: 'Copernicus (open)', status: noMoistureData ? 'unavailable' : 'live' },
    { id: 'openmeteo', name: 'Open-Meteo / IMGW-PIB', category: 'weather', period: `${baseYear - 10}–${baseYear}`, fetchedAt: now, license: 'CC BY 4.0', status: 'live' },
    { id: 'iung', name: 'IUNG-PIB — Mapa podatności gleb na suszę', category: 'soil', period: 'statyczne', fetchedAt: dayAgo, license: 'IUNG-PIB', status: 'cached' },
    { id: 'nmt', name: 'Geoportal NMT (ukształtowanie terenu)', category: 'spatial', period: 'statyczne', fetchedAt: dayAgo, license: 'GUGiK (open data)', status: 'cached' },
    { id: 'hydro', name: 'Hydroportal ISOK / Wody Polskie', category: 'hydrology', period: 'statyczne', fetchedAt: dayAgo, license: 'PGW Wody Polskie', status: 'cached' }
  ];

  const confidence: Confidence = noMoistureData ? 'low' : avgRisk > 70 || avgRisk < 15 ? 'medium' : rnd() > 0.5 ? 'high' : 'medium';

  // --- рекомендации ---
  const retention: Recommendation[] = [
    {
      id: 'cover-crops',
      title: 'Międzyplony i resztki pożniwne',
      text: 'Rozważ zastosowanie międzyplonów oraz pozostawianie resztek pożniwnych w celu zwiększenia retencji glebowej.',
      priority: level === 'high' ? 'high' : 'medium',
      evidence: `Średnie ryzyko suszy z 10 lat: ${Math.round(avgRisk)}%; ${soil}.`
    }
  ];
  if (ditchM < 500) {
    retention.push({
      id: 'ditch-weirs',
      title: 'Spowolnienie odpływu z rowów melioracyjnych',
      text: `W odległości ok. ${ditchM} m znajduje się rów/ciek — rozważ okresowe piętrzenie wody (zastawki) po opadach.`,
      priority: 'medium',
      evidence: `Odległość do najbliższego cieku (Hydroportal): ${ditchM} m.`
    });
  }
  if (slope > 3) {
    retention.push({
      id: 'contour',
      title: 'Uprawa poprzeczna do spadku',
      text: 'Przy większym spadku terenu zalecana jest uprawa warstwicowa i pasy zatrzymujące spływ powierzchniowy.',
      priority: 'medium',
      evidence: `Średni spadek terenu (NMT): ${slope}%.`
    });
  }

  const agro: Recommendation[] = [
    {
      id: 'mulch',
      title: 'Ograniczenie strat wilgoci',
      text: isLight
        ? 'Na glebach lekkich ogranicz uprawę głęboką i utrzymuj mulcz z resztek, aby zmniejszyć parowanie.'
        : 'Stosuj uproszczoną uprawę i okrywę mulczową, aby ograniczyć parowanie z gleby.',
      priority: state === 'critical' ? 'high' : 'low',
      evidence: `NDVI ${ndvi}; opad w ostatnich 30 dniach: ${rain30} mm.`
    }
  ];

  const needsIrrigation = state !== 'optimal';
  const irrDate = needsIrrigation ? new Date(Date.now() + (state === 'critical' ? 1 : 3) * 86400000) : null;

  const [m1, m2, m3] = level === 'high' ? [5, 6, 7] : level === 'moderate' ? [6, 7, 8] : [7, 8, 8];

  return {
    parcelId: req.parcelId,
    areaHa: req.areaHa,
    region: `${req.lat.toFixed(2)}°N, ${req.lng.toFixed(2)}°E`,
    analysisDate: req.date,
    generatedAt: now,
    state,
    soilMoisturePct: moisture,
    droughtRisk: { level, avgIndexPct: Math.round(avgRisk) },
    history,
    criticalMonths: [...new Set([m1, m2, m3])],
    factors: [
      { id: 'ndvi', label: 'NDVI (kondycja roślin)', value: ndvi, source: 'Sentinel-2' },
      { id: 'rain30', label: 'Opad w ostatnich 30 dniach', value: `${rain30} mm`, source: 'Open-Meteo / IMGW' },
      { id: 'soil', label: 'Kategoria gleby', value: soil, source: 'IUNG-PIB' },
      { id: 'slope', label: 'Średni spadek terenu', value: `${slope}%`, source: 'Geoportal NMT' },
      { id: 'water', label: 'Odległość do cieku / rowu', value: `${ditchM} m`, source: 'Hydroportal' }
    ],
    recommendations: {
      retention,
      agrotechnical: agro,
      irrigation: {
        needed: needsIrrigation,
        summary: needsIrrigation
          ? 'Wilgotność gleby jest poniżej progu optymalnego dla wybranej uprawy — zaplanuj nawadnianie.'
          : 'Nawadnianie nie jest konieczne w najbliższych 7 dniach.',
        optimalDate: irrDate ? irrDate.toISOString().slice(0, 10) : null,
        amountMm: needsIrrigation ? (state === 'critical' ? 25 : 15) : null
      }
    },
    sources,
    confidence,
    limitations: [
      'Wynik ma charakter demonstracyjny — dane przykładowe, backend niepodłączony.',
      'Docelowo: rozdzielczość Sentinel-2 (10 m) może nie odzwierciedlać zróżnicowania wewnątrz małych działek.',
      'Nie uwzględniono: lokalnych zabiegów agrotechnicznych, odmiany, nawadniania wykonanego w przeszłości, wód gruntowych.',
      noMoistureData
        ? 'Brak danych satelitarnych dla wybranej daty (zachmurzenie) — wilgotność gleby nie została oszacowana.'
        : 'Zachmurzenie może opóźniać aktualność wskaźników satelitarnych o kilka dni.'
    ],
    isDemo: true
  };
}
