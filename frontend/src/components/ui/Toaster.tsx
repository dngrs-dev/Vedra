import { useToastStore } from './toastStore';

export function Toaster() {
  const message = useToastStore((s) => s.message);
  const kind = useToastStore((s) => s.kind);
  if (!message) return null;
  return (
    <div className={`toast${kind === 'error' ? ' is-error' : ''}`} role="status" aria-live="polite">
      {message}
    </div>
  );
}
