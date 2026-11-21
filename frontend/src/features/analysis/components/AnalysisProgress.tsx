import { useEffect, useState } from 'react';
import { pl } from '@/constants/pl';
import { CheckIcon } from '@/components/ui/Icons';
import { Card } from '@/components/ui/Card';

/**
 * Пошаговый индикатор: расчёт может занимать до ~30 с, поэтому показываем этапы, а не один спиннер.
 * Сейчас шаги переключаются по таймеру. Когда бэкенд начнёт отдавать прогресс (SSE/polling),
 * достаточно передать реальный `step` пропсом.
 */
export function AnalysisProgress({ step }: { step?: number }) {
  const [auto, setAuto] = useState(0);

  useEffect(() => {
    if (step !== undefined) return;
    const id = setInterval(() => setAuto((s) => Math.min(s + 1, pl.steps.length - 1)), 650);
    return () => clearInterval(id);
  }, [step]);

  const current = step ?? auto;

  return (
    <Card title="Analizuję działkę…" className="progress">
      <ol className="progress__list" aria-live="polite">
        {pl.steps.map((label, i) => {
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
