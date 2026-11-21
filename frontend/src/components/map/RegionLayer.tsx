import { useMemo, useState } from 'react';
import L from 'leaflet';
import { Marker, Polygon, useMap, useMapEvents } from 'react-leaflet';
import type { Voivodeship } from '@/types/region';

interface RegionLayerProps {
  regions: Voivodeship[];
  /** Имя активного воеводства (карта приближена на него) */
  active: string | null;
  onSelect: (v: Voivodeship) => void;
}

/** Подписи исчезают при приближении — тогда они только мешают. */
const LABEL_MAX_ZOOM = 8;

function makeLabel(name: string): L.DivIcon {
  const el = document.createElement('span'); // textContent → никакого HTML-инжекта из данных
  el.textContent = name;
  return L.divIcon({ className: 'region-label', html: el, iconSize: [0, 0] });
}

/** Линии воеводств + подписи. Клик по воеводству приближает карту, подпись этого воеводства скрывается. */
export function RegionLayer({ regions, active, onSelect }: RegionLayerProps) {
  const map = useMap();
  const [zoom, setZoom] = useState(map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });

  const icons = useMemo(() => new Map(regions.map((v) => [v.id, makeLabel(v.name)])), [regions]);
  const showLabels = zoom < LABEL_MAX_ZOOM;

  return (
    <>
      {regions.map((v) => {
        const isActive = v.name === active;
        const dim = active !== null && !isActive;
        const baseOpacity = isActive ? 0 : dim ? 0.38 : 0.06;
        return (
          <Polygon
            key={v.id}
            positions={v.polygons}
            pathOptions={{
              color: isActive ? '#8fd5b9' : '#ffffff',
              weight: isActive ? 2.5 : 1.2,
              fillColor: dim ? '#0f2620' : '#ffffff',
              fillOpacity: baseOpacity
            }}
            eventHandlers={{
              click: (e) => {
                // клик по активному воеводству «пролетает» дальше на карту → выбор делянки
                if (isActive) return;
                L.DomEvent.stopPropagation(e);
                onSelect(v);
              },
              mouseover: (e) => {
                if (!isActive) (e.target as L.Path).setStyle({ fillOpacity: dim ? 0.2 : 0.22 });
              },
              mouseout: (e) => {
                if (!isActive) (e.target as L.Path).setStyle({ fillOpacity: baseOpacity });
              }
            }}
          />
        );
      })}

      {showLabels &&
        regions
          .filter((v) => v.name !== active)
          .map((v) => {
            const icon = icons.get(v.id);
            return icon ? <Marker key={`l-${v.id}`} position={v.labelPoint} icon={icon} interactive={false} keyboard={false} /> : null;
          })}
    </>
  );
}
