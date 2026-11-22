import L from 'leaflet';
import { GeoJSON, MapContainer, Marker, ZoomControl } from 'react-leaflet';
import { pl } from '@/constants/pl';
import type { BackendGeometry } from '@/types/backendReport';
import type { RecommendationSite } from '../recommendationGroups';

interface Props {
  parcel?: BackendGeometry | null;
  sites: RecommendationSite[];
  selected: number;
  onSelect: (number: number) => void;
}

export default function RecommendationMap({ parcel, sites, selected, onSelect }: Props) {
  const bounds = L.latLngBounds([]);
  if (parcel) bounds.extend(L.geoJSON(parcel).getBounds());
  const locations = sites.map((site) => {
    const siteBounds = L.geoJSON(site.geometry).getBounds();
    bounds.extend(siteBounds);
    return { ...site, position: siteBounds.getCenter() };
  });

  return (
    <div role="group" aria-label={pl.backend.siteMap}>
      <MapContainer className="site-map" bounds={bounds} boundsOptions={{ padding: [24, 24], maxZoom: 17 }}
        zoomSnap={0.25} scrollWheelZoom={false} attributionControl={false} zoomControl={false}>
        <ZoomControl position="topright" zoomInTitle={pl.map.zoomIn} zoomOutTitle={pl.map.zoomOut} />
        {parcel && <GeoJSON data={parcel} style={{ color: '#28776d', weight: 2, fillOpacity: 0.12, interactive: false }} />}
        {locations.map((site) => (
          <GeoJSON key={site.number} data={site.geometry} pointToLayer={(_, latLng) => L.circleMarker(latLng, { radius: 3 })} style={{
            color: '#a35528', weight: 2, fillOpacity: 0.17, interactive: false
          }} />
        ))}
        {locations.map((site) => (
          <Marker key={site.number} position={site.position} zIndexOffset={site.number === selected ? 1000 : 0}
            title={`${pl.backend.site} ${site.number}`} alt={`${pl.backend.site} ${site.number}`}
            icon={L.divIcon({
              className: `site-marker${site.number === selected ? ' site-marker--selected' : ''}`,
              html: String(site.number), iconSize: [24, 24]
            })} eventHandlers={{ click: () => onSelect(site.number) }} />
        ))}
      </MapContainer>
      <p className="muted small">{pl.backend.siteMapLegend}</p>
    </div>
  );
}
