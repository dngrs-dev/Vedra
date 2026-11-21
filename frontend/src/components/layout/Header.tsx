import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { KowrLogo } from '@/components/ui/Icons';
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
    </header>
  );
}
