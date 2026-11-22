import { useQuery } from '@tanstack/react-query';
import { describeWeather, getCurrentWeather, type WeatherKind } from '@/services/weatherApi';
import { useAnalysis } from '../hooks/useAnalysis';
import { useAnalysisStore } from '../store';

// Обновляем раз в 15 минут - с такой частотой Open-Meteo обновляет текущие данные.
const REFRESH_MS = 15 * 60 * 1000;
const num = new Intl.NumberFormat('pl-PL', { maximumFractionDigits: 1 });

function WeatherIcon({ kind }: { kind: WeatherKind }) {
  const sun = <circle cx="32" cy="11" r="7" fill="#f4c542" />;
  const cloud = <path d="M12 28h22a7 7 0 0 0 0-14 9 9 0 0 0-17-2A8 8 0 0 0 12 28z" fill="#e8eef3" stroke="#b8c4cd" />;
  const drops = (color: string) => (
    <g stroke={color} strokeWidth="2" strokeLinecap="round"><path d="M17 31l-1.5 3" /><path d="M24 31l-1.5 3" /><path d="M31 31l-1.5 3" /></g>
  );
  return (
    <svg viewBox="0 0 48 36" width="34" height="26" aria-hidden="true">
      {(kind === 'sun' || kind === 'partly') && sun}
      {kind === 'sun' ? (
        <g stroke="#f4c542" strokeWidth="2" strokeLinecap="round"><path d="M32 0v1M43 11h1M20 11h1M40 3l1-1M24 3l-1-1" /></g>
      ) : cloud}
      {kind === 'rain' && drops('#4a90c8')}
      {kind === 'snow' && drops('#9fb3c8')}
      {kind === 'storm' && <path d="M24 28l-3 6h4l-2 5" stroke="#e8a317" strokeWidth="2" fill="none" />}
      {kind === 'fog' && <g stroke="#9aa7a2" strokeWidth="2" strokeLinecap="round"><path d="M10 31h26M14 34h22" /></g>}
    </svg>
  );
}

/**
 * «Pogoda teraz» w prawym panelu: aktualna pogoda w środku wybranej działki + link do tego miejsca w Mapach Google.
 * Bez wybranej działki nic nie pokazuje (wcześniej była to stała stopka na dole ekranu, która zasłaniała interfejs).
 */
export function WeatherCard() {
  const selected = useAnalysisStore((s) => s.confirmed ?? s.parcel);
  const region = useAnalysisStore((s) => s.region);
  const { demo, jobs } = useAnalysis({ active: false });
  const point = selected?.center ?? null;
  const lat = point ? +point.lat.toFixed(4) : null;
  const lng = point ? +point.lng.toFixed(4) : null;
  const weather = useQuery({
    queryKey: ['current-weather', lat, lng],
    queryFn: ({ signal }) => getCurrentWeather(lat!, lng!, signal),
    enabled: lat !== null && lng !== null,
    staleTime: REFRESH_MS,
    refetchInterval: REFRESH_MS,
    retry: 1
  });

  if (lat === null || lng === null) return null;

  // Miejsce: gmina i województwo z raportu, inaczej region analizy demo albo województwo na mapie
  const parcel = jobs.find((job) => job.report)?.report?.parcel;
  const place = parcel
    ? [...new Set([parcel.commune, parcel.voivodeship].filter(Boolean))].join(', ')
    : demo.data?.region || region;
  const label = place || `${lat.toFixed(3)}° N, ${lng.toFixed(3)}° E`;
  const maps = `https://www.google.com/maps/search/?api=1&query=${lat},${lng}`;
  const current = weather.data;
  const info = current ? describeWeather(current.weather_code) : null;
  const time = current?.time.slice(11, 16);

  return (
    <section className="card weather-card" aria-label="Aktualna pogoda na działce">
      <WeatherIcon kind={info?.kind ?? 'cloud'} />
      <div className="weather-card__text">
        <div className="weather-card__title">Pogoda teraz</div>
        <a className="weather-card__place" href={maps} target="_blank" rel="noreferrer"
          title="Otwórz lokalizację działki w Mapach Google">
          {label} <span aria-hidden="true">↗</span>
        </a>
        {current && info ? (
          <>
            <div className="weather-card__now">
              <b>{num.format(current.temperature_2m)}°C</b> · {info.text} · wiatr {num.format(current.wind_speed_10m)} km/h
              {' '}· opad {num.format(current.precipitation)} mm
            </div>
            <div className="weather-card__small">Stan na {time} · Open-Meteo</div>
          </>
        ) : (
          <div className="weather-card__small">
            {weather.isError ? 'Nie udało się pobrać aktualnej pogody.' : 'Pobieram aktualną pogodę…'}
          </div>
        )}
      </div>
    </section>
  );
}
