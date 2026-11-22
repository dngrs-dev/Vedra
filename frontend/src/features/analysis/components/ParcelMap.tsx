import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { FullscreenIcon, LayersIcon, LocateIcon, SearchIcon } from '@/components/ui/Icons';
import { toast } from '@/components/ui/toastStore';
import { PolandMap, type BaseLayer } from '@/components/map/PolandMap';
import { BOUNDARY_MIN_ZOOM, PICK_MIN_ZOOM } from '@/constants/map';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS } from '@/constants/poland';
import type { LatLng } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { useParcelBoundaries } from '../hooks/useParcelBoundaries';
import { useParcelSelect } from '../hooks/useParcelSelect';
import { useVoivodeships } from '../hooks/useVoivodeships';
import { useAnalysisStore } from '../store';

/**
 * Карта + плавающие элементы управления.
 * Сценарий: клик по воеводству → приближение → клик (приближает к точке до PICK_MIN_ZOOM) → на крупном зуме видны
 * границы делянок, наведение показывает код, клик выбирает делянку; ИЛИ Ctrl + перетаскивание (своя область)
 * → «Potwierdź działkę» в правой панели → расчёт на бэкенде.
 */
export function ParcelMap() {
  const parcel = useAnalysisStore((s) => s.parcel);
  const region = useAnalysisStore((s) => s.region);
  const setRegion = useAnalysisStore((s) => s.setRegion);
  const { loading, found, selectById, selectByLatLng, selectArea } = useParcelSelect();
  const { data: regions, isError: regionsFailed } = useVoivodeships();

  const [map, setMap] = useState<LeafletMap | null>(null);
  const [layer, setLayer] = useState<BaseLayer>('satellite');
  const [showParcels, setShowParcels] = useState(true);
  const [query, setQuery] = useState('');
  const [zoom, setZoom] = useState(0);
  /** Делянка, по которой кликнули, пока идёт запрос — заливается сразу, до ответа бэкенда */
  const [pendingId, setPendingId] = useState<string | null>(null);
  const cardRef = useRef<HTMLElement>(null);
  const lastAreaAt = useRef(0);
  /** ID контура под последним кликом (слой границ сообщает его раньше, чем карта — сам клик) */
  const clickedId = useRef<string | null>(null);

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

  const zoomedIn = zoom >= PICK_MIN_ZOOM;
  // Воеводство выбрано (или его границы не загрузились — тогда не блокируем работу)
  const regionReady = region !== null || !regions;
  // Кликом делянку выбираем только на крупном зуме: на мелком клик — это «лотерея» среди десятков делянок
  const canPick = zoomedIn;
  const showBoundaries = showParcels && zoom >= BOUNDARY_MIN_ZOOM;
  const { features: boundaries } = useParcelBoundaries(map, showBoundaries);

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
    const hitId = clickedId.current;
    clickedId.current = null;
    if (Date.now() - lastAreaAt.current < 400) return; // «хвост» клика после Ctrl-выделения
    if (!canPick) {
      // мелкий зум внутри воеводства: приближаем к точке клика, выбор — следующим кликом
      if (regionReady) map?.setView([lat, lng], PICK_MIN_ZOOM, { animate: true });
      return;
    }
    if (hitId && hitId === parcel?.id) return; // повторный клик по уже выбранной делянке
    void selectByLatLng(lat, lng);
    if (hitId) setPendingId(hitId);
  };

  const onBoundaryClick = useCallback((id: string) => {
    clickedId.current = id;
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

  const locate = () => {
    if (!navigator.geolocation) return toast('Geolokalizacja niedostępna w tej przeglądarce', 'error');
    navigator.geolocation.getCurrentPosition(
      (p) => map?.setView([p.coords.latitude, p.coords.longitude], PICK_MIN_ZOOM),
      () => toast('Nie udało się pobrać lokalizacji', 'error')
    );
  };

  const fullscreen = () => {
    const el = cardRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen?.();
    setTimeout(() => map?.invalidateSize(), 300);
  };

  const hint = !regionReady && !zoomedIn
    ? pl.map.hintRegion
    : parcel
      ? pl.map.hintSelected
      : zoomedIn
        ? pl.map.hintParcel
        : pl.map.hintZoom;

  return (
    <section className="map-card" aria-label="Mapa działek" ref={cardRef}>
      <PolandMap
        parcel={parcel}
        layer={layer}
        showParcels={showParcels}
        regions={regions}
        activeRegion={region}
        onRegionSelect={selectRegion}
        onPick={pick}
        onArea={onArea}
        onReady={setMap}
        zoom={zoom}
        boundaries={showBoundaries ? boundaries : null}
        pendingId={pendingId}
        onBoundaryClick={onBoundaryClick}
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
        <button type="button" className={`sq-btn${showParcels ? '' : ' is-off'}`} aria-label={pl.map.layers} title={pl.map.layers} onClick={() => setShowParcels((v) => !v)}>
          <LayersIcon />
        </button>
        <button type="button" className="sq-btn" aria-label={pl.map.locate} title={pl.map.locate} onClick={locate}>
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
