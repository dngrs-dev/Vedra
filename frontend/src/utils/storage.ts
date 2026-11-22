/**
 * Безопасная обёртка над localStorage: в приватном режиме / с отключёнными cookies
 * обращение может бросить исключение - тогда просто работаем без запоминания.
 */
export function storageGet(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function storageSet(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* хранилище недоступно - ничего страшного */
  }
}
