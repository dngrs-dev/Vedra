import { useEffect } from 'react';
import L from 'leaflet';
import { useMap } from 'react-leaflet';
import type { LatLng } from '@/types/parcel';
import { rectToRing } from '@/utils/geo';

interface AreaSelectProps {
  /** Вызывается после отпускания ЛКМ: контур прямоугольника (замкнутое кольцо) */
  onSelect: (ring: LatLng[]) => void;
}

const MIN_DRAG_PX = 8;

/**
 * Свободное выделение делянки: Ctrl (⌘ на Mac) + зажатая ЛКМ + перетаскивание.
 * Пока зажат Ctrl, перетаскивание карты отключено, курсор — крестик.
 */
export function AreaSelect({ onSelect }: AreaSelectProps) {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    let armed = false; // Ctrl сейчас зажат
    let start: L.LatLng | null = null;
    let startPx: L.Point | null = null;
    let last: L.LatLng | null = null;
    let rect: L.Rectangle | null = null;

    const setArmed = (v: boolean) => {
      if (v === armed) return;
      armed = v;
      container.classList.toggle('is-selecting', v);
      if (v) map.dragging.disable();
      else if (!start) map.dragging.enable(); // не включаем посреди выделения
    };

    const cleanup = () => {
      rect?.remove();
      rect = null;
      start = null;
      startPx = null;
      last = null;
    };

    const onKey = (e: KeyboardEvent) => setArmed(e.ctrlKey || e.metaKey);
    const onBlur = () => {
      cleanup();
      setArmed(false);
      map.dragging.enable();
    };

    const onDown = (e: L.LeafletMouseEvent) => {
      const ev = e.originalEvent;
      if (!(ev.ctrlKey || ev.metaKey) || ev.button !== 0) return;
      start = e.latlng;
      last = e.latlng;
      startPx = e.containerPoint;
      rect = L.rectangle(L.latLngBounds(start, start), {
        color: '#ffe27a', weight: 2, dashArray: '6 4', fillColor: '#ffe27a', fillOpacity: 0.2, interactive: false
      }).addTo(map);
    };

    const onMove = (e: L.LeafletMouseEvent) => {
      if (!start || !rect) return;
      last = e.latlng;
      rect.setBounds(L.latLngBounds(start, e.latlng));
    };

    const onUp = (ev: MouseEvent) => {
      if (!start || !last || !startPx) return;
      const endPx = map.latLngToContainerPoint(last);
      const moved = Math.max(Math.abs(endPx.x - startPx.x), Math.abs(endPx.y - startPx.y));
      const a = start;
      const b = last;
      cleanup();
      if (!(ev.ctrlKey || ev.metaKey)) setArmed(false);
      if (!armed) map.dragging.enable();
      if (moved < MIN_DRAG_PX) return; // это был просто клик, не выделение
      onSelect(rectToRing(a, b));
    };

    map.on('mousedown', onDown);
    map.on('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    window.addEventListener('keydown', onKey);
    window.addEventListener('keyup', onKey);
    window.addEventListener('blur', onBlur);

    return () => {
      map.off('mousedown', onDown);
      map.off('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      window.removeEventListener('keydown', onKey);
      window.removeEventListener('keyup', onKey);
      window.removeEventListener('blur', onBlur);
      cleanup();
      container.classList.remove('is-selecting');
      map.dragging.enable();
    };
  }, [map, onSelect]);

  return null;
}
