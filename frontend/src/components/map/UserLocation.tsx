import L, { type LatLngTuple } from 'leaflet';
import { Circle, Marker, Pane } from 'react-leaflet';
import { PANE_USER_LOCATION } from '@/constants/map';

export interface UserPosition {
  lat: number;
  lng: number;
  /** Точность в метрах (GeolocationCoordinates.accuracy) */
  accuracy: number;
}

const LOCATION_BLUE = '#1a73e8';

/** Синяя точка с белой обводкой и мягкой пульсацией (CSS: .user-location) */
const dotIcon = L.divIcon({
  className: 'user-location',
  html: '<span class="user-location__pulse"></span><span class="user-location__dot"></span>',
  iconSize: [18, 18],
  iconAnchor: [9, 9]
});

/** Местоположение пользователя «как на обычных картах»: точка + полупрозрачный круг точности. */
export function UserLocation({ position }: { position: UserPosition | null }) {
  if (!position) return null;
  const center: LatLngTuple = [position.lat, position.lng];
  return (
    <Pane name={PANE_USER_LOCATION} style={{ zIndex: '440', pointerEvents: 'none' }}>
      <Circle
        center={center}
        radius={position.accuracy}
        pathOptions={{
          color: LOCATION_BLUE,
          weight: 1,
          opacity: 0.35,
          fillColor: LOCATION_BLUE,
          fillOpacity: 0.12,
          interactive: false
        }}
      />
      <Marker position={center} icon={dotIcon} interactive={false} keyboard={false} />
    </Pane>
  );
}
