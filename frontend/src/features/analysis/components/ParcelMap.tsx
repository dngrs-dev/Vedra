import { useCallback, useRef, useState, type FormEvent } from 'react';
import type { Map as LeafletMap } from 'leaflet';
import { FullscreenIcon, LayersIcon, LocateIcon, SearchIcon } from '@/components/ui/Icons';
import { toast } from '@/components/ui/toastStore';
import { PolandMap, type BaseLayer } from '@/components/map/PolandMap';
import { pl } from '@/constants/pl';
import { POLAND_BOUNDS } from '@/constants/poland';
import type { LatLng } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { useParcelSelect } from '../hooks/useParcelSelect';
import { useVoivodeships } from '../hooks/useVoivodeships';
import { useAnalysisStore } from '../store';

/**
 * Карта + плавающие элементы управления.
 * Сценарий: клик по воеводству → приближение → клик по делянке ИЛИ Ctrl + перетаскивание (своя область)
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
  const cardRef = useRef<HTMLElement>(null);
  const lastAreaAt = useRef(0);

  // Если границы воеводств не загрузились — не блокируем работу: выбор делянки доступен сразу.
  const canPick = region !== null || !regions;

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
    if (Date.now() - lastAreaAt.current < 400) return; // «хвост» клика после Ctrl-выделения
    if (!canPick) return;
    void selectByLatLng(lat, lng);
  };

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
      (p) => map?.setView([p.coords.latitude, p.coords.longitude], 14),
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

  const hint = parcel
    ? pl.map.hintSelected
    : region === null && regions
      ? pl.map.hintRegion
      : pl.map.hintParcel;

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
