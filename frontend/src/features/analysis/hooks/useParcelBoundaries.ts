import { useEffect, useMemo, useState } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { toast } from '@/components/ui/toastStore';
import { CELL_LAT, CELL_LON } from '@/constants/map';
import { pl } from '@/constants/pl';
import { getParcelsInBbox, type BoundaryFeature } from '@/services/parcelApi';

/** Ячейки, уже загруженные за сессию (переживают размонтирование слоя при отдалении). */
const cellCache = new Map<string, BoundaryFeature[]>();
const inFlight = new Set<string>();
const MAX_CACHED_CELLS = 300;
/** Больше ячеек за раз не грузим (огромный монитор / дробный зум) */
const MAX_VISIBLE_CELLS = 48;
const DEBOUNCE_MS = 250;
let warned = false;

const cellKey = (i: number, j: number) => `${i}:${j}`;

function visibleCells(map: LeafletMap): [number, number][] {
  const b = map.getBounds().pad(0.15);
  const i0 = Math.floor(b.getSouth() / CELL_LAT);
  const i1 = Math.floor(b.getNorth() / CELL_LAT);
  const j0 = Math.floor(b.getWest() / CELL_LON);
  const j1 = Math.floor(b.getEast() / CELL_LON);
  const out: [number, number][] = [];
  for (let i = i0; i <= i1; i++) for (let j = j0; j <= j1; j++) out.push([i, j]);
  // ближние к центру — первыми
  const ci = (i0 + i1) / 2;
  const cj = (j0 + j1) / 2;
  out.sort((a, c) => Math.hypot(a[0] - ci, a[1] - cj) - Math.hypot(c[0] - ci, c[1] - cj));
  return out.slice(0, MAX_VISIBLE_CELLS);
}

function remember(key: string, features: BoundaryFeature[]) {
  cellCache.delete(key);
  cellCache.set(key, features);
  while (cellCache.size > MAX_CACHED_CELLS) {
    const oldest = cellCache.keys().next().value;
    if (oldest === undefined) break;
    cellCache.delete(oldest);
  }
}

/**
 * Контуры делянок вокруг видимой области. Грузятся по ячейкам фиксированной сетки (кэш на бэкенде и здесь),
 * поэтому панорамирование догружает только новые ячейки, а границы появляются постепенно — от центра к краям.
 */
export function useParcelBoundaries(map: LeafletMap | null, enabled: boolean) {
  const [cells, setCells] = useState<string[]>([]);
  const [version, setVersion] = useState(0);
  const [pending, setPending] = useState(0);

  useEffect(() => {
    if (!map || !enabled) {
      setCells([]);
      return;
    }
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const load = (i: number, j: number) => {
      const key = cellKey(i, j);
      if (cellCache.has(key) || inFlight.has(key)) return;
      inFlight.add(key);
      setPending((n) => n + 1);
      getParcelsInBbox({
        minLat: i * CELL_LAT,
        minLng: j * CELL_LON,
        maxLat: (i + 1) * CELL_LAT,
        maxLng: (j + 1) * CELL_LON
      })
        .then((features) => {
          remember(key, features);
          if (alive) setVersion((v) => v + 1);
        })
        .catch(() => {
          if (!warned) {
            warned = true;
            toast(pl.map.boundariesFailed, 'error');
          }
        })
        .finally(() => {
          inFlight.delete(key);
          if (alive) setPending((n) => Math.max(0, n - 1));
        });
    };

    const update = () => {
      const visible = visibleCells(map);
      setCells(visible.map(([i, j]) => cellKey(i, j)));
      visible.forEach(([i, j]) => load(i, j));
    };
    const schedule = () => {
      clearTimeout(timer);
      timer = setTimeout(update, DEBOUNCE_MS);
    };

    update();
    map.on('moveend zoomend', schedule);
    return () => {
      alive = false;
      clearTimeout(timer);
      map.off('moveend zoomend', schedule);
      setPending(0);
    };
  }, [map, enabled]);

  const features = useMemo(() => {
    const seen = new Map<string, BoundaryFeature>();
    for (const key of cells) for (const f of cellCache.get(key) ?? []) if (!seen.has(f.id)) seen.set(f.id, f);
    return [...seen.values()];
  }, [cells, version]); // version: пересчёт после догрузки ячейки

  return { features, loading: pending > 0 };
}
