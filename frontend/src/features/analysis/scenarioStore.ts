import { create } from 'zustand';
import type { Levers } from '@/types/scenario';
import { storageGet, storageSet } from '@/utils/storage';

export const NO_ACTION: Levers = {
  retention_mm: 0, organic_matter_pct: 0, cover_pct: 0, irrigation_limit_mm: 0, irrigation_dose_mm: 25
};
const SHOW_KEY = 'vedra.showScenarios';

interface ScenarioState {
  /** Положение суwaków для каждого анализа - общее для карты, страницы raportu и PDF */
  levers: Record<string, Levers>;
  /** Галочка «Co jeśli?»: показывать симуляцию под картой, на странице raportu и в PDF */
  showScenarios: boolean;
  setLevers: (analysisId: string, levers: Levers) => void;
  setShowScenarios: (show: boolean) => void;
}

export const useScenarioStore = create<ScenarioState>((set) => ({
  levers: {},
  showScenarios: storageGet(SHOW_KEY) !== '0',
  setLevers: (analysisId, levers) => set((s) => ({ levers: { ...s.levers, [analysisId]: levers } })),
  setShowScenarios: (showScenarios) => {
    storageSet(SHOW_KEY, showScenarios ? '1' : '0');
    set({ showScenarios });
  }
}));
