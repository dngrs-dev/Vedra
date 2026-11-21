import type { LatLng } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { boundsOfRings, ringCentroid } from '@/utils/geo';

/**
 * Границы województw (GeoJSON, WGS84). Порядок загрузки:
 *  1) локальный файл public/data/wojewodztwa.geojson (если положили — работает офлайн и быстрее),
 *  2) CDN jsDelivr с репозитория ppatrzyk/polska-geojson (лицензия MIT).
 */
const LOCAL_URL = '/data/wojewodztwa.geojson';
const CDN_URL = 'https://cdn.jsdelivr.net/gh/ppatrzyk/polska-geojson@master/wojewodztwa/wojewodztwa-medium.geojson';

interface GeoFeature {
  properties?: Record<string, unknown> | null;
  geometry?: { type: string; coordinates: unknown } | null;
}

const NAME_KEYS = ['nazwa', 'name', 'NAME', 'NAZWA', 'JPT_NAZWA_', 'woj', 'wojewodztwo', 'NAME_1'];

function nameOf(props: Record<string, unknown> | null | undefined, index: number): string {
  const p = props ?? {};
  let raw = NAME_KEYS.map((k) => p[k]).find((v): v is string => typeof v === 'string' && v.length > 0);
  if (!raw) raw = Object.values(p).find((v): v is string => typeof v === 'string' && v.length > 2 && v.length < 40);
  if (!raw) return `Województwo ${index + 1}`;
  const clean = raw.replace(/^województwo\s+/i, '').trim();
  return clean.charAt(0).toUpperCase() + clean.slice(1).toLowerCase();
}

/** GeoJSON [lng, lat] → [lat, lng] */
const toRing = (coords: unknown): LatLng[] =>
  (coords as number[][]).map((c) => [c[1] ?? 0, c[0] ?? 0] as LatLng);

function parsePolygons(g: NonNullable<GeoFeature['geometry']>): LatLng[][][] {
  if (g.type === 'Polygon') return [(g.coordinates as unknown[]).map(toRing)];
  if (g.type === 'MultiPolygon') return (g.coordinates as unknown[][]).map((poly) => poly.map(toRing));
  return [];
}

export function parseVoivodeships(json: unknown): Voivodeship[] {
  const features = (json as { features?: GeoFeature[] }).features;
  if (!Array.isArray(features) || features.length === 0) throw new Error('Nieprawidłowy plik GeoJSON');

  return features.flatMap((f, i) => {
    if (!f.geometry) return [];
    const polygons = parsePolygons(f.geometry);
    if (!polygons.length) return [];
    const outers = polygons.map((p) => p[0]!).filter(Boolean);
    const largest = outers.reduce((a, b) => (b.length > a.length ? b : a), outers[0]!);
    const name = nameOf(f.properties, i);
    return [{ id: name.toLowerCase(), name, polygons, bounds: boundsOfRings(outers), labelPoint: ringCentroid(largest) }];
  });
}

async function tryFetch(url: string): Promise<unknown> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json(); // если dev-сервер вернул index.html — здесь бросит и мы пойдём на CDN
}

export async function loadVoivodeships(): Promise<Voivodeship[]> {
  for (const url of [LOCAL_URL, CDN_URL]) {
    try {
      return parseVoivodeships(await tryFetch(url));
    } catch {
      /* следующий источник */
    }
  }
  throw new Error('Nie udało się pobrać granic województw');
}
