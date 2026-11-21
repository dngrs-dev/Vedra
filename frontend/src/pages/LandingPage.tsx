import { Link } from 'react-router-dom';
import { HeroArt } from '@/components/landing/HeroArt';
import {
  ArrowRightIcon, CalendarIcon, DropIcon, FileIcon, KowrLogo, PinIcon, ShieldIcon, SproutIcon
} from '@/components/ui/Icons';
import { pl } from '@/constants/pl';

const STEPS = [
  { icon: <PinIcon />, title: 'Wskaż działkę', text: 'Wybierz województwo na mapie, a potem kliknij działkę albo zaznacz własny obszar.' },
  { icon: <SproutIcon />, title: 'Wybierz uprawę', text: 'Powiedz, co rośnie na polu i na jaki dzień ma być analiza — dziś lub z ostatnich 10 lat.' },
  { icon: <FileIcon />, title: 'Odbierz zalecenia', text: 'Dostajesz prostą ocenę suszy, zalecenia i gotowy raport do wydruku lub zapisu w PDF.' }
];

const BENEFITS = [
  { icon: <DropIcon size={26} />, title: 'Ocena wilgotności i suszy', text: 'Aktualny stan gleby i ryzyko suszy na tle ostatnich 10 lat.' },
  { icon: <ShieldIcon size={26} />, title: 'Retencja wody', text: 'Co zrobić, żeby woda została na polu: międzyplony, resztki, spowolnienie odpływu.' },
  { icon: <CalendarIcon size={26} />, title: 'Termin nawadniania', text: 'Czy nawadniać i kiedy — jasno i bez zbędnej statystyki.' },
  { icon: <FileIcon size={26} />, title: 'Uczciwy raport', text: 'Źródła, daty i ograniczenia. Gdy brakuje danych, mówimy to wprost.' }
];

const SOURCES = ['Sentinel-2', 'IMGW-PIB', 'Open-Meteo', 'IUNG-PIB', 'GUGiK / Geoportal', 'Wody Polskie'];

/** Главная «/» — короткий лендинг: hero, 3 шага, польза, источники, CTA → /map. */
export function LandingPage() {
  return (
    <div className="landing">
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

      <section className="l-hero">
        <div className="l-hero__text">
          <span className="l-pill">Zadanie KOWR · HackNation 2026</span>
          <h2 className="l-hero__title">Zatrzymaj wodę,<br />chroń swoje plony</h2>
          <p className="l-hero__lead">
            Wskaż działkę, a my zamienimy dane satelitarne i pogodowe w jasne decyzje:
            czy grozi susza, jak zatrzymać wodę na polu i kiedy warto nawadniać.
          </p>
          <div className="l-hero__cta">
            <Link to="/map" className="btn-primary btn-lg">Zobacz mapę <ArrowRightIcon /></Link>
            <a href="#how" className="btn-ghost btn-lg">Jak to działa</a>
          </div>
          <ul className="l-stats">
            <li><b>10 lat</b><span>danych historycznych</span></li>
            <li><b>Cała Polska</b><span>dowolna działka</span></li>
            <li><b>PDF</b><span>raport do wydruku</span></li>
          </ul>
        </div>
        <div className="l-hero__art"><HeroArt /></div>
      </section>

      <section className="l-section" id="how">
        <h2 className="l-h2">Trzy kroki do decyzji o wodzie</h2>
        <p className="l-sub">Bez map GIS, bez tabel i specjalistycznej wiedzy.</p>
        <ol className="l-steps">
          {STEPS.map((s, i) => (
            <li key={s.title} className="l-step">
              <span className="l-step__num">{i + 1}</span>
              <span className="l-step__icon">{s.icon}</span>
              <h3>{s.title}</h3>
              <p>{s.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="l-section l-section--tint" id="benefits">
        <h2 className="l-h2">Co dostajesz</h2>
        <div className="l-benefits">
          {BENEFITS.map((b) => (
            <article key={b.title} className="l-benefit">
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
        <h2 className="l-h2">Oparte na otwartych danych</h2>
        <p className="l-sub">Łączymy dane z oficjalnych, publicznych źródeł.</p>
        <ul className="l-sources">
          {SOURCES.map((s) => <li key={s}>{s}</li>)}
        </ul>
      </section>

      <section className="l-cta">
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
