export interface Crop {
  id: string;
  name: string;
  en: string;
  /** Относительная потребность в воде 0..1 (используется в демо-расчёте) */
  waterNeed: number;
}

export const CROPS: readonly Crop[] = [
  { id: 'winter-wheat', name: 'Pszenica Ozima', en: 'Winter Wheat', waterNeed: 0.55 },
  { id: 'corn', name: 'Kukurydza', en: 'Corn', waterNeed: 0.8 },
  { id: 'rapeseed', name: 'Rzepak', en: 'Rapeseed', waterNeed: 0.65 },
  { id: 'spring-barley', name: 'Jęczmień Jary', en: 'Spring Barley', waterNeed: 0.5 },
  { id: 'potato', name: 'Ziemniak', en: 'Potato', waterNeed: 0.85 },
  { id: 'sugar-beet', name: 'Burak Cukrowy', en: 'Sugar Beet', waterNeed: 0.75 },
  { id: 'rye', name: 'Żyto', en: 'Rye', waterNeed: 0.4 }
];

export const DEFAULT_CROP_IDS = ['winter-wheat'];
