import { useEffect, useRef, useState } from 'react';
import { CROPS } from '@/constants/crops';
import { pl } from '@/constants/pl';
import { ChevronIcon } from '@/components/ui/Icons';
import { useAnalysisStore } from '../store';

/** Мультивыбор культур (как в макете): выпадающий список с чекбоксами. */
export function CropSelect() {
  const cropIds = useAnalysisStore((s) => s.cropIds);
  const toggleCrop = useAnalysisStore((s) => s.toggleCrop);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrapRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const picked = CROPS.filter((c) => cropIds.includes(c.id));

  return (
    <div className={`multi${open ? ' is-open' : ''}`} ref={wrapRef}>
      <button
        type="button"
        className="multi__trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-labelledby="cropLabel"
        onClick={() => setOpen((v) => !v)}
      >
        <span className={`multi__value${picked.length ? '' : ' is-placeholder'}`}>
          {picked.length ? picked.map((c) => `${c.name} - ${c.en}`).join(', ') : pl.form.cropPlaceholder}
        </span>
        <span className="multi__chev"><ChevronIcon /></span>
      </button>

      {open && (
        <ul className="multi__list" role="listbox" aria-multiselectable="true">
          {CROPS.map((c) => {
            const checked = cropIds.includes(c.id);
            return (
              <li key={c.id} role="option" aria-selected={checked}>
                <label className="multi__item">
                  <input type="checkbox" checked={checked} onChange={() => toggleCrop(c.id)} />
                  <span>{c.name}</span>
                  <small>{c.en}</small>
                </label>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
