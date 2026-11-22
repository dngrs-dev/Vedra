import { useCallback, useRef, useState } from 'react';
import { latLngBounds } from 'leaflet';
import { GROUP_JOB_LIMIT } from '@/constants/groupAnalysis';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS, POLAND_OUTLINE } from '@/constants/poland';
import { toast } from '@/components/ui/toastStore';
import { findParcelsInArea, getParcelById, getParcelByLatLng, ParcelNotFoundError } from '@/services/parcelApi';
import type { LatLng, Parcel } from '@/types/parcel';
import { demoSquare, pointInRing, polygonAreaHa, ringCenter } from '@/utils/geo';
import { dzialki } from '@/utils/format';
import { unionRings } from '@/utils/union';
import { isParcelId } from '@/utils/validation';
import { useAnalysisStore } from '../store';

/** Максимальная площадь самостоятельно выделенной области (защита от «выделил пол-Польши»). */
const MAX_CUSTOM_AREA_HA = 5000;

function groupParcels(parcels: Parcel[], ring: LatLng[], center: Parcel['center'], boundary?: LatLng[][][]): Parcel {
  const parts = parcels.map((parcel) => ({ id: parcel.id, ring: parcel.ring, areaHa: parcel.areaHa }));
  const areaHa = +parts.reduce((sum, parcel) => sum + parcel.areaHa, 0).toFixed(2);
  const outline = boundary ?? unionRings(parts.map((parcel) => parcel.ring));
  return {
    id: `GRUPA_${parts.length}_${center.lat.toFixed(4)}_${center.lng.toFixed(4)}`,
    ring,
    areaHa,
    center,
    parts,
    outline: outline.length ? outline : parts.map((parcel) => [parcel.ring])
  };
}

