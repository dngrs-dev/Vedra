import { useEffect, useState } from 'react';
import { pl } from '@/constants/pl';
import { CheckIcon } from '@/components/ui/Icons';
import { Card } from '@/components/ui/Card';

// The existing timer animates demo jobs. Real jobs show only reported progress.
export function AnalysisProgress({ progress }: { progress?: string[] }) {
  const [auto, setAuto] = useState(0);

  useEffect(() => {
    if (progress !== undefined) return;
    const id = setInterval(() => setAuto((s) => Math.min(s + 1, pl.steps.length - 1)), 650);
    return () => clearInterval(id);
  }, [progress]);

  const labels = progress ? (progress.length ? progress : [pl.backend.preparing]) : pl.steps;
  const current = progress ? labels.length - 1 : auto;

  return (
    <Card title="Analizuję działkę…" className="progress">
      <ol className="progress__list" aria-live="polite">
        {labels.map((label, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={label} className={done ? 'is-done' : active ? 'is-active' : ''}>
              <span className="progress__mark">{done ? <CheckIcon size={14} /> : active ? <span className="spinner spinner--sm" /> : null}</span>
              {label}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
