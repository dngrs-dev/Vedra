import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { BellIcon, KowrLogo, UserIcon } from '@/components/ui/Icons';
import { pl } from '@/constants/pl';

export function Header({ center, actions }: { center?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="topbar">
      <Link to="/" className="brand" aria-label="Strona główna">
        <KowrLogo />
        <div className="brand__text">
          <h1>{pl.appTitle}</h1>
          <p>{pl.appSubtitle}</p>
        </div>
      </Link>
      {center && <div className="topbar__center">{center}</div>}
      <div className="topbar__actions">
        {actions}
        <button type="button" className="icon-btn icon-btn--round" aria-label="Profil użytkownika" title="Profil">
          <UserIcon />
        </button>
        <button type="button" className="icon-btn icon-btn--bell" aria-label="Powiadomienia" title="Powiadomienia">
          <BellIcon />
          <i className="bell-dot" />
        </button>
      </div>
    </header>
  );
}
