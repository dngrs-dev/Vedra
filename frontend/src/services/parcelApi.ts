import { z } from 'zod';
import { pl } from '@/constants/pl';
import type { LatLng, Parcel } from '@/types/parcel';
import { pointInRing, polygonAreaHa, ringCenter, shareInsideRect } from '@/utils/geo';
import { isParcelId } from '@/utils/validation';
import { ApiError, request } from './http';

/**
 * Поиск участков через публичный ULDK GUGiK (бесплатно, без ключа).
 * Документация: https://uldk.gugik.gov.pl/opis.html
 * Ответ: первая строка - статус ("0" = OK), далее "id|SRID=4326;POLYGON((lon lat,...))".
 */
const ULDK = import.meta.env.VITE_ULDK_URL ?? 'https://uldk.gugik.gov.pl/';
const STANDALONE_DEMO = import.meta.env.VITE_USE_MOCK === 'true';
const recentParcels = new Map<string, Parcel>();

// RFC 7946 GeoJSON rings use longitude, latitude and at least four positions.
const position = z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)]);
const polygon = z.array(z.array(position).min(4)).min(1);
const backendParcel = z.object({
  parcel_id: z.string().refine(isParcelId),
  area_ha: z.number().nonnegative(),
  centroid_lat: z.number().min(-90).max(90),
  centroid_lon: z.number().min(-180).max(180),
  geometry_wgs84: z.discriminatedUnion('type', [
    z.object({ type: z.literal('Polygon'), coordinates: polygon }),
    z.object({ type: z.literal('MultiPolygon'), coordinates: z.array(polygon).min(1) })
  ])
});

export class ParcelNotFoundError extends Error {
  constructor() {
    super('Parcel not found');
    this.name = 'ParcelNotFoundError';
  }
}

function parse(text: string): Parcel {
  const lines = text.trim().split(/\r?\n/);
  if (lines[0]?.trim().startsWith('-1')) throw new ParcelNotFoundError();
  if (lines[0]?.trim() !== '0' || !lines[1]) throw new Error(pl.search.unavailable);
  const [id, geom] = lines[1].split('|');
  const m = geom?.match(/POLYGON\(\((.+?)\)\)/);
  if (!id || !isParcelId(id) || !m?.[1]) throw new Error(pl.search.unavailable);

  const ring: LatLng[] = m[1].split(',').map((pair) => {
    const parsed = position.safeParse(pair.trim().split(/\s+/).map(Number));
    if (!parsed.success) throw new Error(pl.search.unavailable);
    const [lon, lat] = parsed.data;
    return [lat, lon];
  });
  return {
    id: id.trim(),
    ring,
    areaHa: +polygonAreaHa(ring).toFixed(2),
    center: ringCenter(ring)
  };
}

async function callUldk(query: string, signal?: AbortSignal): Promise<Parcel> {
  const res = await fetch(`${ULDK}?${query}&result=id,geom_wkt&srid=4326`, { signal });
  if (!res.ok) throw new Error(pl.search.unavailable);
  return parse(await res.text());
}

function fromBackend(raw: unknown): Parcel {
  const parsed = backendParcel.safeParse(raw);
  if (!parsed.success) throw new Error(pl.search.unavailable);
  const { parcel_id, area_ha, centroid_lat, centroid_lon, geometry_wgs84 } = parsed.data;
  const polygons = geometry_wgs84.type === 'Polygon' ? [geometry_wgs84.coordinates] : geometry_wgs84.coordinates;
  const outline = polygons.map((rings) => rings.map((ring) => ring.map(([lon, lat]): LatLng => [lat, lon])));
  const [first, ...others] = outline.map((rings) => rings[0]!);
  if (!first) throw new Error(pl.search.unavailable);
  const ring = others.reduce((largest, candidate) =>
    polygonAreaHa(candidate) > polygonAreaHa(largest) ? candidate : largest, first);
  return { id: parcel_id, ring, outline, areaHa: area_ha, center: { lat: centroid_lat, lng: centroid_lon } };
}

function remember(parcel: Parcel): Parcel {
  const key = parcel.id.toLowerCase();
  recentParcels.delete(key);
  recentParcels.set(key, parcel);
  // Limit the session cache to the size of the existing smart-selection limit.
  if (recentParcels.size > AREA_LIMITS.maxParcels) {
    const oldest = recentParcels.keys().next().value;
    if (oldest !== undefined) recentParcels.delete(oldest);
  }
  return parcel;
}

async function lookup(
  path: string, directQuery: string, select: (raw: unknown) => Parcel, signal?: AbortSignal
): Promise<Parcel> {
  try {
    return remember(select(await request<unknown>(path, { signal })));
  } catch (error) {
    if (signal?.aborted) throw error;
    if (STANDALONE_DEMO) return remember(await callUldk(directQuery, signal));
    if (error instanceof ApiError && error.status === 404) throw new ParcelNotFoundError();
    throw error;
  }
}

