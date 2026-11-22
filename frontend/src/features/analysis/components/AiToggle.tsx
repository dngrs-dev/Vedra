import { useAiStore } from '../aiStore';
import { useAiStatus } from '../hooks/useAiStatus';

/** Переключатель «Analiza AI» в правой панели (до запуска анализа). */
export function AiToggle() {
  const enabled = useAiStore((s) => s.enabled);
  const setEnabled = useAiStore((s) => s.setEnabled);
  const consentFor = useAiStore((s) => s.consentFor);
  const withdrawConsent = useAiStore((s) => s.withdrawConsent);
  const { data: status } = useAiStatus();
  const consented = status?.external && consentFor === status.provider;

  return (
    <div className="field ai-toggle">
      <label className="switch">
        <input type="checkbox" role="switch" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
        <span className="switch__track" aria-hidden="true"><span className="switch__thumb" /></span>
        <span className="switch__text">
          <b>Analiza AI</b>
          <small>
            {enabled
              ? 'Model językowy opisze wyniki prostym językiem. Obliczenia zawsze wykonuje aplikacja.'
              : 'Wyłączona - zobaczysz tylko wyniki obliczeń, bez komentarza AI.'}
          </small>
        </span>
      </label>
      {consented && (
        <p className="ai-toggle__consent">
          Zgoda na przekazanie danych do {status.provider_name}: udzielona ·{' '}
          <button type="button" className="link-btn" onClick={withdrawConsent}>Wycofaj zgodę</button>
        </p>
      )}
    </div>
  );
}
