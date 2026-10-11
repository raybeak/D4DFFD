import { isTracking, type Frame, type Vec2 } from '../types/frame';
import { drawAxes } from './layers/axes';
import { drawHeatmap } from './layers/heatmap';
import {
  drawCovEllipse,
  drawEstimate,
  drawKalmanMarker,
  drawSlm,
  drawTrail,
  drawVelocity,
  type TrailPoint,
} from './layers/kalman';
import { drawNodes, drawRings } from './layers/nodes';
import { COLORS } from './layers/style';
import type { Transform } from './transform';

export interface LayerToggles {
  heatmap: boolean;
  rings: boolean;
  est: boolean;
  ellipse: boolean;
  trail: boolean;
  prediction: boolean;
  slm: boolean;
}

export const DEFAULT_LAYERS: LayerToggles = {
  heatmap: true,
  rings: true,
  est: true,
  ellipse: true,
  trail: true,
  prediction: true,
  slm: true,
};

export interface SceneInput {
  frame: Frame | null;
  trail: readonly TrailPoint[];
  layers: LayerToggles;
  /** Prediction horizon for the velocity arrow (s). */
  predictDt: number;
  /** Pre-rendered heatmap for frame.grid (see renderHeatmapBitmap). */
  heatmapBitmap: CanvasImageSource | null;
  /** Optional interpolated Kalman position replacing kalman.pos for display. */
  kalmanPos?: Vec2 | null;
}

const warned = new Set<string>();

/** Run one layer; a failing layer is logged once and skipped so the rest still draw. */
function layer(name: string, ctx: CanvasRenderingContext2D, fn: () => void): void {
  ctx.save();
  try {
    fn();
  } catch (e) {
    if (!warned.has(name)) {
      warned.add(name);
      console.warn(`[map] layer "${name}" failed; skipping`, e);
    }
  } finally {
    ctx.restore();
  }
}

/**
 * Compose all map layers onto `ctx` (CSS-pixel coordinates). Pure canvas code,
 * independent of React, so it can be reused for other renderers.
 */
export function drawScene(ctx: CanvasRenderingContext2D, tf: Transform, width: number, height: number, s: SceneInput): void {
  ctx.fillStyle = COLORS.background;
  ctx.fillRect(0, 0, width, height);
  layer('axes', ctx, () => drawAxes(ctx, tf));

  const f = s.frame;
  if (!f) return;

  // Clip data layers to the plot square.
  ctx.save();
  ctx.beginPath();
  ctx.rect(tf.left, tf.top, tf.size, tf.size);
  ctx.clip();

  if (s.layers.heatmap && f.grid && s.heatmapBitmap) {
    const grid = f.grid;
    const bmp = s.heatmapBitmap;
    layer('heatmap', ctx, () => drawHeatmap(ctx, tf, grid, bmp));
  }
  if (s.layers.rings) layer('rings', ctx, () => drawRings(ctx, tf, f.nodes));

  const k = f.kalman;
  const tracking = isTracking(k);
  if (tracking && s.layers.trail) layer('trail', ctx, () => drawTrail(ctx, tf, s.trail));
  if (s.layers.est && f.est) {
    const est = f.est;
    layer('est', ctx, () => drawEstimate(ctx, tf, est));
  }
  if (tracking) {
    const pos = s.kalmanPos ?? k.pos;
    if (s.layers.ellipse) layer('ellipse', ctx, () => drawCovEllipse(ctx, tf, pos, k.cov));
    if (s.layers.prediction) layer('prediction', ctx, () => drawVelocity(ctx, tf, pos, k.vel, s.predictDt));
    if (s.layers.slm && f.slm) {
      const slm = f.slm;
      layer('slm', ctx, () => drawSlm(ctx, tf, pos, slm));
    }
    layer('kalman', ctx, () => drawKalmanMarker(ctx, tf, pos));
  }
  ctx.restore();

  // Nodes last and unclipped so labels near the edge stay readable.
  layer('nodes', ctx, () => drawNodes(ctx, tf, f.nodes));
}
