/**
 * Klikanie w mapę przybliża ją krokami, a działkę wybiera się dopiero na poziomie działek:
 *   województwo (≈8) → klik → ≈12 → klik → 15 (poziom obrębów) → klik → 17 (poziom działek) → klik = wybór.
 * Tak samo przy włączonym i wyłączonym przełączniku «Granice działek» - on tylko rysuje linie.
 */
/** Poniżej tego zumu klik przybliża mniej więcej w pół drogi do poziomu obrębów */
export const ZOOM_STEP_FROM = 11;
/** Warstwa granic, poziom 1: obręby ewidencyjne (grupy działek) - zum 15-16 */
export const OBREB_MIN_ZOOM = 15;
/** Warstwa granic, poziom 2: pojedyncze działki - od zumu 17 (1-4 komórki na ekran) */
export const PARCEL_BOUNDARY_MIN_ZOOM = 17;
/** Od tego zumu klik wybiera działkę (na 17 przy ~52° 1 px ≈ 0,8 m - pojedyncze działki są dobrze widoczne) */
export const PICK_MIN_ZOOM = PARCEL_BOUNDARY_MIN_ZOOM;

/** Zum, do którego przybliża klik na mniejszym zumie niż PICK_MIN_ZOOM */
export function nextZoomStep(zoom: number): number {
  if (zoom < ZOOM_STEP_FROM) return Math.ceil((zoom + OBREB_MIN_ZOOM) / 2);
  if (zoom < OBREB_MIN_ZOOM) return OBREB_MIN_ZOOM;
  return PICK_MIN_ZOOM;
}

export type BoundaryKind = 'obreby' | 'parcels';

/** Сетки ячеек, которыми грузятся границы (те же, что в backend/app/api/parcel_grid.py). */
export const GRIDS: Record<BoundaryKind, { lat: number; lon: number; path: string }> = {
  parcels: { lat: 0.01, lon: 0.015, path: '/parcels/in-bbox' },
  obreby: { lat: 0.04, lon: 0.06, path: '/parcels/obreby-in-bbox' }
};

/** Цвет границ: мягкий янтарный - виден и на тёмном спутнике, и на светлой карте рельефа. */
export const BOUNDARY_COLOR = '#ffb547';
export const PARCEL_FILL = '#4fa183';

/** Толщина линии по зуму: на крупном зуме чуть шире, на мелком - тоньше, чтобы не «забивать» карту. */
export function boundaryWeight(zoom: number, kind: BoundaryKind = 'parcels'): number {
  const z = Math.round(zoom);
  if (kind === 'obreby') return z >= 16 ? 1.5 : 1.2;
  const table: Record<number, number> = { 17: 0.9, 18: 1.4, 19: 1.9 };
  return table[Math.min(19, Math.max(17, z))] ?? 1;
}

/** Leaflet-панели: границы над масками/воеводствами (overlayPane = 400), выбранная делянка - над границами. */
export const PANE_BOUNDARIES = 'parcel-boundaries';
export const PANE_SELECTED = 'parcel-selected';
export const PANE_USER_LOCATION = 'user-location';

/** Ключ localStorage для переключателя «Granice działek» */
export const BOUNDARIES_STORAGE_KEY = 'vedra.boundaries';
