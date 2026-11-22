import type { ReactNode } from 'react';
import { Header } from './Header';

interface AppShellProps {
  children: ReactNode;
  /** Элементы в центре верхней панели (например, переключатель режима выбора) */
  headerCenter?: ReactNode;
  /** Дополнительные кнопки справа в верхней панели (перед иконкой профиля) */
  headerActions?: ReactNode;
}

export function AppShell({ children, headerCenter, headerActions }: AppShellProps) {
  return (
    <div className="app">
      <Header center={headerCenter} actions={headerActions} />
      <main className="main">{children}</main>
    </div>
  );
}
