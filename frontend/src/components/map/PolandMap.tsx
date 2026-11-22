import { useEffect } from 'react';
import L, { type LatLngTuple, type Map as LeafletMap } from 'leaflet';
import { MapContainer, Pane, Polygon, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { PANE_BOUNDARIES, PANE_SELECTED, PICK_MIN_ZOOM, boundaryWeight } from '@/constants/map';
import { POLAND_BOUNDS, POLAND_OUTLINE, WORLD_RING } from '@/constants/poland';
import type { BoundaryFeature } from '@/services/parcelApi';
import type { LatLng, Parcel } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { dzialki } from '@/utils/format';
import { AreaSelect } from './AreaSelect';
import { ParcelBoundaries } from './ParcelBoundaries';
import { RegionLayer } from './RegionLayer';

export type BaseLayer = 'satellite' | 'terrain';

const TILES: Record<BaseLayer, { url: string; attribution: string; maxZoom: number }> = {
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics',
    maxZoom: 19
  },
  terrain: {
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors, SRTM | © OpenTopoMap (CC-BY-SA)',
    maxZoom: 17
  }
};

/** Карта «заперта» в границах Польши (+5% запаса). */
const MAX_BOUNDS = L.latLngBounds(POLAND_BOUNDS).pad(0.05);

interface PolandMapProps {
  parcel: Parcel | null;
  layer: BaseLayer;
  showParcels: boolean;
  regions: Voivodeship[] | undefined;
  activeRegion: string | null;
  onRegionSelect: (v: Voivodeship) => void;
  onPick: (lat: number, lng: number) => void;
  onArea: (ring: LatLng[]) => void;
  onReady: (map: LeafletMap | null) => void;
  /** Текущий зум карты (толщина линий выбранной делянки) */
  zoom: number;
  /** Контуры всех делянок вокруг видимой области; null — слой границ скрыт (мелкий зум) */
  boundaries: BoundaryFeature[] | null;
  /** Делянка, по которой только что кликнули (запрос ещё идёт) */
  pendingId: string | null;
  onBoundaryClick: (id: string) => void;
}

function ClickHandler({ onPick }: { onPick: PolandMapProps['onPick'] }) {
  useMapEvents({ click: (e) => onPick(e.latlng.lat, e.latlng.lng) });
  return null;
}

function FitParcel({ parcel }: { parcel: Parcel | null }) {
  const map = useMap();
  useEffect(() => {
    if (!parcel || parcel.isCustom) return; // свою область не «перепрыгиваем» — пользователь её только что нарисовал
    const pts = parcel.outline ? parcel.outline.flatMap((poly) => poly[0] ?? []) : parcel.parts ? parcel.parts.flatMap((p) => p.ring) : parcel.ring;
    const bounds = L.latLngBounds(pts as LatLngTuple[]);
    // делянку выбрали кликом на крупном зуме и она целиком видна — карту не дёргаем (раньше отдаляло до 17)
    if (map.getZoom() >= PICK_MIN_ZOOM && map.getBounds().contains(bounds)) return;
    map.fitBounds(bounds, { maxZoom: 17, padding: [60, 60] });
  }, [map, parcel]);
  return null;
}

export function PolandMap({
  parcel, layer, showParcels, regions, activeRegion, onRegionSelect, onPick, onArea, onReady,
  zoom, boundaries, pendingId, onBoundaryClick
}: PolandMapProps) {
  const tiles = TILES[layer];
  // выбранная делянка заметно толще сетки границ
  const selectedWeight = zoom >= PICK_MIN_ZOOM ? boundaryWeight(zoom) + 1.6 : 2.5;

  // Маска «всё кроме Польши»: внешнее кольцо = мир, «дыры» = внешние контуры воеводств.
  // Пока границы не загрузились — упрощённый контур страны.
  const maskPositions: LatLng[][] = regions?.length
    ? [WORLD_RING, ...regions.flatMap((v) => v.polygons.map((p) => p[0]!).filter(Boolean))]
    : [WORLD_RING, POLAND_OUTLINE];

  return (
    <MapContainer
      ref={onReady}
      className="map"
      bounds={POLAND_BOUNDS}
      minZoom={6}
      maxBounds={MAX_BOUNDS}
      maxBoundsViscosity={1}
      zoomControl={false}
    >
      <TileLayer key={layer} url={tiles.url} attribution={tiles.attribution} maxZoom={tiles.maxZoom} />

      <Polygon
        positions={maskPositions}
        pathOptions={{ stroke: false, fillColor: '#0f2620', fillOpacity: 0.72, interactive: false }}
      />

      {regions && <RegionLayer regions={regions} active={activeRegion} onSelect={onRegionSelect} />}

      {showParcels && boundaries && (
        <Pane name={PANE_BOUNDARIES} style={{ zIndex: '420' }}>
          <ParcelBoundaries
            features={boundaries}
            selectedId={parcel && !parcel.parts && !parcel.isCustom ? parcel.id : null}
            pendingId={pendingId}
            onFeatureClick={onBoundaryClick}
          />
        </Pane>
      )}

      {/* выбранная делянка — над сеткой границ; панель «прозрачна» для мыши, чтобы не перекрывать canvas границ */}
      <Pane name={PANE_SELECTED} style={{ zIndex: '430', pointerEvents: 'none' }}>
        {/* key: при смене делянки полигон и постоянная подпись создаются заново — подпись встаёт в центр НОВОЙ
            делянки (react-leaflet только меняет координаты полигона, а тултип остаётся на старом месте) */}
        {/* групповой выбор: один общий (объединённый) контур + подпись в центре */}
        {showParcels && parcel?.parts && (
          <Polygon
            key={parcel.id}
            positions={parcel.outline ?? parcel.parts.map((p) => [p.ring])}
            pathOptions={{ color: '#ffffff', weight: selectedWeight + 0.5, fillColor: '#4fa183', fillOpacity: 0.5, interactive: false }}
          >
            <Tooltip permanent direction="center" className="parcel-label">
              {dzialki(parcel.parts.length)} · {parcel.areaHa} ha
            </Tooltip>
          </Polygon>
        )}

        {showParcels && parcel && !parcel.parts && (
          <Polygon
            key={parcel.id}
            positions={parcel.outline ?? parcel.ring}
            pathOptions={{
              color: parcel.isCustom ? '#ffe27a' : '#ffffff',
              weight: selectedWeight,
              fillColor: parcel.isCustom ? '#ffe27a' : '#4fa183',
              fillOpacity: parcel.isCustom ? 0.4 : 0.5,
              interactive: false
            }}
          >
            <Tooltip permanent direction="center" className="parcel-label">
              {parcel.isCustom ? `Własny obszar · ${parcel.areaHa} ha` : parcel.id}
            </Tooltip>
          </Polygon>
        )}
      </Pane>

      <ClickHandler onPick={onPick} />
      <AreaSelect onSelect={onArea} />
      <FitParcel parcel={parcel} />
    </MapContainer>
  );
}
