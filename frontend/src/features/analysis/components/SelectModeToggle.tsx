import { pl } from '@/constants/pl';
import { useAnalysisStore, type SelectMode } from '../store';

const OPTIONS: { value: SelectMode; label: string; tip: string }[] = [
  { value: 'simple', label: pl.selectMode.simple, tip: pl.selectMode.simpleTip },
  { value: 'smart', label: pl.selectMode.smart, tip: pl.selectMode.smartTip }
];

/** Переключатель режима рамки Ctrl + ЛКМ (в верхней панели на /map). */
export function SelectModeToggle() {
  const mode = useAnalysisStore((s) => s.selectMode);
  const setMode = useAnalysisStore((s) => s.setSelectMode);

  return (
    <div className="mode-toggle" role="radiogroup" aria-label={pl.selectMode.label}>
      {OPTIONS.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={mode === o.value}
          className={mode === o.value ? 'is-active' : ''}
          title={o.tip}
          onClick={() => setMode(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
