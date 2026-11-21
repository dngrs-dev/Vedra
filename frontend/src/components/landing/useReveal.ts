import { useEffect, type RefObject } from 'react';

/**
 * Анимация появления при прокрутке: элементы с атрибутом data-reveal внутри root
 * получают класс is-visible, когда попадают в экран.
 * Прячем элементы только после монтирования (класс reveal-ready на root) — без JS контент всегда виден.
 */
export function useReveal(root: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    const items = Array.from(el.querySelectorAll<HTMLElement>('[data-reveal]'));
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (reduce || !('IntersectionObserver' in window)) {
      items.forEach((i) => i.classList.add('is-visible'));
      return;
    }
    el.classList.add('reveal-ready');
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-visible');
            io.unobserve(e.target);
          }
        }
      },
      { threshold: 0.15, rootMargin: '0px 0px -40px 0px' }
    );
    items.forEach((i) => io.observe(i));
    return () => io.disconnect();
  }, [root]);
}
