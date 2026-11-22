import { useRef, type CSSProperties, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRightIcon, CalendarIcon, ChevronIcon, DropIcon, FileIcon, HistoryIcon, KowrLogo, LeafIcon, MapIcon, PinIcon,
  SlidersIcon, SparkIcon, SproutIcon
} from '@/components/ui/Icons';
import { pl } from '@/constants/pl';
import {
  FEATURES, HERO_LEAD, HERO_STATS, QUESTIONS, SOURCE_GROUPS, STEPS, type LandingFeature
} from '@/constants/landing';
import { useReveal } from '@/components/landing/useReveal';

/** Задержка анимации для «лесенки» элементов */
const delay = (i: number) => ({ '--d': `${i * 90}ms` }) as CSSProperties;

const STEP_ICONS: ReactNode[] = [<PinIcon key="pin" />, <SproutIcon key="sprout" />, <FileIcon key="file" />];

const FEATURE_ICONS: Record<LandingFeature['icon'], ReactNode> = {
  drop: <DropIcon size={26} />,
  history: <HistoryIcon />,
  pin: <PinIcon size={26} />,
  leaf: <LeafIcon />,
  calendar: <CalendarIcon size={26} />,
  sliders: <SlidersIcon />,
  spark: <SparkIcon />,
  file: <FileIcon size={26} />,
  map: <MapIcon />
};

/**
 * Главная «/»: hero на фото поля, 3 шага, что умеет Vedra, источники данных с пояснениями, вопросы и ответы, CTA → /map.
 * Тексты - в constants/landing.ts (для фермера: просто, без жаргона).
 */
export function LandingPage() {
  const rootRef = useRef<HTMLDivElement>(null);
  useReveal(rootRef);

  return (
    <div className="landing" ref={rootRef}>
      <header className="l-nav">
        <Link to="/" className="brand brand--dark" aria-label="Strona główna">
          <KowrLogo />
          <div className="brand__text">
            <h1>{pl.appTitle}</h1>
            <p>{pl.appSubtitle}</p>
          </div>
        </Link>
        <nav className="l-nav__links" aria-label="Nawigacja">
          <a href="#how">Jak to działa</a>
          <a href="#features">Co potrafi</a>
          <a href="#data">Dane</a>
          <a href="#faq">Pytania</a>
        </nav>
        <Link to="/map" className="btn-primary">Zobacz mapę</Link>
      </header>

      {/* Фото поля - фон hero (public/images/hero-field.jpg) */}
      <section className="l-hero">
        <div className="l-hero__text">
          <h2 className="l-hero__title anim-in" style={delay(1)}>Zatrzymaj wodę,<br />chroń swoje plony</h2>
          <p className="l-hero__lead anim-in" style={delay(2)}>{HERO_LEAD}</p>
          <div className="l-hero__cta anim-in" style={delay(3)}>
            <Link to="/map" className="btn-primary btn-lg">Sprawdź swoją działkę <ArrowRightIcon /></Link>
            <a href="#how" className="btn-ghost btn-lg">Jak to działa</a>
          </div>
          <ul className="l-stats anim-in" style={delay(4)}>
            {HERO_STATS.map((s) => <li key={s.value}><b>{s.value}</b><span>{s.label}</span></li>)}
          </ul>
        </div>
      </section>

      <section className="l-section" id="how">
        <h2 className="l-h2" data-reveal>Trzy kroki do decyzji o wodzie</h2>
        <p className="l-sub" data-reveal>Bez map GIS, tabel i specjalistycznej wiedzy - wystarczy przeglądarka.</p>
        <ol className="l-steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="l-step" data-reveal style={delay(i + 1)}>
              <span className="l-step__num">{i + 1}</span>
              <span className="l-step__icon">{STEP_ICONS[i]}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="l-section l-section--tint" id="features">
        <h2 className="l-h2" data-reveal>Co potrafi Vedra</h2>
        <p className="l-sub" data-reveal>Wszystko, czego dowiesz się o wodzie na swoim polu - na ekranie i w raporcie.</p>
        <div className="l-features">
          {FEATURES.map((f, i) => (
            <article key={f.title} className="l-feature" data-reveal style={delay(i % 3)}>
              <span className="l-feature__icon">{FEATURE_ICONS[f.icon]}</span>
              <h3>{f.title}</h3>
              <p>{f.text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="l-section" id="data">
        <h2 className="l-h2" data-reveal>Skąd bierzemy dane</h2>
        <p className="l-sub" data-reveal>
          Tylko oficjalne, publiczne źródła. Każdy raport podaje, z czego i z jakiego dnia pochodzą dane.
        </p>
        <div className="l-sourcegroups">
          {SOURCE_GROUPS.map((g, i) => (
            <section key={g.title} className="l-sourcegroup" data-reveal style={delay(i % 3)} aria-labelledby={`src-${i}`}>
              <h3 id={`src-${i}`}>{g.title}</h3>
              <ul>
                {g.sources.map((s) => (
                  <li key={s.name}>
                    <a href={s.url} target="_blank" rel="noreferrer">{s.name}<span aria-hidden="true"> ↗</span></a>
                    <p>{s.what}</p>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </section>

      <section className="l-section l-section--tint" id="faq">
        <h2 className="l-h2" data-reveal>Pytania i odpowiedzi</h2>
        <div className="l-faq">
          {QUESTIONS.map((item) => (
            <details key={item.q} className="l-faq__item" data-reveal>
              <summary>
                <span>{item.q}</span>
                <ChevronIcon size={20} />
              </summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="l-cta" data-reveal>
        <h2>Sprawdź swoją działkę - zajmie to minutę</h2>
        <p>Bez rejestracji. Wystarczy wskazać pole na mapie.</p>
        <Link to="/map" className="btn-light btn-lg">Zobacz mapę <ArrowRightIcon /></Link>
      </section>

      <footer className="l-foot">
        <span>{pl.appTitle} · {pl.appSubtitle}</span>
        <span className="muted">Wyniki mają charakter pomocniczy i nie zastępują oceny agronomicznej.</span>
      </footer>
    </div>
  );
}
