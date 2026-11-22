import { useEffect, useState } from 'react';
import { pl } from '@/constants/pl';
import { CheckIcon } from '@/components/ui/Icons';
import { Card } from '@/components/ui/Card';

// The existing timer animates demo jobs. Real jobs show only reported progress.
export function AnalysisProgress({ progress, compact = false }: { progress?: string[]; compact?: boolean }) {
  const [auto, setAuto] = useState(0);
  const steps = compact ? pl.panel.loadingSteps : pl.steps;

  useEffect(() => {
    if (progress !== undefined) return;
    const id = setInterval(() => setAuto((s) => Math.min(s + 1, steps.length - 1)), 650);
    return () => clearInterval(id);
  }, [progress, steps]);

  const labels = compact || !progress ? steps : progress.length ? progress : [pl.backend.preparing];
  const current = progress ? Math.max(0, Math.min(progress.length, labels.length) - 1) : auto;

  return (
    <Card title={pl.panel.loading} className="progress">
      <ol className="progress__list" aria-live="polite">
        {labels.map((label, i) => {
          const done = i < current;
          const active = i === current;
          return (
            <li key={label} className={done ? 'is-done' : active ? 'is-active' : ''} aria-current={active ? 'step' : undefined}>
              <span className="progress__mark" aria-hidden="true">{done ? <CheckIcon size={14} /> : active ? <span className="spinner spinner--sm" /> : i + 1}</span>
              {label}
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
