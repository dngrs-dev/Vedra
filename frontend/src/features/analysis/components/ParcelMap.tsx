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
  PICK_MIN_ZOOM
} from '@/constants/map';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS } from '@/constants/poland';
import { parcelFromBoundary, type BoundaryFeature } from '@/services/parcelApi';
import type { LatLng } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { useParcelBoundaries, type BoundaryMode } from '../hooks/useParcelBoundaries';
import { useParcelSelect } from '../hooks/useParcelSelect';
import { useVoivodeships } from '../hooks/useVoivodeships';
import { useAnalysisStore } from '../store';

/** Точность хуже этой (м) — показываем весь круг точности, а не приближаем к точке */
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
    // приватный режим / заблокированное хранилище — просто не запоминаем
  }
}

/**
 * Карта + плавающие элементы управления.
 * Сценарий: клик по воеводству → приближение → клик (приближает к точке до PICK_MIN_ZOOM) → клик по делянке
 * ИЛИ Ctrl + перетаскивание (своя область) → «Potwierdź działkę» в правой панели → расчёт на бэкенде.
 * Переключатель «Granice działek» (по умолчанию выкл.): на зуме 15–16 — obręby (клик приближает), с 17 — делянки
 * (наведение показывает номер, клик выбирает мгновенно — контур уже загружен).
 */
export function ParcelMap() {
  const parcel = useAnalysisStore((s) => s.parcel);
  const region = useAnalysisStore((s) => s.region);
  const setRegion = useAnalysisStore((s) => s.setRegion);
  const { loading, found, selectById, selectByLatLng, selectArea, selectParcel } = useParcelSelect();
  const { data: regions, isError: regionsFailed } = useVoivodeships();

  const [map, setMap] = useState<LeafletMap | null>(null);
  const [layer, setLayer] = useState<BaseLayer>('satellite');
  const [boundariesOn, setBoundariesOn] = useState(readBoundariesPref);
  const [query, setQuery] = useState('');
  const [zoom, setZoom] = useState(0);
  /** Делянка, по которой кликнули, пока идёт запрос по точке — заливается сразу, до ответа бэкенда */
  const [pendingId, setPendingId] = useState<string | null>(null);
  const [userPosition, setUserPosition] = useState<UserPosition | null>(null);
  const [watching, setWatching] = useState(false);
  const cardRef = useRef<HTMLElement>(null);
  const lastAreaAt = useRef(0);
  /** Контур под последним кликом (слой границ сообщает его раньше, чем карта — сам клик) */
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

  const mode: BoundaryMode = !boundariesOn || zoom < OBREB_MIN_ZOOM
    ? 'off'
    : zoom < PARCEL_BOUNDARY_MIN_ZOOM ? 'obreby' : 'parcels';
  const boundaries = useParcelBoundaries(map, mode);

  // Воеводство выбрано (или его границы не загрузились — тогда не блокируем работу)
  const regionReady = region !== null || !regions;

  const toggleBoundaries = () => {
    setBoundariesOn((on) => {
      writeBoundariesPref(!on);
      return !on;
    });
  };

  const selectRegion = useCallback(
    (v: Voivodeship) => {
      setRegion(v.name);
      map?.fitBounds(v.bounds, { padding: [30, 30], animate: true });
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
      // мелкий зум: клик — это «лотерея» среди десятков делянок; приближаем к точке, выбор — следующим кликом
      if (regionReady) map?.setView([lat, lng], PICK_MIN_ZOOM, { animate: true });
      return;
    }
    if (mode === 'obreby') {
      // уровень obrębów: клик приближает до уровня делянок
      map?.setView([lat, lng], PARCEL_BOUNDARY_MIN_ZOOM, { animate: true });
      return;
    }
    if (hit && mode === 'parcels') {
      if (hit.id === parcel?.id) return; // повторный клик по уже выбранной делянке
      const ready = parcelFromBoundary(hit);
      if (ready) {
        selectParcel(ready); // контур уже загружен — выбор без запроса к серверу
        return;
      }
    }
    void selectByLatLng(lat, lng);
    if (hit) setPendingId(hit.id);
  };

  const onBoundaryClick = useCallback((feature: BoundaryFeature) => {
    clickedFeature.current = feature;
  }, []);

  // useCallback: AreaSelect переподписывается на события при смене функции — она должна быть стабильной
  const onArea = useCallback(
    (ring: LatLng[]) => {
      lastAreaAt.current = Date.now();
      selectArea(ring);
    },
    [selectArea]
  );

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void selectById(query);
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
        // единичный сбой при уже найденной позиции не мешает — точка остаётся
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

  const hint = !regionReady && zoom < PICK_MIN_ZOOM
    ? pl.map.hintRegion
    : parcel
      ? pl.map.hintSelected
      : zoom < PICK_MIN_ZOOM
        ? pl.map.hintZoom
        : mode === 'obreby'
          ? pl.map.hintObreby
          : pl.map.hintParcel;

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
        <button type="button" aria-label={pl.map.zoomOut} onClick={() => map?.zoomOut()}>−</button>
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

      <div className="map-hint" role="note">
        {hint}
        {regionsFailed && <span className="map-hint__warn"> · {pl.map.regionsFailed}</span>}
      </div>

      {loading && (
        <div className="map-loader">
          <span className="spinner" />
          {found === null ? 'Pobieram działkę…' : `Szukam działek w zaznaczeniu… znaleziono: ${found}`}
        </div>
      )}
    </section>
  );
}