/** Выбор участка: по ID (поиск), по клику на карте или своим прямоугольником (Ctrl + перетаскивание). Кладёт результат в store. */
export function useParcelSelect() {
  const setParcel = useAnalysisStore((s) => s.setParcel);
  const [loading, setLoading] = useState(false);
  /** Сколько делянок уже найдено в рамке (null — поиск по рамке не идёт) */
  const [found, setFound] = useState<number | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(
    async (loader: (signal: AbortSignal) => Promise<Parcel>, fallback?: () => Parcel,
      onError?: (error: unknown) => void) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      try {
        let parcel: Parcel;
        try {
          parcel = await loader(ctrl.signal);
        } catch (e) {
          if (ctrl.signal.aborted) return false;
          if (e instanceof ParcelNotFoundError || !fallback) throw e;
          parcel = fallback(); // An unavailable register leaves a labeled demonstration outline.
          toast(pl.search.demoFallback);
        }
        if (ctrl.signal.aborted) return false;
        setParcel(parcel);
        return true;
      } catch (e) {
        if (!ctrl.signal.aborted) {
          if (onError) onError(e);
          else toast(e instanceof ParcelNotFoundError ? pl.search.notFound : pl.search.unavailable, 'error');
        }
        return false;
      } finally {
        if (abortRef.current === ctrl) setLoading(false);
      }
    },
    [setParcel]
  );

  const selectByIds = useCallback(async (raw: string) => {
    const ids = [...new Map(raw.trim().split(/[\s,;]+/).filter(Boolean)
      .map((id) => [id.toLowerCase(), id])).values()];
    if (!ids.length || ids.some((id) => !isParcelId(id))) {
      toast(pl.batch.invalidList, 'error');
      return false;
    }
    if (ids.length > GROUP_JOB_LIMIT) {
      toast(pl.batch.tooManyIds(GROUP_JOB_LIMIT), 'error');
      return false;
    }

    return run(async (signal) => {
      const parcels: Parcel[] = [];
      for (const id of ids) {
        try {
          parcels.push(await getParcelById(id, signal));
        } catch (error) {
          if (signal.aborted) throw error;
          throw new Error(pl.batch.lookupFailed(id));
        }
      }
      if (parcels.length === 1) return parcels[0]!;
      const boundary = parcels.flatMap((parcel) => parcel.outline ?? [[parcel.ring]]);
      const extent = latLngBounds(boundary.flatMap((rings) => rings[0] ?? []));
      const { lat, lng } = extent.getCenter();
      const south = extent.getSouth(), north = extent.getNorth();
      const west = extent.getWest(), east = extent.getEast();
      return groupParcels(parcels, [[south, west], [south, east], [north, east], [north, west], [south, west]],
        { lat, lng }, boundary);
    }, undefined, (error) => toast(error instanceof Error ? error.message : pl.search.unavailable, 'error'));
  }, [run]);

  const selectById = useCallback(
    (raw: string) => {
      const id = raw.trim();
      if (!isParcelId(id)) {
        toast(pl.search.badFormat, 'error');
        return Promise.resolve();
      }
      return run((signal) => getParcelById(id, signal));
    },
    [run]
  );

  const selectByLatLng = useCallback(
    (lat: number, lng: number) => {
      if (!pointInRing(lat, lng, POLAND_OUTLINE)) {
        // контур упрощённый, поэтому не блокируем жёстко у самой границы — только предупреждаем вдали
        const nearBorder = lat > 48.9 && lat < 55.05 && lng > 13.9 && lng < 24.3;
        if (!nearBorder) {
          toast(pl.search.outsidePoland, 'error');
          return Promise.resolve();
        }
      }
      return run(
        (signal) => getParcelByLatLng(lat, lng, signal),
        () => {
          const ring = demoSquare(lat, lng);
          return {
            id: `DEMO_${lat.toFixed(4)}_${lng.toFixed(4)}`,
            ring,
            areaHa: +polygonAreaHa(ring).toFixed(2),
            center: ringCenter(ring),
            isDemo: true
          };
        }
      );
    },
    [run]
  );

  // Ctrl-drag in smart mode selects registered parcels. Simple mode selects the drawn area.
  const selectArea = useCallback(
    async (ring: LatLng[]) => {
      const areaHa = +polygonAreaHa(ring).toFixed(2);
      const center = ringCenter(ring);
      const [[s, w], [n, e]] = POLAND_BOUNDS;
      if (center.lat < s || center.lat > n || center.lng < w || center.lng > e) {
        toast(pl.search.outsidePoland, 'error');
        return;
      }
      if (areaHa > MAX_CUSTOM_AREA_HA) {
        toast(`Obszar jest zbyt duży (${Math.round(areaHa)} ha). Maksimum: ${MAX_CUSTOM_AREA_HA} ha.`, 'error');
        return;
      }

      if (useAnalysisStore.getState().selectMode === 'simple') {
        abortRef.current?.abort();
        setLoading(false);
        setFound(null);
        setParcel({
          id: `OBSZAR_${center.lat.toFixed(4)}_${center.lng.toFixed(4)}`,
          ring,
          areaHa,
          center,
          isCustom: true
        });
        return;
      }

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      setFound(0);
      try {
        const res = await findParcelsInArea(ring, { signal: ctrl.signal, onProgress: setFound });
        if (ctrl.signal.aborted) return;

        if (res.parcels.length === 1) {
          setParcel(res.parcels[0]!);
        } else if (res.parcels.length > 1) {
          const group = groupParcels(res.parcels, ring, center);
          setParcel(group);
          const total = group.areaHa;
          const outline = group.outline!;
          toast(
            outline.length > 1
              ? `Połączono ${dzialki(res.parcels.length)} (${total} ha) w ${outline.length} części — rozdziela je np. droga lub rów.`
              : `Połączono ${dzialki(res.parcels.length)} w jeden obszar (${total} ha).`
          );
        } else {
          toast(res.serviceDown ? pl.batch.areaLookupFailed : pl.batch.areaNoParcels, 'error');
          return;
        }
        if (res.skippedEdge > 0 && res.parcels.length > 0 && !res.truncated) {
          setTimeout(() => toast(`Pominięto ${dzialki(res.skippedEdge)}, które tylko zahaczają o ramkę.`), 2500);
        }
        if (res.truncated) toast('Zaznaczenie jest bardzo duże — pokazano tylko część działek. Zaznacz mniejszy obszar.', 'error');
      } catch {
        if (!ctrl.signal.aborted) toast(pl.batch.areaLookupFailed, 'error');
      } finally {
        if (abortRef.current === ctrl) {
          setLoading(false);
          setFound(null);
        }
      }
    },
    [setParcel]
  );

  return { loading, found, selectById, selectByIds, selectByLatLng, selectArea };
}