export async function getParcelById(id: string, signal?: AbortSignal): Promise<Parcel> {
  signal?.throwIfAborted();
  const key = id.toLowerCase();
  const cached = recentParcels.get(key);
  if (cached) return remember(cached);
  const encoded = encodeURIComponent(id);
  return lookup(`/parcels/search?q=${encoded}`, `request=GetParcelById&id=${encoded}`, (raw) => {
    if (!Array.isArray(raw)) throw new Error(pl.search.unavailable);
    const exact = raw.find((item) => typeof item?.parcel_id === 'string' && item.parcel_id.toLowerCase() === key);
    if (!exact) throw new ParcelNotFoundError();
    return fromBackend(exact);
  }, signal);
}

const pointQuery = (lat: number, lng: number) => `request=GetParcelByXY&xy=${lng},${lat},4326`;

export async function getParcelByLatLng(lat: number, lng: number, signal?: AbortSignal): Promise<Parcel> {
  signal?.throwIfAborted();
  for (const parcel of recentParcels.values()) {
    const polygons = parcel.outline ?? [[parcel.ring]];
    if (polygons.some(([outer, ...holes]) =>
      outer && pointInRing(lat, lng, outer) && !holes.some((ring) => pointInRing(lat, lng, ring))
    )) return remember(parcel);
  }
  const params = new URLSearchParams({ lat: String(lat), lon: String(lng) });
  return lookup(`/parcels/by-point?${params}`, pointQuery(lat, lng), fromBackend, signal);
}

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
 * Точка, которая уже лежит внутри найденной делянки, повторно не запрашивается -
 * поэтому запросов к ULDK примерно столько, сколько делянок (+ дороги/вода).
 * Делянки уже шага сетки (узкие полоски) могут быть пропущены - это ограничение метода.
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

  // точки - центры ячеек; обходим от центра к краям, чтобы сначала находились «главные» делянки
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
        // Smart selection samples many points. Keep those requests separate from the single-parcel backend lookup.
        const p = await callUldk(pointQuery(la, lo), signal);
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

/* ---------- границы для слоя на карте (GET /parcels/in-bbox, /parcels/obreby-in-bbox) ---------- */

const boundaryFeature = z.object({
  type: z.literal('Feature'),
  id: z.string(),
  properties: z.object({
    id: z.string(),
    /** делянка: номер и площадь (из EPSG:2180 до упрощения) */
    number: z.string().optional(),
    area_ha: z.number().nonnegative().optional(),
    /** obręb: название */
    name: z.string().optional()
  }),
  geometry: z.discriminatedUnion('type', [
    z.object({ type: z.literal('Polygon'), coordinates: polygon }),
    z.object({ type: z.literal('MultiPolygon'), coordinates: z.array(polygon).min(1) })
  ])
});
const boundaryCollection = z.object({
  features: z.array(z.unknown()),
  truncated: z.boolean().optional()
});

export type BoundaryFeature = z.infer<typeof boundaryFeature>;

export interface BoundaryBox {
  minLat: number;
  minLng: number;
  maxLat: number;
  maxLng: number;
}

/** Контуры в рамке (сетка ячеек на бэкенде). Битые записи пропускаются, а не роняют весь слой. */
export async function getBoundaries(path: string, box: BoundaryBox, signal?: AbortSignal): Promise<BoundaryFeature[]> {
  const params = new URLSearchParams({
    min_lat: box.minLat.toFixed(6),
    min_lon: box.minLng.toFixed(6),
    max_lat: box.maxLat.toFixed(6),
    max_lon: box.maxLng.toFixed(6)
  });
  const raw = boundaryCollection.parse(await request<unknown>(`${path}?${params}`, { signal }));
  return raw.features.flatMap((f) => {
    const parsed = boundaryFeature.safeParse(f);
    return parsed.success ? [parsed.data] : [];
  });
}

/**
 * Делянка из уже загруженного контура слоя границ - выбор без запроса к серверу.
 * Анализу нужен только ID (бэкенд сам находит делянку по нему), площадь и контур - для отображения.
 */
export function parcelFromBoundary(f: BoundaryFeature): Parcel | null {
  if (!isParcelId(f.id) || f.properties.area_ha === undefined) return null;
  const polygons = f.geometry.type === 'Polygon' ? [f.geometry.coordinates] : f.geometry.coordinates;
  const outline = polygons.map((rings) => rings.map((ring) => ring.map(([lon, lat]): LatLng => [lat, lon])));
  const [first, ...others] = outline.map((rings) => rings[0]!);
  if (!first) return null;
  const ring = others.reduce((largest, candidate) =>
    polygonAreaHa(candidate) > polygonAreaHa(largest) ? candidate : largest, first);
  return remember({ id: f.id, ring, outline, areaHa: f.properties.area_ha, center: ringCenter(ring) });
}
