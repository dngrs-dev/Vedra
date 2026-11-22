import { pl } from '@/constants/pl';

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export const API_URL = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/+$/, '');

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('Accept', 'application/json');
  if (init.body) headers.set('Content-Type', 'application/json');

  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers });
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new ApiError(pl.error.connection);
  }
  if (!res.ok) throw await responseError(res);
  try {
    return (await res.json()) as T;
  } catch (e) {
    if (init.signal?.aborted) throw e;
    throw new ApiError(pl.error.invalidResponse, res.status);
  }
}

async function responseError(res: Response): Promise<ApiError> {
  let msg = `Błąd serwera (${res.status})`;
  try {
    const body = (await res.json()) as { message?: unknown; detail?: unknown } | null;
    const detail = body?.detail ?? body?.message;
    if (typeof detail === 'string') msg = detail;
  } catch {
    // Proxies may return an HTML error page.
  }
  return new ApiError(msg, res.status);
}

/**
 * Download a file from the API and hand it to the browser as `fallbackName`, or the server's name.
 * Errors are thrown as ApiError, so the page can show them instead of navigating to an error body.
 */
export async function downloadFile(url: string, fallbackName: string): Promise<void> {
  let res: Response;
  try {
    res = await fetch(url);
  } catch {
    throw new ApiError(pl.error.connection);
  }
  if (!res.ok) throw await responseError(res);
  const name = /filename="([^"]+)"/.exec(res.headers.get('Content-Disposition') ?? '')?.[1] ?? fallbackName;
  const href = URL.createObjectURL(await res.blob());
  const link = Object.assign(document.createElement('a'), { href, download: name });
  document.body.append(link);
  link.click();
  link.remove();
  // Let the browser start the download before the object URL is released.
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

export function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal?.throwIfAborted();
    const onAbort = () => {
      clearTimeout(t);
      reject(signal?.reason);
    };
    const t = setTimeout(() => {
      signal?.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    signal?.addEventListener('abort', onAbort, { once: true });
  });
}
