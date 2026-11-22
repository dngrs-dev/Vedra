import { useCallback, useRef, useState } from 'react';
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

/** Выбор участка: по ID (поиск), по клику на карте или своим прямоугольником (Ctrl + перетаскивание). Кладёт результат в store. */
export function useParcelSelect() {
  const setParcel = useAnalysisStore((s) => s.setParcel);
  const [loading, setLoading] = useState(false);
  /** Сколько делянок уже найдено в рамке (null — поиск по рамке не идёт) */
  const [found, setFound] = useState<number | null>(null);
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
          parcel = fallback(); // An unavailable register leaves a labeled demonstration outline.
          toast(pl.search.demoFallback);
        }
        if (!ctrl.signal.aborted) setParcel(parcel);
      } catch (e) {
        toast(e instanceof ParcelNotFoundError ? pl.search.notFound : pl.search.unavailable, 'error');
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

  /**
   * Ctrl + ЛКМ рамка → выбираются ВСЕ делянки из ewidencji, которые попали в рамку (групповой выбор).
   * Одна делянка → обычный выбор. Ни одной (дорога, вода) или ULDK недоступен → рамка = «własny obszar».
   */
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

      const customArea: Parcel = {
        id: `OBSZAR_${center.lat.toFixed(4)}_${center.lng.toFixed(4)}`,
        ring,
        areaHa,
        center,
        isCustom: true
      };

      // «Zwykły wybór» — просто прямоугольник, без поиска делянок
      if (useAnalysisStore.getState().selectMode === 'simple') {
        abortRef.current?.abort();
        setLoading(false);
        setFound(null);
        setParcel(customArea);
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
          const parts = res.parcels.map((p) => ({ id: p.id, ring: p.ring, areaHa: p.areaHa }));
          const total = +parts.reduce((sum, p) => sum + p.areaHa, 0).toFixed(2);
          // объединяем делянки в один общий контур (без внутренних границ)
          let outline = unionRings(parts.map((p) => p.ring));
          if (!outline.length) outline = parts.map((p) => [p.ring]); // на всякий случай — показываем как есть
          setParcel({
            id: `GRUPA_${parts.length}_${center.lat.toFixed(4)}_${center.lng.toFixed(4)}`,
            ring,
            areaHa: total,
            center,
            parts,
            outline
          });
          toast(
            outline.length > 1
              ? `Połączono ${dzialki(parts.length)} (${total} ha) w ${outline.length} części — rozdziela je np. droga lub rów.`
              : `Połączono ${dzialki(parts.length)} w jeden obszar (${total} ha).`
          );
        } else {
          setParcel(customArea);
          toast(
            res.serviceDown
              ? 'Usługa ULDK niedostępna — zaznaczony prostokąt użyto jako własny obszar.'
              : 'W zaznaczeniu nie ma działki ewidencyjnej — użyto zaznaczonego obszaru.'
          );
        }
        if (res.skippedEdge > 0 && res.parcels.length > 0 && !res.truncated) {
          setTimeout(() => toast(`Pominięto ${dzialki(res.skippedEdge)}, które tylko zahaczają o ramkę.`), 2500);
        }
        if (res.truncated) toast('Zaznaczenie jest bardzo duże — pokazano tylko część działek. Zaznacz mniejszy obszar.', 'error');
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setParcel(customArea);
      } finally {
        if (abortRef.current === ctrl) {
          setLoading(false);
          setFound(null);
        }
      }
    },
    [setParcel]
  );

  /** Готовая делянка (из загруженного слоя границ): мгновенно, без сети; идущий запрос отменяется. */
  const selectParcel = useCallback(
    (parcel: Parcel) => {
      abortRef.current?.abort();
      abortRef.current = null;
      setLoading(false);
      setFound(null);
      setParcel(parcel);
    },
    [setParcel]
  );

  return { loading, found, selectById, selectByLatLng, selectArea, selectParcel };
}
