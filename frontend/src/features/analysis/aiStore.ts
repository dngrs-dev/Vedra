import { create } from 'zustand';
import { storageGet, storageSet } from '@/utils/storage';

/** Версия текста zgody: при его изменении пользователь должен согласиться заново */
const CONSENT_KEY = 'vedra.aiConsent.v1';

interface AiState {
  /** Поставщик AI (например, "gemini"), на передачу данных которому пользователь согласился (RODO) */
  consentFor: string | null;
  grantConsent: (provider: string) => void;
  withdrawConsent: () => void;
}

/**
 * Zgoda na analizę AI - pamiętana między wizytami (localStorage). Osobnego przełącznika AI nie ma:
 * w symulacji „Co jeśli?” zawsze jest «Zapytaj AI», a pytanie wysyła się dopiero po kliknięciu (i zgodzie).
 */
export const useAiStore = create<AiState>((set) => ({
  consentFor: storageGet(CONSENT_KEY),
  grantConsent: (provider) => {
    storageSet(CONSENT_KEY, provider);
    set({ consentFor: provider });
  },
  withdrawConsent: () => {
    storageSet(CONSENT_KEY, null);
    set({ consentFor: null });
  }
}));
