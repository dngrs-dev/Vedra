export type LatLng = [lat: number, lng: number];

/** Одна делянка внутри группового выбора */
export interface ParcelPart {
  id: string;
  ring: LatLng[];
  areaHa: number;
}

export interface Parcel {
  /** Идентификатор эвиденции (напр. 141201_1.0001.6509) либо OBSZAR_lat_lng для самостоятельно выделенной области */
  id: string;
  /** Контур участка (lat, lng) */
  ring: LatLng[];
  areaHa: number;
  center: { lat: number; lng: number };
  /** true, если контур не получен из ULDK и показан приблизительно (демо) */
  isDemo?: boolean;
  /** true, если область выделена пользователем вручную (Ctrl + перетаскивание) и делянок в ней не нашлось */
  isCustom?: boolean;
  /**
   * Групповой выбор: все делянки, найденные в рамке Ctrl + ЛКМ.
   * Для группы `ring` - это сама рамка (обрамление), `areaHa` - сумма площадей делянок.
   */
  parts?: ParcelPart[];
  /**
   * Объединённый контур группы (мультиполигон: [[внешний контур, ...дыры], ...]).
   * Обычно одна часть; несколько - если делянки разделены дорогой/рвом.
   */
  outline?: LatLng[][][];
}
