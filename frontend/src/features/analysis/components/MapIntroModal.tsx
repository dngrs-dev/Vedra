import { useEffect, useRef, useState } from 'react';

interface MapIntroModalProps {
  /** remember = true → больше не показывать автоматически при входе на /map */
  onClose: (remember: boolean) => void;
  /** Начальное состояние галочки (true, если пользователь уже просил запомнить) */
  initialRemember?: boolean;
}

/** Иконка мыши с подсвеченной левой кнопкой */
function MouseLeft() {
  return (
    <svg viewBox="0 0 24 32" width="22" height="30" aria-hidden="true">
      <rect x="2" y="2" width="20" height="28" rx="10" fill="#fff" stroke="currentColor" strokeWidth="2" />
      <path d="M12 2v11H2.2A10 10 0 0 1 12 2z" fill="#2f8a64" />
      <path d="M12 2v11M2 13h20" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

const STEPS = [
  {
    title: 'Wybierz województwo',
    text: 'Kliknij województwo na mapie Polski - mapa przybliży się do niego.',
    keys: <MouseLeft />
  },
  {
    title: 'Kliknij działkę',
    text: 'Przybliż mapę (pierwsze kliknięcie przybliża) i kliknij pole - zaznaczymy działkę ewidencyjną. Przełącznik „Granice działek” pokaże granice i numery.',
    keys: <MouseLeft />
  },
  {
    title: 'Albo zaznacz ramką',
    text: 'Przytrzymaj Ctrl (⌘ na Macu), wciśnij lewy przycisk myszy i przeciągnij ramkę. Na górnym pasku: „Zwykły wybór” - sam prostokąt, „Inteligentny wybór” - wszystkie działki w środku.',
    keys: (
      <>
        <kbd>Ctrl</kbd>
        <span className="intro__plus">+</span>
        <MouseLeft />
      </>
    )
  },
  {
    title: 'Potwierdź działkę',
    text: 'W panelu po prawej kliknij „Potwierdź działkę” - wtedy ruszą obliczenia.',
    keys: <span className="intro__btn-demo">Potwierdź</span>
  }
];

/**
 * Окно-инструкция при входе на /map. Карта под ним недоступна, пока пользователь не нажмёт «OK».
 * Закрывается кнопкой OK или клавишей Enter / Esc. Галочка «Zapamiętaj» сохраняется в localStorage этого браузера.
 */
export function MapIntroModal({ onClose, initialRemember = false }: MapIntroModalProps) {
  const okRef = useRef<HTMLButtonElement>(null);
  const [remember, setRemember] = useState(initialRemember);

  useEffect(() => {
    okRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose(remember);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, remember]);

  return (
    <div className="intro-backdrop">
      <div className="intro" role="dialog" aria-modal="true" aria-labelledby="intro-title">
        <h2 id="intro-title" className="intro__title">Jak zaznaczyć działkę</h2>
        <p className="intro__lead">Cztery proste kroki - potem zobaczysz ocenę wody na swoim polu.</p>

        <ol className="intro__steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="intro__step" style={{ animationDelay: `${120 + i * 90}ms` }}>
              <span className="intro__num">{i + 1}</span>
              <div className="intro__body">
                <b>{s.title}</b>
                <p>{s.text}</p>
              </div>
              <span className="intro__keys">{s.keys}</span>
            </li>
          ))}
        </ol>

        <label className="intro__remember">
          <input type="checkbox" checked={remember} onChange={(e) => setRemember(e.target.checked)} />
          <span>Zapamiętaj mój wybór - nie pokazuj tego okna przy następnym wejściu</span>
        </label>

        <button ref={okRef} type="button" className="btn-primary btn-block intro__ok" onClick={() => onClose(remember)}>
          OK, rozumiem
        </button>
      </div>
    </div>
  );
}
