import { useMemo } from 'react';
import { pl } from '@/constants/pl';
import { addYears, toISODate } from '@/utils/format';
import { useAnalysisStore } from '../store';

/** Дата анализа: сегодня или любая дата за последние 10 лет (требование жюри в ТЗ, разд. 6). */
export function DateField() {
  const date = useAnalysisStore((s) => s.date);
  const setDate = useAnalysisStore((s) => s.setDate);
  const { min, max } = useMemo(() => {
    const now = new Date();
    return { min: toISODate(addYears(now, -10)), max: toISODate(now) };
  }, []);

  return (
    <div className="field">
      <label className="field__label" htmlFor="analysisDate">{pl.form.date}</label>
      <input
        id="analysisDate"
        className="input"
        type="date"
        value={date}
        min={min}
        max={max}
        onChange={(e) => e.target.value && setDate(e.target.value)}
        aria-describedby="analysisDateHint"
      />
      <small id="analysisDateHint" className="field__hint">{pl.form.dateHint}</small>
    </div>
  );
}
