export type LatLng = [lat: number, lng: number];

export interface Parcel {
  /** Идентификатор эвиденции (напр. 141201_1.0001.6509) либо OBSZAR_lat_lng для самостоятельно выделенной области */
  id: string;
  /** Контур участка (lat, lng) */
  ring: LatLng[];
  areaHa: number;
  center: { lat: number; lng: number };
  /** true, если контур не получен из ULDK и показан приблизительно (демо) */
  isDemo?: boolean;
  /** true, если область выделена пользователем вручную (Ctrl + перетаскивание) */
  isCustom?: boolean;
}
