import { useEffect } from 'react';
import L, { type LatLngTuple, type Map as LeafletMap } from 'leaflet';
import { MapContainer, Polygon, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet';
import { POLAND_BOUNDS, POLAND_OUTLINE, WORLD_RING } from '@/constants/poland';
import type { LatLng, Parcel } from '@/types/parcel';
import type { Voivodeship } from '@/types/region';
import { dzialki } from '@/utils/format';
import { AreaSelect } from './AreaSelect';
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
    map.fitBounds(pts as LatLngTuple[], { maxZoom: 17, padding: [60, 60] });
  }, [map, parcel]);
  return null;
}

export function PolandMap({
  parcel, layer, showParcels, regions, activeRegion, onRegionSelect, onPick, onArea, onReady
}: PolandMapProps) {
  const tiles = TILES[layer];

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

      {/* групповой выбор: один общий (объединённый) контур + подпись в центре */}
      {showParcels && parcel?.parts && (
        <Polygon
          positions={parcel.outline ?? parcel.parts.map((p) => [p.ring])}
          pathOptions={{ color: '#ffffff', weight: 3, fillColor: '#4fa183', fillOpacity: 0.45, interactive: false }}
        >
          <Tooltip permanent direction="center" className="parcel-label">
            {dzialki(parcel.parts.length)} · {parcel.areaHa} ha
          </Tooltip>
        </Polygon>
      )}

      {showParcels && parcel && !parcel.parts && (
        <Polygon
          positions={parcel.ring}
          pathOptions={{
            color: parcel.isCustom ? '#ffe27a' : '#ffffff',
            weight: 2.5,
            fillColor: parcel.isCustom ? '#ffe27a' : '#4fa183',
            fillOpacity: 0.4,
            interactive: false
          }}
        >
          <Tooltip permanent direction="center" className="parcel-label">
            {parcel.isCustom ? `Własny obszar · ${parcel.areaHa} ha` : parcel.id}
          </Tooltip>
        </Polygon>
      )}

      <ClickHandler onPick={onPick} />
      <AreaSelect onSelect={onArea} />
      <FitParcel parcel={parcel} />
    </MapContainer>
  );
}
