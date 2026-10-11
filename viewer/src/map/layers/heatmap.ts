import type { Grid } from '../../types/frame';
import type { Transform } from '../transform';

// Viridis sampled at 0, 0.1, ..., 1.0.
const VIRIDIS: readonly [number, number, number][] = [
  [68, 1, 84],
  [72, 36, 117],
  [65, 68, 135],
  [53, 95, 141],
  [42, 120, 142],
  [33, 145, 140],
  [34, 168, 132],
  [68, 191, 112],
  [122, 209, 81],
  [189, 223, 38],
  [253, 231, 37],
];

/** Map v in [0, 1] to viridis RGB. Out-of-range / non-finite values are clamped. */
export function viridis(v: number): [number, number, number] {
  const t = Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;
  const pos = t * (VIRIDIS.length - 1);
  const i = Math.min(VIRIDIS.length - 2, Math.floor(pos));
  const f = pos - i;
  const a = VIRIDIS[i]!;
  const b = VIRIDIS[i + 1]!;
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** Opacity for a cell value: ~transparent at 0, mostly opaque at 1. */
export function heatAlpha(v: number): number {
  const t = Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;
  return Math.sqrt(t) * 0.88;
}

/**
 * Rasterise the grid into an n x n RGBA bitmap. v[0] is the bottom row (y min),
 * so rows are flipped for the canvas (row 0 = top). Returns null if no DOM canvas.
 */
export function renderHeatmapBitmap(grid: Grid): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null;
  const n = grid.n;
  const canvas = document.createElement('canvas');
  canvas.width = n;
  canvas.height = n;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  const img = ctx.createImageData(n, n);
  for (let iy = 0; iy < n; iy++) {
    const row = grid.v[iy];
    const canvasRow = n - 1 - iy;
    for (let ix = 0; ix < n; ix++) {
      const v = row?.[ix] ?? 0;
      const [r, g, b] = viridis(v);
      const o = (canvasRow * n + ix) * 4;
      img.data[o] = r;
      img.data[o + 1] = g;
      img.data[o + 2] = b;
      img.data[o + 3] = Math.round(heatAlpha(v) * 255);
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas;
}

/** Draw a pre-rendered heatmap bitmap; each cell is centred on its grid coordinate. */
export function drawHeatmap(
  ctx: CanvasRenderingContext2D,
  tf: Transform,
  grid: Grid,
  bitmap: CanvasImageSource,
): void {
  const half = grid.step / 2;
  const ext = (grid.n - 1) * grid.step;
  const [x0, y0] = tf.toPx(grid.x0 - half, grid.y0 + ext + half);
  const [x1, y1] = tf.toPx(grid.x0 + ext + half, grid.y0 - half);
  ctx.save();
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.drawImage(bitmap, x0, y0, x1 - x0, y1 - y0);
  ctx.restore();
}
