import { useRef, type CSSProperties } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRightIcon, CalendarIcon, DropIcon, FileIcon, KowrLogo, PinIcon, ShieldIcon, SproutIcon
} from '@/components/ui/Icons';
import { pl } from '@/constants/pl';
import { useReveal } from '@/components/landing/useReveal';

/** Задержка анимации для «лесенки» элементов */
const delay = (i: number) => ({ '--d': `${i * 90}ms` }) as CSSProperties;

const STEPS = [
  { icon: <PinIcon />, title: 'Wskaż działkę', text: 'Wybierz województwo na mapie, a potem kliknij działkę albo zaznacz własny obszar.' },
  { icon: <SproutIcon />, title: 'Wybierz uprawę', text: 'Powiedz, co rośnie na polu i na jaki dzień ma być analiza - dziś lub z ostatnich 10 lat.' },
  { icon: <FileIcon />, title: 'Odbierz zalecenia', text: 'Dostajesz prostą ocenę suszy, zalecenia i gotowy raport do wydruku lub zapisu w PDF.' }
];

const BENEFITS = [
  { icon: <DropIcon size={26} />, title: 'Ocena wilgotności i suszy', text: 'Aktualny stan gleby i ryzyko suszy na tle ostatnich 10 lat.' },
  { icon: <ShieldIcon size={26} />, title: 'Retencja wody', text: 'Co zrobić, żeby woda została na polu: międzyplony, resztki, spowolnienie odpływu.' },
  { icon: <CalendarIcon size={26} />, title: 'Termin nawadniania', text: 'Czy nawadniać i kiedy - jasno i bez zbędnej statystyki.' },
  { icon: <FileIcon size={26} />, title: 'Uczciwy raport', text: 'Źródła, daty i ograniczenia. Gdy brakuje danych, mówimy to wprost.' }
];

const SOURCES = ['Sentinel-2', 'IMGW-PIB', 'Open-Meteo', 'IUNG-PIB', 'GUGiK / Geoportal', 'Wody Polskie'];

/** Главная «/» - короткий лендинг: hero на фото поля, 3 шага, польза, источники, CTA → /map. */
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
          <a href="#benefits">Co dostajesz</a>
          <a href="#data">Dane</a>
        </nav>
        <Link to="/map" className="btn-primary">Zobacz mapę</Link>
      </header>

      {/* Фото поля - фон hero (public/images/hero-field.jpg) */}
      <section className="l-hero">
        <div className="l-hero__text">
          <h2 className="l-hero__title anim-in" style={delay(1)}>Zatrzymaj wodę,<br />chroń swoje plony</h2>
          <p className="l-hero__lead anim-in" style={delay(2)}>
            Wskaż działkę, a my zamienimy dane satelitarne i pogodowe w jasne decyzje:
            czy grozi susza, jak zatrzymać wodę na polu i kiedy warto nawadniać.
          </p>
          <div className="l-hero__cta anim-in" style={delay(3)}>
            <Link to="/map" className="btn-primary btn-lg">Zobacz mapę <ArrowRightIcon /></Link>
            <a href="#how" className="btn-ghost btn-lg">Jak to działa</a>
          </div>
          <ul className="l-stats anim-in" style={delay(4)}>
            <li><b>10 lat</b><span>danych historycznych</span></li>
            <li><b>Cała Polska</b><span>dowolna działka</span></li>
            <li><b>PDF</b><span>raport do wydruku</span></li>
          </ul>
        </div>
      </section>

      <section className="l-section" id="how">
        <h2 className="l-h2" data-reveal>Trzy kroki do decyzji o wodzie</h2>
        <p className="l-sub" data-reveal>Bez map GIS, bez tabel i specjalistycznej wiedzy.</p>
        <ol className="l-steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="l-step" data-reveal style={delay(i + 1)}>
              <span className="l-step__num">{i + 1}</span>
              <span className="l-step__icon">{s.icon}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="l-section l-section--tint" id="benefits">
        <h2 className="l-h2" data-reveal>Co dostajesz</h2>
        <div className="l-benefits">
          {BENEFITS.map((b, i) => (
            <article key={b.title} className="l-benefit" data-reveal style={delay(i)}>
              <span className="l-benefit__icon">{b.icon}</span>
              <div>
                <h3>{b.title}</h3>
                <p>{b.text}</p>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section className="l-section" id="data">
        <h2 className="l-h2" data-reveal>Oparte na otwartych danych</h2>
        <p className="l-sub" data-reveal>Łączymy dane z oficjalnych, publicznych źródeł.</p>
        <ul className="l-sources">
          {SOURCES.map((s, i) => <li key={s} data-reveal style={delay(i)}>{s}</li>)}
        </ul>
      </section>

      <section className="l-cta" data-reveal>
        <h2>Sprawdź swoją działkę w minutę</h2>
        <Link to="/map" className="btn-light btn-lg">Zobacz mapę <ArrowRightIcon /></Link>
      </section>

      <footer className="l-foot">
        <span>{pl.appTitle} · {pl.appSubtitle}</span>
        <span className="muted">Wyniki mają charakter pomocniczy i nie zastępują oceny agronomicznej.</span>
      </footer>
    </div>
  );
}
