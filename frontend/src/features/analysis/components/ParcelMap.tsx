import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import L, { type Map as LeafletMap } from 'leaflet';
import { FullscreenIcon, LayersIcon, LocateIcon, SearchIcon } from '@/components/ui/Icons';
import { toast } from '@/components/ui/toastStore';
import { PolandMap, type BaseLayer } from '@/components/map/PolandMap';
import type { UserPosition } from '@/components/map/UserLocation';
import {
  BOUNDARIES_STORAGE_KEY,
  OBREB_MIN_ZOOM,
  PARCEL_BOUNDARY_MIN_ZOOM,
  PICK_MIN_ZOOM,
  nextZoomStep
} from '@/constants/map';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS } from '@/constants/poland';
import { parcelFromBoundary, type BoundaryFeature } from '@/services/parcelApi';
import type { LatLng, Parcel } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import {
  findLoadedParcelAt,
  prefetchAround,
  prefetchView,
  useParcelBoundaries,
  type BoundaryMode
} from '../hooks/useParcelBoundaries';
import { useParcelSelect } from '../hooks/useParcelSelect';
import { useVoivodeships } from '../hooks/useVoivodeships';
import { useAnalysisStore } from '../store';

/** Рамка делянки / группы (внешние контуры) */
function parcelBounds(p: Parcel): L.LatLngBounds {
  const rings = p.outline ? p.outline.map((poly) => poly[0] ?? []) : p.parts ? p.parts.map((x) => x.ring) : [p.ring];
  return L.latLngBounds(rings.flat());
}

/** Индикатор «Pobieram działkę…» - только если ответ дольше этого (быстрые ответы из кэша не мигают) */
const LOADER_DELAY_MS = 400;

/** Точность хуже этой (м) - показываем весь круг точности, а не приближаем к точке */
const LOCATE_FIT_ACCURACY_M = 300;

