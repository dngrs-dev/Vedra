export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const API_URL = import.meta.env.VITE_API_URL ?? '/api';

/** Тонкая обёртка над fetch: JSON in/out, единый тип ошибки. */
export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...(init.headers ?? {}) }
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e;
    throw new ApiError('Brak połączenia z serwerem');
  }
  if (!res.ok) {
    let msg = `Błąd serwera (${res.status})`;
    try {
      const body = (await res.json()) as { message?: string; detail?: string };
      msg = body.message ?? body.detail ?? msg;
    } catch {
      /* тело не JSON — оставляем общий текст */
    }
    throw new ApiError(msg, res.status);
  }
  return (await res.json()) as T;
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new DOMException('Aborted', 'AbortError'));
    });
  });
}
