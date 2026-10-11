import type { Frame } from '../types/frame';

/** World bounds in metres. */
export interface Bounds {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
}

export const DEFAULT_BOUNDS: Bounds = { xmin: -0.6, xmax: 0.6, ymin: -0.6, ymax: 0.6 };

/** Maps world metres (origin centre, y up) to canvas CSS pixels (y down). */
export interface Transform {
  bounds: Bounds;
  /** Pixels per metre. */
  scale: number;
  /** Inner plot rectangle in canvas pixels. */
  left: number;
  top: number;
  size: number;
  toPx(x: number, y: number): [number, number];
  toWorld(px: number, py: number): [number, number];
}

export interface Margins {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const DEFAULT_MARGINS: Margins = { left: 40, right: 12, top: 12, bottom: 28 };

/**
 * Build a transform that fits `bounds` (made square around its centre) into a
 * canvas of `width` x `height` CSS pixels, leaving `margins` for axis labels.
 */
export function makeTransform(
  bounds: Bounds,
  width: number,
  height: number,
  margins: Margins = DEFAULT_MARGINS,
): Transform {
  const span = Math.max(bounds.xmax - bounds.xmin, bounds.ymax - bounds.ymin, 1e-6);
  const cx = (bounds.xmin + bounds.xmax) / 2;
  const cy = (bounds.ymin + bounds.ymax) / 2;
  const sq: Bounds = { xmin: cx - span / 2, xmax: cx + span / 2, ymin: cy - span / 2, ymax: cy + span / 2 };

  const availW = Math.max(1, width - margins.left - margins.right);
  const availH = Math.max(1, height - margins.top - margins.bottom);
  const size = Math.min(availW, availH);
  const left = margins.left + (availW - size) / 2;
  const top = margins.top + (availH - size) / 2;
  const scale = size / span;

  return {
    bounds: sq,
    scale,
    left,
    top,
    size,
    toPx: (x, y) => [left + (x - sq.xmin) * scale, top + (sq.ymax - y) * scale],
    toWorld: (px, py) => [sq.xmin + (px - left) / scale, sq.ymax - (py - top) / scale],
  };
}

/**
 * View bounds for a frame: the grid extent (cell centres), or `fallback` when the
 * grid is null, unioned with node positions plus a small pad.
 */
export function boundsForFrame(frame: Frame | null, fallback: Bounds = DEFAULT_BOUNDS): Bounds {
  if (!frame) return fallback;
  const g = frame.grid;
  let b: Bounds = fallback;
  if (g) {
    const ext = (g.n - 1) * g.step;
    b = { xmin: g.x0, xmax: g.x0 + ext, ymin: g.y0, ymax: g.y0 + ext };
  }
  const pad = 0.1;
  for (const n of Object.values(frame.nodes)) {
    b = {
      xmin: Math.min(b.xmin, n.x - pad),
      xmax: Math.max(b.xmax, n.x + pad),
      ymin: Math.min(b.ymin, n.y - pad),
      ymax: Math.max(b.ymax, n.y + pad),
    };
  }
  return b;
}
