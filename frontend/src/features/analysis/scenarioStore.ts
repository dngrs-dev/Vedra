import { create } from 'zustand';
import type { Levers } from '@/types/scenario';
import { storageGet, storageSet } from '@/utils/storage';

export const NO_ACTION: Levers = {
  retention_mm: 0, organic_matter_pct: 0, cover_pct: 0, irrigation_limit_mm: 0, irrigation_dose_mm: 25
};
// Ten sam klucz co dawniej («pokaż symulację»): zapisany wybór użytkownika dalej działa - teraz tylko dla PDF
const PDF_KEY = 'vedra.showScenarios';

interface ScenarioState {
  /** Положение суwaków для каждого анализа - общее для страницы raportu и PDF */
  levers: Record<string, Levers>;
  /** Pole wyboru «Dołącz „Co jeśli?” do PDF» obok «Pobierz PDF»; na ekranie symulacja to rozwijany blok */
  includeInPdf: boolean;
  setLevers: (analysisId: string, levers: Levers) => void;
  setIncludeInPdf: (include: boolean) => void;
}

export const useScenarioStore = create<ScenarioState>((set) => ({
  levers: {},
  includeInPdf: storageGet(PDF_KEY) !== '0',
  setLevers: (analysisId, levers) => set((s) => ({ levers: { ...s.levers, [analysisId]: levers } })),
  setIncludeInPdf: (includeInPdf) => {
    storageSet(PDF_KEY, includeInPdf ? '1' : '0');
    set({ includeInPdf });
  }
}));
