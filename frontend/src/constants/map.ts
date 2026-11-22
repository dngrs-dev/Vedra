/**
 * Зум, с которого можно кликом выбрать делянку и видны границы всех делянок.
 * На 15 при широте ~52° 1 px ≈ 3 м: типичная делянка 20–100 м занимает 7–30 px — попасть в неё можно осознанно.
 */
export const PICK_MIN_ZOOM = 15;
export const BOUNDARY_MIN_ZOOM = PICK_MIN_ZOOM;

/** Сетка ячеек, которыми грузятся границы (та же, что в backend/app/api/parcel_grid.py), ~1,1 × 1,0 км. */
export const CELL_LAT = 0.01;
export const CELL_LON = 0.015;

/** Цвет границ делянок: мягкий янтарный — виден и на тёмном спутнике, и на светлой карте рельефа. */
export const BOUNDARY_COLOR = '#ffb547';
export const PARCEL_FILL = '#4fa183';

/** Толщина линии границ по зуму: на крупном зуме чуть шире, на мелком — тоньше, чтобы не «забивать» карту. */
export function boundaryWeight(zoom: number): number {
  const table: Record<number, number> = { 15: 0.6, 16: 0.9, 17: 1.3, 18: 1.8, 19: 2.2 };
  const z = Math.round(Math.min(19, Math.max(15, zoom)));
  return table[z] ?? 1;
}

/** Leaflet-панели: границы над масками/воеводствами (overlayPane = 400), выбранная делянка — над границами. */
export const PANE_BOUNDARIES = 'parcel-boundaries';
export const PANE_SELECTED = 'parcel-selected';
