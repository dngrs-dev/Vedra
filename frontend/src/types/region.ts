import type { LatLng } from './parcel';

/** Воеводство: один или несколько полигонов (MultiPolygon), каждый — набор колец (внешнее + дыры). */
export interface Voivodeship {
  id: string;
  /** Например: "Podkarpackie" */
  name: string;
  polygons: LatLng[][][];
  /** [юго-запад, северо-восток] */
  bounds: [LatLng, LatLng];
  /** Точка для подписи (центроид крупнейшего полигона) */
  labelPoint: LatLng;
}
