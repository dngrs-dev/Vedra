import { useCallback, useRef, useState } from 'react';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS, POLAND_OUTLINE } from '@/constants/poland';
import { toast } from '@/components/ui/toastStore';
import { getParcelById, getParcelByLatLng, ParcelNotFoundError } from '@/services/parcelApi';
import type { LatLng, Parcel } from '@/types/parcel';
import { demoSquare, pointInRing, polygonAreaHa, ringCenter } from '@/utils/geo';
import { isParcelId } from '@/utils/validation';
import { useAnalysisStore } from '../store';

/** Максимальная площадь самостоятельно выделенной области (защита от «выделил пол-Польши»). */
const MAX_CUSTOM_AREA_HA = 5000;

/** Выбор участка: по ID (поиск), по клику на карте или своим прямоугольником (Ctrl + перетаскивание). Кладёт результат в store. */
export function useParcelSelect() {
  const setParcel = useAnalysisStore((s) => s.setParcel);
  const [loading, setLoading] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(
    async (loader: (signal: AbortSignal) => Promise<Parcel>, fallback?: () => Parcel) => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setLoading(true);
      try {
        let parcel: Parcel;
        try {
          parcel = await loader(ctrl.signal);
        } catch (e) {
          if (e instanceof DOMException && e.name === 'AbortError') return;
          if (e instanceof ParcelNotFoundError || !fallback) throw e;
          parcel = fallback(); // ULDK недоступен (сеть/CORS) → демо-контур
          toast(pl.search.demoFallback);
        }
        if (!ctrl.signal.aborted) setParcel(parcel);
      } catch (e) {
        toast(e instanceof ParcelNotFoundError ? pl.search.notFound : 'Błąd pobierania działki', 'error');
      } finally {
        if (abortRef.current === ctrl) setLoading(false);
      }
    },
    [setParcel]
  );

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

  /** Своя область: прямоугольник, выделенный Ctrl + ЛКМ. Бэкенду уходит как isCustomArea + geometry. */
  const selectArea = useCallback(
    (ring: LatLng[]) => {
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
      abortRef.current?.abort(); // не даём «опоздавшему» ULDK перезаписать свой выбор
      setLoading(false);
      setParcel({
        id: `OBSZAR_${center.lat.toFixed(4)}_${center.lng.toFixed(4)}`,
        ring,
        areaHa,
        center,
        isCustom: true
      });
    },
    [setParcel]
  );

  return { loading, selectById, selectByLatLng, selectArea };
}
