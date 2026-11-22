import { z } from 'zod';

/**
 * Aktualna pogoda w punkcie (Open-Meteo Forecast API, bez klucza, CC BY 4.0).
 * https://open-meteo.com/en/docs - те же данные Open-Meteo, что использует бэкенд.
 */
const URL = 'https://api.open-meteo.com/v1/forecast';

const schema = z.object({
  current: z.object({
    time: z.string(),
    temperature_2m: z.number(),
    relative_humidity_2m: z.number(),
    precipitation: z.number(),
    weather_code: z.number(),
    wind_speed_10m: z.number()
  })
});
export type CurrentWeather = z.infer<typeof schema>['current'];

export async function getCurrentWeather(lat: number, lng: number, signal?: AbortSignal): Promise<CurrentWeather> {
  const params = new URLSearchParams({
    latitude: lat.toFixed(4),
    longitude: lng.toFixed(4),
    current: 'temperature_2m,relative_humidity_2m,precipitation,weather_code,wind_speed_10m',
    timezone: 'Europe/Warsaw'
  });
  const res = await fetch(`${URL}?${params}`, { signal });
  if (!res.ok) throw new Error(`Open-Meteo ${res.status}`);
  return schema.parse(await res.json()).current;
}

/** Kody pogody WMO (Open-Meteo) → opis i ikona */
export type WeatherKind = 'sun' | 'partly' | 'cloud' | 'fog' | 'rain' | 'snow' | 'storm';

export function describeWeather(code: number): { text: string; kind: WeatherKind } {
  if (code === 0) return { text: 'Bezchmurnie', kind: 'sun' };
  if (code === 1) return { text: 'Przeważnie słonecznie', kind: 'partly' };
  if (code === 2) return { text: 'Częściowe zachmurzenie', kind: 'partly' };
  if (code === 3) return { text: 'Pochmurno', kind: 'cloud' };
  if (code === 45 || code === 48) return { text: 'Mgła', kind: 'fog' };
  if (code >= 51 && code <= 57) return { text: 'Mżawka', kind: 'rain' };
  if (code === 66 || code === 67) return { text: 'Marznący deszcz', kind: 'rain' };
  if ((code >= 61 && code <= 65) || (code >= 80 && code <= 82)) return { text: 'Deszcz', kind: 'rain' };
  if ((code >= 71 && code <= 77) || code === 85 || code === 86) return { text: 'Śnieg', kind: 'snow' };
  if (code >= 95) return { text: 'Burza', kind: 'storm' };
  return { text: 'Brak opisu', kind: 'cloud' };
}
