import { Card } from '@/components/ui/Card';
import { pl } from '@/constants/pl';
import type { Analysis } from '@/types/analysis';
import { fmtDateTime } from '@/utils/format';
import { SourceDot } from './Badges';

/** «Почему такой вывод»: факторы, источники данных со статусом и ограничения. Прозрачность = критерий оценки жюри. */
export function BasisCard({ data }: { data: Analysis }) {
  return (
    <Card className="basis">
      <details>
        <summary className="basis__summary">{pl.basis.title}</summary>

        <h3 className="basis__h">{pl.basis.factors}</h3>
        <dl className="factors">
          {data.factors.map((f) => (
            <div key={f.id}>
              <dt>{f.label}</dt>
              <dd>{f.value} <small>({f.source})</small></dd>
            </div>
          ))}
        </dl>

        <h3 className="basis__h">{pl.basis.sources}</h3>
        <ul className="sources">
          {data.sources.map((s) => (
            <li key={s.id}>
              <SourceDot status={s.status} />
              <div>
                <div>{s.name}</div>
                <small>
                  {s.period} · {s.license} · {pl.sourceStatus[s.status]}
                  {s.fetchedAt ? ` · ${fmtDateTime(s.fetchedAt)}` : ''}
                </small>
              </div>
            </li>
          ))}
        </ul>

        <h3 className="basis__h">{pl.report.limitations}</h3>
        <ul className="limits">
          {data.limitations.map((l) => <li key={l}>{l}</li>)}
        </ul>
      </details>
    </Card>
  );
}
