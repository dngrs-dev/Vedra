/**
 * Зум, с которого можно кликом выбрать делянку (без слоя границ — запросом по точке).
 * На 15 при широте ~52° 1 px ≈ 3 м: типичная делянка 20–100 м занимает 7–30 px — попасть в неё можно осознанно.
 */
export const PICK_MIN_ZOOM = 15;
/** Слой границ, уровень 1: контуры obrębów ewidencyjnych (группы делянок) — зум 15–16 */
export const OBREB_MIN_ZOOM = 15;
/** Слой границ, уровень 2: контуры отдельных делянок — с зума 17 (1–4 ячейки на экран вместо 12–48 на зуме 15) */
export const PARCEL_BOUNDARY_MIN_ZOOM = 17;

export type BoundaryKind = 'obreby' | 'parcels';

/** Сетки ячеек, которыми грузятся границы (те же, что в backend/app/api/parcel_grid.py). */
export const GRIDS: Record<BoundaryKind, { lat: number; lon: number; path: string }> = {
  parcels: { lat: 0.01, lon: 0.015, path: '/parcels/in-bbox' },
  obreby: { lat: 0.04, lon: 0.06, path: '/parcels/obreby-in-bbox' }
};

/** Цвет границ: мягкий янтарный — виден и на тёмном спутнике, и на светлой карте рельефа. */
export const BOUNDARY_COLOR = '#ffb547';
export const PARCEL_FILL = '#4fa183';

/** Толщина линии по зуму: на крупном зуме чуть шире, на мелком — тоньше, чтобы не «забивать» карту. */
export function boundaryWeight(zoom: number, kind: BoundaryKind = 'parcels'): number {
  const z = Math.round(zoom);
  if (kind === 'obreby') return z >= 16 ? 1.5 : 1.2;
  const table: Record<number, number> = { 17: 0.9, 18: 1.4, 19: 1.9 };
  return table[Math.min(19, Math.max(17, z))] ?? 1;
}

/** Leaflet-панели: границы над масками/воеводствами (overlayPane = 400), выбранная делянка — над границами. */
export const PANE_BOUNDARIES = 'parcel-boundaries';
export const PANE_SELECTED = 'parcel-selected';
export const PANE_USER_LOCATION = 'user-location';

/** Ключ localStorage для переключателя «Granice działek» */
export const BOUNDARIES_STORAGE_KEY = 'vedra.boundaries';