function readBoundariesPref(): boolean {
  try {
    return localStorage.getItem(BOUNDARIES_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

function writeBoundariesPref(on: boolean) {
  try {
    localStorage.setItem(BOUNDARIES_STORAGE_KEY, on ? '1' : '0');
  } catch {
    // приватный режим / заблокированное хранилище - просто не запоминаем
  }
}

/**
 * Карта + плавающие элементы управления.
 * Сценарий: клик по воеводству → приближение → клик (приближает к точке до PICK_MIN_ZOOM) → клик по делянке
 * ИЛИ Ctrl + перетаскивание (своя область) → «Potwierdź działkę» в правой панели → расчёт на бэкенде.
 * Переключатель «Granice działek» (по умолчанию выкл.): на зуме 15-16 - obręby (фон), с 17 - делянки
 * (наведение показывает номер). Выбор кликом камеру не двигает; «Pokaż całą działkę» - если делянка не влезает.
 */
export function ParcelMap() {
  const parcel = useAnalysisStore((s) => s.parcel);
  const region = useAnalysisStore((s) => s.region);
  const setRegion = useAnalysisStore((s) => s.setRegion);
  const { loading, found, selectById, selectByIds, selectByLatLng, selectArea, selectParcel } = useParcelSelect();
  const { data: regions, isError: regionsFailed } = useVoivodeships();
  useEffect(() => {
    if (regionsFailed) toast(pl.map.regionsFailed, 'error');
  }, [regionsFailed]);

  const [map, setMap] = useState<LeafletMap | null>(null);
  const [layer, setLayer] = useState<BaseLayer>('satellite');
  const [boundariesOn, setBoundariesOn] = useState(readBoundariesPref);
  const [query, setQuery] = useState('');
  const [batchOpen, setBatchOpen] = useState(false);
  const [batchQuery, setBatchQuery] = useState('');
  const [zoom, setZoom] = useState(0);
  /** Делянка, по которой кликнули, пока идёт запрос по точке - заливается сразу, до ответа бэкенда */
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [userPosition, setUserPosition] = useState<UserPosition | null>(null);
  const [watching, setWatching] = useState(false);
  /** Выбранная делянка не помещается в видимую область - показываем кнопку «Pokaż całą działkę» */
  const [parcelOffscreen, setParcelOffscreen] = useState(false);
  const cardRef = useRef<HTMLElement>(null);
  const lastAreaAt = useRef(0);
  /** Контур под последним кликом (слой границ сообщает его раньше, чем карта - сам клик) */
  const clickedFeature = useRef<BoundaryFeature | null>(null);
  const watchId = useRef<number | null>(null);
  const centerOnNextFix = useRef(false);

  useEffect(() => {
    if (!map) return;
    const sync = () => setZoom(map.getZoom());
    sync();
    map.on('zoomend', sync);
    return () => {
      map.off('zoomend', sync);
    };
  }, [map]);

  useEffect(() => {
    if (!loading) setPendingId(null);
  }, [loading]);

  // индикатор загрузки с задержкой; поиск в рамке (found !== null) показываем сразу - он заведомо долгий
  const [showLoader, setShowLoader] = useState(false);
  useEffect(() => {
    if (!loading) {
      setShowLoader(false);
      return;
    }
    if (found !== null) {
      setShowLoader(true);
      return;
    }
    const t = setTimeout(() => setShowLoader(true), LOADER_DELAY_MS);
    return () => clearTimeout(t);
  }, [loading, found]);

  // на зуме выбора - фоновая подгрузка контуров видимой области ещё до клика (и при выключенных границах)
  useEffect(() => {
    if (!map) return;
    const onMove = () => {
      if (map.getZoom() >= PICK_MIN_ZOOM) prefetchView(map);
    };
    onMove();
    map.on('moveend', onMove);
    return () => {
      map.off('moveend', onMove);
    };
  }, [map]);

  // после выбора - фоновая подгрузка контуров вокруг: следующий клик рядом выберет делянку мгновенно
  useEffect(() => {
    if (!parcel || parcel.isCustom || parcel.parts || parcel.isDemo) return;
    prefetchAround(parcel.center.lat, parcel.center.lng);
  }, [parcel]);

  useEffect(() => {
    if (!map || !parcel || parcel.isCustom) {
      setParcelOffscreen(false);
      return;
    }
    const bounds = parcelBounds(parcel);
    const check = () => setParcelOffscreen(!map.getBounds().contains(bounds));
    check();
    map.on('moveend', check);
    return () => {
      map.off('moveend', check);
    };
  }, [map, parcel]);

  const fitParcel = useCallback(
    (p: Parcel) => map?.fitBounds(parcelBounds(p), { maxZoom: 17, padding: [60, 60], animate: true }),
    [map]
  );

  /** Камеру двигаем только при поиске по ID и выделении рамкой - выбор кликом оставляет вид как есть */
  const fitIfChanged = useCallback(
    (beforeId: string | undefined, groupsOnly = false) => {
      const now = useAnalysisStore.getState().parcel;
      if (!now || now.id === beforeId || now.isCustom || (groupsOnly && !now.parts)) return;
      fitParcel(now);
    },
    [fitParcel]
  );

  const mode: BoundaryMode = !boundariesOn || zoom < OBREB_MIN_ZOOM
    ? 'off'
    : zoom < PARCEL_BOUNDARY_MIN_ZOOM ? 'obreby' : 'parcels';
  const boundaries = useParcelBoundaries(map, mode);

  // Воеводство выбрано (или его границы не загрузились - тогда не блокируем работу)
  const regionReady = region !== null || !regions;

  const toggleBoundaries = () => {
    setBoundariesOn((on) => {
      writeBoundariesPref(!on);
      return !on;
    });
  };

  const selectRegion = useCallback(
    (v: Voivodeship, fit: boolean) => {
      setRegion(v.name);
      if (fit) map?.fitBounds(v.bounds, { padding: [30, 30], animate: true });
    },
    [map, setRegion]
  );

  const resetView = () => {
    setRegion(null);
    map?.fitBounds(POLAND_BOUNDS, { animate: true });
  };

  const pick = (lat: number, lng: number) => {
    const hit = clickedFeature.current;
    clickedFeature.current = null;
    if (Date.now() - lastAreaAt.current < 400) return; // «хвост» клика после Ctrl-выделения
    const z = map?.getZoom() ?? zoom;
    if (z < PICK_MIN_ZOOM) {
      // мелкий зум: клик - это «лотерея» среди десятков делянок; приближаем к точке шагами
      // (воеводство → пол-пути → уровень obrębów → уровень делянок), выбор - только на уровне делянок
      if (regionReady) map?.setView([lat, lng], nextZoomStep(z), { animate: true });
      return;
    }
    // зум ≥ 17 (уровень делянок): выбор.
    // Сначала - из уже загруженных контуров (слой границ или фоновая подгрузка): без запроса и без индикатора.
    const loaded = (hit && mode === 'parcels' ? hit : null) ?? findLoadedParcelAt(lat, lng);
    if (loaded) {
      if (loaded.id === parcel?.id) return; // повторный клик по уже выбранной делянке
      const ready = parcelFromBoundary(loaded);
      if (ready) {
        selectParcel(ready);
        return;
      }
    }
    void selectByLatLng(lat, lng);
    if (hit && mode === 'parcels') setPendingId(hit.id);
  };

  const onBoundaryClick = useCallback((feature: BoundaryFeature) => {
    clickedFeature.current = feature;
  }, []);

  // useCallback: AreaSelect переподписывается на события при смене функции - она должна быть стабильной
  const onArea = useCallback(
    (ring: LatLng[]) => {
      lastAreaAt.current = Date.now();
      const before = useAnalysisStore.getState().parcel?.id;
      void selectArea(ring).then(() => fitIfChanged(before, true));
    },
    [selectArea, fitIfChanged]
  );

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const before = useAnalysisStore.getState().parcel?.id;
    void selectById(query).then(() => fitIfChanged(before));
  };

  const onBatchSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const before = useAnalysisStore.getState().parcel?.id;
    if (await selectByIds(batchQuery)) {
      setBatchOpen(false);
      fitIfChanged(before);
    }
  };

  /* ---------- геолокация: точка + круг точности, обновляется при перемещении ---------- */

  const stopWatching = useCallback(() => {
    if (watchId.current !== null) navigator.geolocation?.clearWatch(watchId.current);
    watchId.current = null;
    setWatching(false);
  }, []);

  useEffect(() => stopWatching, [stopWatching]);

  const centerOn = (pos: UserPosition) => {
    if (!map) return;
    if (pos.accuracy > LOCATE_FIT_ACCURACY_M) {
      map.fitBounds(L.latLng(pos.lat, pos.lng).toBounds(pos.accuracy * 2), { animate: true, maxZoom: PICK_MIN_ZOOM });
    } else {
      map.setView([pos.lat, pos.lng], Math.max(map.getZoom(), PICK_MIN_ZOOM), { animate: true });
    }
  };
  const centerOnRef = useRef(centerOn);
  centerOnRef.current = centerOn;

  const locate = () => {
    if (!navigator.geolocation) return toast(pl.map.locateUnavailable, 'error');
    if (watchId.current !== null) {
      // уже следим: повторное нажатие только центрирует (или центрирует при первой позиции)
      if (userPosition) centerOn(userPosition);
      else centerOnNextFix.current = true;
      return;
    }
    centerOnNextFix.current = true;
    setWatching(true);
    let hadFix = false;
    watchId.current = navigator.geolocation.watchPosition(
      (p) => {
        hadFix = true;
        const pos = { lat: p.coords.latitude, lng: p.coords.longitude, accuracy: p.coords.accuracy };
        setUserPosition(pos);
        if (centerOnNextFix.current) {
          centerOnNextFix.current = false;
          centerOnRef.current(pos);
        }
      },
      (err) => {
        // единичный сбой при уже найденной позиции не мешает - точка остаётся
        if (err.code !== err.PERMISSION_DENIED && hadFix) return;
        stopWatching();
        if (err.code === err.PERMISSION_DENIED) setUserPosition(null);
        toast(pl.map.locateFailed, 'error');
      },
      { enableHighAccuracy: true, maximumAge: 10_000, timeout: 20_000 }
    );
  };

  const fullscreen = () => {
    const el = cardRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
    setTimeout(() => map?.invalidateSize(), 300);
  };

  const toggleSub = !boundariesOn
    ? pl.map.boundariesOff
    : mode === 'off'
      ? pl.map.boundariesZoomIn
      : mode === 'obreby'
        ? pl.map.boundariesObreby
        : pl.map.boundariesParcels;

  return (
    <section className="map-card" aria-label="Mapa działek" ref={cardRef}>
      <PolandMap
        parcel={parcel}
        layer={layer}
        regions={regions}
        activeRegion={region}
        onRegionSelect={selectRegion}
        onPick={pick}
        onArea={onArea}
        onReady={setMap}
        zoom={zoom}
        boundaryKind={mode === 'off' ? null : mode}
        boundaries={boundaries}
        pendingId={pendingId}
        onBoundaryClick={onBoundaryClick}
        userPosition={userPosition}
      />

      <form className="map-search" role="search" autoComplete="off" onSubmit={onSubmit}>
        <button type="submit" className="map-search__btn" aria-label="Szukaj"><SearchIcon /></button>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={pl.search.placeholder}
          aria-label="Identyfikator działki ewidencyjnej"
          spellCheck={false}
        />
        <button type="button" className="map-search__batch" aria-expanded={batchOpen} aria-controls="map-batch-search"
          onClick={() => setBatchOpen(!batchOpen)}>{pl.batch.openLookup}</button>
      </form>
      <form id="map-batch-search" className="map-batch-search" hidden={!batchOpen}
        autoComplete="off" onSubmit={(event) => void onBatchSubmit(event)}>
        <label htmlFor="batch-parcel-ids">{pl.batch.lookupTitle}</label>
        <textarea id="batch-parcel-ids" className="input" rows={4} value={batchQuery} spellCheck={false}
          aria-describedby="batch-parcel-hint" onChange={(event) => setBatchQuery(event.target.value)} />
        <small id="batch-parcel-hint" className="muted">{pl.batch.lookupHint}</small>
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? pl.batch.lookupPending : pl.batch.lookupSubmit}
        </button>
      </form>

      <div className="map-type" role="group" aria-label="Typ mapy">
        <button type="button" className={layer === 'satellite' ? 'is-active' : ''} onClick={() => setLayer('satellite')}>
          {pl.map.satellite}
        </button>
        <button type="button" className={layer === 'terrain' ? 'is-active' : ''} onClick={() => setLayer('terrain')}>
          {pl.map.terrain}
        </button>
      </div>

      <div className="map-side-btns">
        <button
          type="button"
          role="switch"
          aria-checked={boundariesOn}
          className={`map-toggle${boundariesOn ? ' is-on' : ''}`}
          title={pl.map.boundariesHint}
          onClick={toggleBoundaries}
        >
          <LayersIcon size={16} />
          <span className="map-toggle__text">
            <span className="map-toggle__label">{pl.map.boundaries}</span>
            <span className="map-toggle__sub">{toggleSub}</span>
          </span>
          <span className="map-toggle__track" aria-hidden="true"><span className="map-toggle__thumb" /></span>
        </button>
        <button
          type="button"
          className={`sq-btn${watching ? ' is-active' : ''}`}
          aria-label={pl.map.locate}
          aria-pressed={watching}
          title={pl.map.locate}
          onClick={locate}
        >
          <LocateIcon />
        </button>
      </div>

      <div className="map-zoom">
        <button type="button" aria-label={pl.map.zoomIn} onClick={() => map?.zoomIn()}>+</button>
        <button type="button" aria-label={pl.map.zoomOut} onClick={() => map?.zoomOut()}>-</button>
      </div>
      <button type="button" className="sq-btn map-fullscreen" aria-label={pl.map.fullscreen} title={pl.map.fullscreen} onClick={fullscreen}>
        <FullscreenIcon />
      </button>

      {region && (
        <div className="map-region">
          <span>{region}</span>
          <button type="button" onClick={resetView}>{pl.map.backToPoland}</button>
        </div>
      )}

      {/* Bez tekstowych podpowiedzi na mapie - na dole tylko przyciski akcji, gdy są potrzebne */}
      {parcel && parcelOffscreen && (
        <div className="map-hint map-hint--actions">
          <button type="button" className="map-hint__btn" onClick={() => fitParcel(parcel)}>
            {pl.map.showWholeParcel}
          </button>
        </div>
      )}

      {loading && showLoader && (
        <div className="map-loader">
          <span className="spinner" />
          {found === null ? 'Pobieram działkę…' : `Szukam działek w zaznaczeniu… znaleziono: ${found}`}
        </div>
      )}
    </section>
  );
}
