import type { LatLng, Parcel } from '@/types/parcel';
import { pointInRing, polygonAreaHa, ringCenter, shareInsideRect } from '@/utils/geo';

/**
 * Поиск участков через публичный ULDK GUGiK (бесплатно, без ключа).
 * Документация: https://uldk.gugik.gov.pl/opis.html
 * Ответ: первая строка — статус ("0" = OK), далее "id|SRID=4326;POLYGON((lon lat,...))".
 */
const ULDK = import.meta.env.VITE_ULDK_URL ?? 'https://uldk.gugik.gov.pl/';

export class ParcelNotFoundError extends Error {
  constructor() {
    super('Parcel not found');
    this.name = 'ParcelNotFoundError';
  }
}

function parse(text: string): Parcel {
  const lines = text.trim().split(/\r?\n/);
  if (lines[0]?.trim() !== '0' || !lines[1]) throw new ParcelNotFoundError();
  const [id, geom] = lines[1].split('|');
  const m = geom?.match(/POLYGON\(\((.+?)\)\)/);
  if (!id || !m?.[1]) throw new ParcelNotFoundError();

  const ring: LatLng[] = m[1].split(',').map((pair) => {
    const [x, y] = pair.trim().split(' ').map(Number);
    return [y ?? 0, x ?? 0] as LatLng; // srid=4326 → x = lon, y = lat
  });
  return {
    id: id.trim(),
    ring,
    areaHa: +polygonAreaHa(ring).toFixed(2),
    center: ringCenter(ring)
  };
}

async function call(query: string, signal?: AbortSignal): Promise<Parcel> {
  const res = await fetch(`${ULDK}?${query}&result=id,geom_wkt&srid=4326`, { signal });
  if (!res.ok) throw new Error(`ULDK ${res.status}`);
  return parse(await res.text());
}

export const getParcelById = (id: string, signal?: AbortSignal) =>
  call(`request=GetParcelById&id=${encodeURIComponent(id)}`, signal);

export const getParcelByLatLng = (lat: number, lng: number, signal?: AbortSignal) =>
  call(`request=GetParcelByXY&xy=${lng},${lat},4326`, signal);

export interface AreaSearchResult {
  /** Все делянки, пересекающие рамку */
  parcels: Parcel[];
  /** true, если ULDK не ответил ни на одну точку (сеть/CORS) */
  serviceDown: boolean;
  /** true, если упёрлись в лимит делянок/запросов и показали не все */
  truncated: boolean;
  /** Сколько делянок отброшено, потому что рамка задела их только краем */
  skippedEdge: number;
}

export interface AreaSearchOptions {
  signal?: AbortSignal;
  /** Вызывается по мере нахождения делянок (для индикатора «znaleziono: N») */
  onProgress?: (found: number) => void;
}

/** Лимиты, чтобы огромная рамка не «положила» ULDK */
/**
 * Делянка берётся в выбор, только если внутри рамки лежит не меньше этой доли её площади.
 * 0.5 = «большая часть делянки внутри». Поле, которое рамка задела краешком, не цепляется.
 */
export const MIN_INSIDE_SHARE = 0.5;

export const AREA_LIMITS = { maxParcels: 150, maxRequests: 300, maxPoints: 900, minStepM: 12, concurrency: 8 };

/**
 * Находит ВСЕ делянки в рамке.
 * Рамка покрывается сеткой точек (шаг подстраивается под размер, минимум ~12 м).
 * Точка, которая уже лежит внутри найденной делянки, повторно не запрашивается —
 * поэтому запросов к ULDK примерно столько, сколько делянок (+ дороги/вода).
 * Делянки уже шага сетки (узкие полоски) могут быть пропущены — это ограничение метода.
 */
export async function findParcelsInArea(ring: LatLng[], opts: AreaSearchOptions = {}): Promise<AreaSearchResult> {
  const { signal, onProgress } = opts;
  const lats = ring.map((p) => p[0]);
  const lngs = ring.map((p) => p[1]);
  const s = Math.min(...lats), n = Math.max(...lats);
  const w = Math.min(...lngs), e = Math.max(...lngs);

  // размеры рамки в метрах → шаг сетки
  const mPerDegLat = 111_320;
  const mPerDegLng = 111_320 * Math.cos((((s + n) / 2) * Math.PI) / 180);
  const hM = (n - s) * mPerDegLat;
  const wM = (e - w) * mPerDegLng;
  const step = Math.max(AREA_LIMITS.minStepM, Math.sqrt((hM * wM) / AREA_LIMITS.maxPoints));
  const rows = Math.max(1, Math.round(hM / step));
  const cols = Math.max(1, Math.round(wM / step));

  // точки — центры ячеек; обходим от центра к краям, чтобы сначала находились «главные» делянки
  const pts: [number, number][] = [];
  for (let r = 0; r < rows; r++)
    for (let c = 0; c < cols; c++) pts.push([s + ((r + 0.5) / rows) * (n - s), w + ((c + 0.5) / cols) * (e - w)]);
  const cLat = (s + n) / 2, cLng = (w + e) / 2;
  pts.sort((a, b) => Math.hypot(a[0] - cLat, (a[1] - cLng) * 0.6) - Math.hypot(b[0] - cLat, (b[1] - cLng) * 0.6));

  const found = new Map<string, Parcel>();
  const inFound = (la: number, lo: number) => {
    for (const p of found.values()) if (pointInRing(la, lo, p.ring)) return true;
    return false;
  };

  let requests = 0, answered = 0, truncated = false, cursor = 0;

  const worker = async () => {
    while (cursor < pts.length) {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');
      if (found.size >= AREA_LIMITS.maxParcels || requests >= AREA_LIMITS.maxRequests) {
        truncated = true;
        return;
      }
      const [la, lo] = pts[cursor++]!;
      if (inFound(la, lo)) continue;
      requests++;
      try {
        const p = await getParcelByLatLng(la, lo, signal);
        answered++;
        if (!found.has(p.id)) {
          found.set(p.id, p);
          onProgress?.(found.size);
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') throw err;
        if (err instanceof ParcelNotFoundError) answered++;
        // сетевые ошибки по отдельным точкам пропускаем
      }
    }
  };

  await Promise.all(Array.from({ length: AREA_LIMITS.concurrency }, worker));
  if (signal?.aborted) throw new DOMException('Aborted', 'AbortError');

  const all = [...found.values()];
  const inside = all.filter((p) => shareInsideRect(p.ring, s, w, n, e) >= MIN_INSIDE_SHARE);
  return { parcels: inside, serviceDown: answered === 0, truncated, skippedEdge: all.length - inside.length };
}
