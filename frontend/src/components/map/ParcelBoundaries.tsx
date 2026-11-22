import { useEffect, useRef } from 'react';
import L from 'leaflet';
import { useMap } from 'react-leaflet';
import { BOUNDARY_COLOR, PANE_BOUNDARIES, PARCEL_FILL, boundaryWeight, type BoundaryKind } from '@/constants/map';
import type { BoundaryFeature } from '@/services/parcelApi';

interface ParcelBoundariesProps {
  /** obręby (зум 15-16, клик приближает) или делянки (зум ≥ 17, клик выбирает). Смена - через key (перемонтирование). */
  kind: BoundaryKind;
  features: BoundaryFeature[];
  /** ID выбранной делянки - её рисует отдельный полигон сверху, здесь не подсвечиваем */
  selectedId: string | null;
  /** ID делянки, по которой только что кликнули (идёт запрос) - сразу заливаем плотнее */
  pendingId: string | null;
  /** Клик по контуру: вызывается ДО клика по карте (canvas → слой → карта), карта затем делает выбор */
  onFeatureClick: (feature: BoundaryFeature) => void;
}

const HOVER_FILL = 0.22;
const OBREB_HOVER_FILL = 0.12;
const PENDING_FILL = 0.4;

const label = (kind: BoundaryKind, f: BoundaryFeature) =>
  kind === 'obreby' ? `Obręb ${f.properties.name || f.properties.id}` : f.properties.id;

/**
 * Границы всех делянок (или obrębów) вокруг видимой области. Canvas-рендерер (тысячи полигонов без тормозов),
 * толщина линии зависит от зума, наведение - лёгкая заливка + код делянки рядом с курсором.
 * Должен рендериться внутри <Pane name={PANE_BOUNDARIES}>.
 */
export function ParcelBoundaries({ kind, features, selectedId, pendingId, onFeatureClick }: ParcelBoundariesProps) {
  const map = useMap();
  const groupRef = useRef<L.LayerGroup | null>(null);
  const rendererRef = useRef<L.Canvas | null>(null);
  const tooltipRef = useRef<L.Tooltip | null>(null);
  const layers = useRef(new Map<string, L.Polygon>());
  const state = useRef({ hovered: null as string | null, selectedId, pendingId });
  const clickRef = useRef(onFeatureClick);
  clickRef.current = onFeatureClick;

  const styleFor = (id: string): L.PathOptions => {
    const { hovered, selectedId: sel, pendingId: pend } = state.current;
    const hover = kind === 'obreby' ? OBREB_HOVER_FILL : HOVER_FILL;
    const fillOpacity = id === sel ? 0 : id === pend ? PENDING_FILL : id === hovered ? hover : 0;
    return { weight: boundaryWeight(map.getZoom(), kind), fillOpacity };
  };
  const restyle = (id: string | null) => {
    if (id) layers.current.get(id)?.setStyle(styleFor(id));
  };

  // слой, рендерер и общий тултип - один раз на монтирование
  useEffect(() => {
    const renderer = L.canvas({ pane: PANE_BOUNDARIES, padding: 0.3 });
    const group = L.layerGroup().addTo(map);
    const tooltip = L.tooltip({ direction: 'top', offset: [0, -10], className: 'parcel-hover-label', opacity: 1 });
    rendererRef.current = renderer;
    groupRef.current = group;
    tooltipRef.current = tooltip;

    const onZoom = () => layers.current.forEach((layer, id) => layer.setStyle(styleFor(id)));
    map.on('zoomend', onZoom);
    const current = layers.current;
    return () => {
      map.off('zoomend', onZoom);
      tooltip.remove();
      group.remove();
      renderer.remove();
      current.clear();
      state.current.hovered = null;
    };
  }, [map]);

  // дифф по ID: добавляем новые контуры, убираем ушедшие из видимых ячеек
  useEffect(() => {
    const group = groupRef.current;
    const renderer = rendererRef.current;
    const tooltip = tooltipRef.current;
    if (!group || !renderer || !tooltip) return;

    const wanted = new Set(features.map((f) => f.id));
    layers.current.forEach((layer, id) => {
      if (wanted.has(id)) return;
      group.removeLayer(layer);
      layers.current.delete(id);
      if (state.current.hovered === id) {
        state.current.hovered = null;
        tooltip.remove();
      }
    });

    for (const f of features) {
      if (layers.current.has(f.id)) continue;
      const latlngs = L.GeoJSON.coordsToLatLngs(f.geometry.coordinates, f.geometry.type === 'Polygon' ? 1 : 2);
      const id = f.id;
      const layer = L.polygon(latlngs, {
        renderer,
        color: BOUNDARY_COLOR,
        opacity: 0.85,
        fill: true, // прозрачная заливка ловит наведение и клик внутри контура
        fillColor: PARCEL_FILL,
        lineJoin: 'round',
        ...styleFor(id)
      });
      layer.on({
        mouseover: (e: L.LeafletMouseEvent) => {
          state.current.hovered = id;
          restyle(id);
          tooltip.setContent(label(kind, f)).setLatLng(e.latlng);
          if (!map.hasLayer(tooltip)) tooltip.addTo(map);
        },
        mousemove: (e: L.LeafletMouseEvent) => tooltip.setLatLng(e.latlng),
        mouseout: () => {
          if (state.current.hovered === id) state.current.hovered = null;
          restyle(id);
          tooltip.remove();
        },
        click: () => clickRef.current(f)
      });
      layers.current.set(id, layer);
      group.addLayer(layer);
    }
  }, [features]);

  // выбранная / ожидающая делянка
  useEffect(() => {
    const prev = state.current;
    state.current = { ...prev, selectedId, pendingId };
    [prev.selectedId, prev.pendingId, selectedId, pendingId].forEach(restyle);
  }, [selectedId, pendingId]);

  return null;
}
