import type { LatLng, Parcel } from '@/types/parcel';
import { polygonAreaHa, ringCenter } from '@/utils/geo';

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
