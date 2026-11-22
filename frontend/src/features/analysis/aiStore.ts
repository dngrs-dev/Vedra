import { create } from 'zustand';
import { storageGet, storageSet } from '@/utils/storage';

const ENABLED_KEY = 'vedra.aiEnabled';
/** Версия текста zgody: при его изменении пользователь должен согласиться заново */
const CONSENT_KEY = 'vedra.aiConsent.v1';

interface AiState {
  /** Переключатель «Analiza AI» в правой панели */
  enabled: boolean;
  /** Поставщик AI (например, "gemini"), на передачу данных которому пользователь согласился (RODO) */
  consentFor: string | null;
  setEnabled: (enabled: boolean) => void;
  grantConsent: (provider: string) => void;
  withdrawConsent: () => void;
}

/** Настройки комментария AI - помнятся между визитами (localStorage). */
export const useAiStore = create<AiState>((set) => ({
  enabled: storageGet(ENABLED_KEY) !== '0',
  consentFor: storageGet(CONSENT_KEY),
  setEnabled: (enabled) => {
    storageSet(ENABLED_KEY, enabled ? '1' : '0');
    set({ enabled });
  },
  grantConsent: (provider) => {
    storageSet(CONSENT_KEY, provider);
    set({ consentFor: provider });
  },
  withdrawConsent: () => {
    storageSet(CONSENT_KEY, null);
    set({ consentFor: null });
  }
}));
