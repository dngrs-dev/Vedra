import { create } from 'zustand';
import { DEFAULT_CROP_IDS } from '@/constants/crops';
import type { Parcel } from '@/types/parcel';
import { toISODate } from '@/utils/format';

/** Режим рамки Ctrl + ЛКМ: простой прямоугольник или поиск всех делянок в рамке */
export type SelectMode = 'simple' | 'smart';

interface AnalysisState {
  /** Выбранная (ещё не подтверждённая) делянка — подсвечена на карте */
  parcel: Parcel | null;
  /** Подтверждённая делянка — только для неё запускается расчёт на бэкенде */
  confirmed: Parcel | null;
  /** Активное воеводство (на него приближена карта) */
  region: string | null;
  selectMode: SelectMode;
  cropIds: string[];
  /** YYYY-MM-DD */
  date: string;
  setParcel: (p: Parcel | null) => void;
  confirm: () => void;
  unconfirm: () => void;
  setRegion: (r: string | null) => void;
  toggleCrop: (id: string) => void;
  setDate: (d: string) => void;
  setSelectMode: (m: SelectMode) => void;
}

/**
 * Состояние «что анализируем»: выбранная делянка → подтверждённая делянка + культуры + дата.
 * Результат расчёта живёт в React Query (см. hooks/useAnalysis).
 */
export const useAnalysisStore = create<AnalysisState>((set) => ({
  parcel: null,
  confirmed: null,
  region: null,
  selectMode: 'smart',
  cropIds: DEFAULT_CROP_IDS,
  date: toISODate(new Date()),
  // новый выбор сбрасывает подтверждение: расчёт нужно запустить заново кнопкой
  setParcel: (parcel) => set({ parcel, confirmed: null }),
  confirm: () => set((s) => (s.parcel ? { confirmed: s.parcel } : s)),
  unconfirm: () => set({ confirmed: null }),
  setRegion: (region) => set({ region }),
  toggleCrop: (id) =>
    set((s) => {
      const has = s.cropIds.includes(id);
      if (has && s.cropIds.length === 1) return s; // минимум одна культура
      return { cropIds: has ? s.cropIds.filter((c) => c !== id) : [...s.cropIds, id] };
    }),
  setDate: (date) => set({ date }),
  setSelectMode: (selectMode) => set({ selectMode })
}));
