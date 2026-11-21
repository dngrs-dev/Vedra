import { create } from 'zustand';

interface ToastState {
  message: string | null;
  kind: 'info' | 'error';
  show: (message: string, kind?: 'info' | 'error') => void;
  hide: () => void;
}

let timer: ReturnType<typeof setTimeout> | undefined;

export const useToastStore = create<ToastState>((set) => ({
  message: null,
  kind: 'info',
  show: (message, kind = 'info') => {
    clearTimeout(timer);
    set({ message, kind });
    timer = setTimeout(() => set({ message: null }), 4000);
  },
  hide: () => set({ message: null })
}));

/** Короткий хелпер: toast('tekst', 'error') */
export const toast = (message: string, kind: 'info' | 'error' = 'info') =>
  useToastStore.getState().show(message, kind);
