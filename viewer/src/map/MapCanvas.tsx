import { useEffect, useMemo, useRef, useState } from 'react';
import { isTracking, type Frame, type Vec2 } from '../types/frame';
import { renderHeatmapBitmap } from './layers/heatmap';
import type { TrailPoint } from './layers/kalman';
import { drawScene, type LayerToggles } from './scene';
import { boundsForFrame, makeTransform } from './transform';

interface Props {
  frame: Frame | null;
  /** Local receive time of `frame` (ms), used for interpolation. */
  frameRecvAt: number | null;
  trail: readonly TrailPoint[];
  layers: LayerToggles;
  predictDt: number;
  /** Dead-reckon the Kalman marker between frames with requestAnimationFrame. */
  smooth: boolean;
}

/** Max extrapolation between frames (s); beyond this the marker just holds. */
const MAX_EXTRAPOLATE_S = 1;

export function MapCanvas({ frame, frameRecvAt, trail, layers, predictDt, smooth }: Props) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [box, setBox] = useState({ w: 0, h: 0 });

  // Fit a square canvas to the container (height-limited on wide screens).
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      const side = Math.floor(Math.max(0, Math.min(width, height)));
      setBox((b) => (b.w === side && b.h === side ? b : { w: side, h: side }));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Heatmap bitmap only changes with the grid; rebuild once per frame, not per paint.
  const grid = frame?.grid ?? null;
  const heatmapBitmap = useMemo(() => (grid ? renderHeatmapBitmap(grid) : null), [grid]);

  const bounds = useMemo(() => boundsForFrame(frame), [frame]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || box.w === 0) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(box.w * dpr);
    canvas.height = Math.round(box.h * dpr);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const tf = makeTransform(bounds, box.w, box.h);

    const k = frame?.kalman;
    const tracking = isTracking(k);

    const paint = (kalmanPos: Vec2 | null) => {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      drawScene(ctx, tf, box.w, box.h, { frame, trail, layers, predictDt, heatmapBitmap, kalmanPos });
    };

    if (!smooth || !tracking || frameRecvAt == null) {
      paint(null);
      return;
    }

    // Animate only while there is motion to show; idle frames cost one paint.
    let raf = 0;
    const loop = () => {
      const dt = Math.min(MAX_EXTRAPOLATE_S, Math.max(0, (Date.now() - frameRecvAt) / 1000));
      paint([k.pos[0] + k.vel[0] * dt, k.pos[1] + k.vel[1] * dt]);
      if (dt < MAX_EXTRAPOLATE_S) raf = requestAnimationFrame(loop);
    };
    loop();
    return () => cancelAnimationFrame(raf);
  }, [frame, frameRecvAt, trail, layers, predictDt, smooth, heatmapBitmap, bounds, box]);

  return (
    <div ref={wrapRef} className="map-wrap">
      <canvas
        ref={canvasRef}
        style={{ width: box.w, height: box.h }}
        role="img"
        aria-label="RF emitter map: heatmap, sensor nodes and Kalman track"
      />
    </div>
  );
}
