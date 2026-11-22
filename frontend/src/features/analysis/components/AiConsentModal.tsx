import { useEffect, useState } from 'react';
import type { AiStatus } from '@/types/scenario';

const TERMS: Record<AiStatus['provider'], string> = {
  gemini: 'https://ai.google.dev/gemini-api/terms',
  anthropic: 'https://www.anthropic.com/legal/commercial-terms'
};

/**
 * Informacja i zgoda RODO przed wysłaniem danych analizy do zewnętrznej usługi AI.
 * Без согласия бэкенд тоже не отправит данные (routes_scenarios.py → 403).
 */
export function AiConsentModal({ status, onAccept, onCancel }: {
  status: AiStatus;
  onAccept: () => void;
  onCancel: () => void;
}) {
  const [agreed, setAgreed] = useState(false);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="intro-backdrop" onClick={(e) => e.target === e.currentTarget && onCancel()}>
      <div className="intro consent" role="dialog" aria-modal="true" aria-labelledby="consent-title">
        <h2 id="consent-title" className="intro__title">Zgoda na przekazanie danych do usługi AI</h2>
        <p className="intro__lead">
          Komentarz AI przygotowuje zewnętrzna usługa <b>{status.provider_name}</b> (model {status.model}).
          Aby go otrzymać, aplikacja wyśle tam dane z analizy Twojej działki.
        </p>

        <h3>Jakie dane zostaną przekazane</h3>
        <ul>
          <li>identyfikator i powierzchnia działki ewidencyjnej oraz jej lokalizacja (gmina, powiat, województwo),</li>
          <li>wybrana uprawa i data analizy,</li>
          <li>wyniki oceny suszy, historia z ostatnich lat i wyniki symulacji „co jeśli”.</li>
        </ul>
        <p>Nie przekazujemy imienia, nazwiska, adresu e-mail ani innych danych kontaktowych.</p>

        <h3>Co warto wiedzieć</h3>
        <ul>
          <li>
            Identyfikator działki w połączeniu z ewidencją gruntów może pozwolić ustalić jej właściciela,
            dlatego traktujemy go jak dane osobowe w rozumieniu RODO.
          </li>
          {status.provider === 'gemini' ? (
            <li>
              W bezpłatnym planie Google może wykorzystywać przesłane treści do ulepszania swoich usług,
              a dane mogą być przetwarzane poza Europejskim Obszarem Gospodarczym.
            </li>
          ) : (
            <li>Dane mogą być przetwarzane poza Europejskim Obszarem Gospodarczym zgodnie z warunkami dostawcy.</li>
          )}
          <li>
            Podstawą przekazania jest Twoja zgoda (art. 6 ust. 1 lit. a RODO). Zgoda jest dobrowolna - bez niej
            aplikacja działa w pełni, nie zobaczysz tylko komentarza AI.
          </li>
          <li>
            Zgodę możesz w każdej chwili wycofać w panelu po prawej („Wycofaj zgodę” lub przełącznik „Analiza AI”).
            Wycofanie nie wpływa na zgodność z prawem wcześniejszego przekazania.
          </li>
          <li>
            Warunki usługi:{' '}
            <a href={TERMS[status.provider]} target="_blank" rel="noreferrer">{status.provider_name}</a>.
          </li>
        </ul>

        <label className="intro__remember">
          <input type="checkbox" checked={agreed} onChange={(e) => setAgreed(e.target.checked)} />
          <span>
            Zapoznałem(-am) się z informacją i wyrażam zgodę na przekazanie danych analizy do usługi{' '}
            {status.provider_name} w celu przygotowania komentarza AI.
          </span>
        </label>

        <div className="consent__actions">
          <button type="button" className="btn-secondary" onClick={onCancel}>Anuluj</button>
          <button type="button" className="btn-primary" disabled={!agreed} onClick={onAccept}>
            Wyrażam zgodę i wyślij
          </button>
        </div>
      </div>
    </div>
  );
}
