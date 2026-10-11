import { useEffect, useMemo, useRef } from 'react';
import type { TrailPoint } from '../map/layers/kalman';
import { boundsForFrame, makeTransform, type Margins } from '../map/transform';
import { isNodeActive, isTracking, type Frame, type Vec2 } from '../types/frame';
import { bearingDeg, nodeCentroid, type GridStats } from './metrics';
import {
  drawBackdrop,
  drawBanner,
  drawContours,
  drawEllipse,
  drawEmitter,
  drawEst,
  drawHeat,
  drawNodes,
  drawPerimeter,
  drawPrediction,
  drawRings,
  drawSlm,
  drawSweep,
  drawTrack,
  renderHeatBitmap,
} from './tactical';

export interface TacticalLayers {
  heatmap: boolean;
  contours: boolean;
  rings: boolean;
  est: boolean;
  ellipse: boolean;
  trail: boolean;
  prediction: boolean;
}

export const DEFAULT_TACTICAL_LAYERS: TacticalLayers = {
  heatmap: true,
  contours: true,
  rings: true,
  est: true,
  ellipse: true,
  trail: true,
  prediction: true,
};

interface Props {
  frame: Frame | null;
  /** Receive time of `frame` (ms); null when paused (no extrapolation). */
  recvAt: number | null;
  trail: readonly TrailPoint[];
  stats: GridStats | null;
  layers: TacticalLayers;
  predictDt: number;
}

const MARGINS: Margins = { left: 46, right: 18, top: 30, bottom: 26 };
const MAX_EXTRAPOLATE_S = 1.5;

const warned = new Set<string>();
/** Run one layer; failures are logged once and skipped so the rest still draw. */
function layer(name: string, ctx: CanvasRenderingContext2D, fn: () => void): void {
  ctx.save();
  try {
    fn();
  } catch (e) {
    if (!warned.has(name)) {
      warned.add(name);
      console.warn(`[tactical] layer "${name}" failed; skipping`, e);
    }
  } finally {
    ctx.restore();
  }
}

/** Full-size canvas running one rAF loop; props are read through a ref each paint. */
export function TacticalMap(props: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const propsRef = useRef(props);
  propsRef.current = props;

  const grid = props.frame?.grid ?? null;
  const bitmap = useMemo(() => (grid ? renderHeatBitmap(grid) : null), [grid]);
  const bitmapRef = useRef(bitmap);
  bitmapRef.current = bitmap;

  useEffect(() => {
    const wrap = wrapRef.current;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!wrap || !canvas || !ctx) return;
    let w = 0;
    let h = 0;
    let dpr = 1;
    const ro = new ResizeObserver(([entry]) => {
      if (!entry) return;
      w = Math.floor(entry.contentRect.width);
      h = Math.floor(entry.contentRect.height);
      dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      canvas.style.width = `${w}px`;
      canvas.style.height = `${h}px`;
    });
    ro.observe(wrap);

    let heatA = 0;
    let raf = 0;
    const paint = () => {
      raf = requestAnimationFrame(paint);
      if (w === 0 || h === 0) return;
      const { frame, recvAt, trail, stats, layers, predictDt } = propsRef.current;
      const t = performance.now();
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const tf = makeTransform(boundsForFrame(frame), w, h, MARGINS);
      layer('backdrop', ctx, () => drawBackdrop(ctx, tf, w, h));
      if (!frame) {
        layer('sweep', ctx, () => drawSweep(ctx, tf, t, 'NO DATA · 허브 연결 대기'));
        return;
      }

      const k = frame.kalman;
      const tracking = isTracking(k);
      const anyActive = Object.values(frame.nodes).some(isNodeActive);
      heatA += ((frame.grid && layers.heatmap ? 1 : 0) - heatA) * 0.12;

      ctx.save();
      ctx.beginPath();
      ctx.rect(tf.left, tf.top, tf.size, tf.size);
      ctx.clip();
      layer('perimeter', ctx, () => drawPerimeter(ctx, tf, frame.nodes));
      const bmp = bitmapRef.current;
      if (frame.grid && bmp && heatA > 0.01) {
        const g = frame.grid;
        layer('heat', ctx, () => drawHeat(ctx, tf, g, bmp, heatA));
      }
      if (layers.contours && stats) layer('contours', ctx, () => drawContours(ctx, tf, stats));
      if (layers.rings) layer('rings', ctx, () => drawRings(ctx, tf, frame.nodes));
      if (!tracking && !frame.est) {
        layer('sweep', ctx, () => drawSweep(ctx, tf, t, `SCANNING · RF 감시 중 · ${Object.keys(frame.nodes).length} NODES`));
      }
      if (tracking && layers.trail) layer('trail', ctx, () => drawTrack(ctx, tf, trail));
      if (layers.est && frame.est) {
        const est = frame.est;
        layer('est', ctx, () => drawEst(ctx, tf, est));
      }

      let target: Vec2 | null = frame.est ?? null;
      if (tracking) {
        const dt = recvAt == null ? 0 : Math.min(MAX_EXTRAPOLATE_S, Math.max(0, (Date.now() - recvAt) / 1000));
        const pos: Vec2 = [k.pos[0] + k.vel[0] * dt, k.pos[1] + k.vel[1] * dt];
        target = pos;
        if (layers.ellipse) layer('ellipse', ctx, () => drawEllipse(ctx, tf, pos, k.cov));
        if (layers.prediction) layer('prediction', ctx, () => drawPrediction(ctx, tf, pos, k.vel, predictDt));
        if (frame.slm) {
          const slm = frame.slm;
          layer('slm', ctx, () => drawSlm(ctx, tf, pos, slm));
        }
      }
      ctx.restore();

      layer('nodes', ctx, () => drawNodes(ctx, tf, frame.nodes, t));
      if (target) {
        const pos = target;
        const c = nodeCentroid(frame);
        const brg = Math.round(bearingDeg(c, pos)) % 360;
        const rng = Math.hypot(pos[0] - c[0], pos[1] - c[1]);
        const cep = stats ? ` · ±${Math.round(stats.cep50 * 100)} cm` : '';
        const label = tracking ? 'EMITTER · EKF TRACK' : 'EMITTER · GRID EST';
        layer('emitter', ctx, () =>
          drawEmitter(ctx, tf, pos, t, label, `${String(brg).padStart(3, '0')}° · ${rng.toFixed(2)} m${cep}`),
        );
      }
      if (!anyActive) {
        layer('banner', ctx, () => drawBanner(ctx, tf, '노드 신호 없음', 'ALL NODES DOWN · 측정 대기'));
      } else if (!frame.grid) {
        layer('banner', ctx, () => drawBanner(ctx, tf, '확률 지도 없음', 'GRID NULL · 위치 산출 불가'));
      }
    };
    raf = requestAnimationFrame(paint);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
    };
  }, []);

  return (
    <div ref={wrapRef} className="tmap">
      <canvas ref={canvasRef} role="img" aria-label="RF 확률 히트맵, 센서 노드, EKF 추적" />
    </div>
  );
}
