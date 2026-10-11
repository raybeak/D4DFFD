// Tactical-style ("Squad Radar") canvas layers for the hub frame. Pure canvas
// code with no React, mirroring src/map/layers so it can be reused elsewhere.
import { covarianceEllipse } from '../math/ellipse';
import type { Frame, Grid, NodeInfo, Slm, TrackingKalman, Vec2 } from '../types/frame';
import { isNodeActive } from '../types/frame';
import type { Transform } from '../map/transform';
import type { TrailPoint } from '../map/layers/kalman';
import type { GridStats, Segment } from './metrics';

export const TC = {
  bg: '#0b0f0d',
  plot: 'rgba(0,0,0,.18)',
  fine: 'rgba(210,230,210,.07)',
  major: 'rgba(120,180,230,.16)',
  label: 'rgba(140,195,240,.7)',
  frame: 'rgba(226,233,224,.85)',
  ok: '#8ddc97',
  down: '#5a675e',
  hostile: '#ff4a3a',
  amber: '#ffb21e',
  pred: '#ffd75a',
  slm: '#7cc6ff',
  text: '#e3e9e0',
} as const;

const MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace';
const KR = '"Noto Sans KR", system-ui, -apple-system, "Malgun Gothic", sans-serif';

// Amber → orange → red → white-hot, with alpha ramping in (from 히트맵.html).
const STOPS: readonly (readonly [number, number, number, number, number])[] = [
  [0, 255, 180, 40, 0],
  [0.18, 255, 176, 32, 0.18],
  [0.42, 255, 128, 30, 0.45],
  [0.68, 255, 70, 45, 0.72],
  [0.88, 255, 60, 55, 0.88],
  [1, 255, 236, 214, 0.96],
];
const HEAT_CUT = 0.07;
const HEAT_GAMMA = 1.6;

/** RGBA (0..255) for a normalised cell value; below HEAT_CUT is transparent. */
export function heatColor(v: number): [number, number, number, number] {
  const r0 = Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : 0;
  const t = r0 < HEAT_CUT ? 0 : Math.pow((r0 - HEAT_CUT) / (1 - HEAT_CUT), HEAT_GAMMA);
  let i = 0;
  while (i < STOPS.length - 2 && t > STOPS[i + 1]![0]) i++;
  const a = STOPS[i]!;
  const b = STOPS[i + 1]!;
  const f = (t - a[0]) / (b[0] - a[0]);
  const mix = (k: number) => a[k]! + (b[k]! - a[k]!) * f;
  return [mix(1), mix(2), mix(3), Math.round(mix(4) * 255)];
}

/** n x n bitmap of the grid; v[0] is the bottom row so rows are flipped. */
export function renderHeatBitmap(grid: Grid): HTMLCanvasElement | null {
  if (typeof document === 'undefined') return null;
  const n = grid.n;
  const c = document.createElement('canvas');
  c.width = n;
  c.height = n;
  const ctx = c.getContext('2d');
  if (!ctx) return null;
  const img = ctx.createImageData(n, n);
  for (let iy = 0; iy < n; iy++) {
    const row = grid.v[iy];
    for (let ix = 0; ix < n; ix++) {
      const [r, g, b, a] = heatColor(row?.[ix] ?? 0);
      const o = ((n - 1 - iy) * n + ix) * 4;
      img.data[o] = r;
      img.data[o + 1] = g;
      img.data[o + 2] = b;
      img.data[o + 3] = a;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

/** Background, 0.05 m / 0.25 m grid, axis labels and scale bar. */
export function drawBackdrop(ctx: CanvasRenderingContext2D, tf: Transform, w: number, h: number): void {
  ctx.fillStyle = TC.bg;
  ctx.fillRect(0, 0, w, h);
  const vg = ctx.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, Math.max(w, h) * 0.7);
  vg.addColorStop(0, 'rgba(20,32,25,.9)');
  vg.addColorStop(1, 'rgba(7,9,8,0)');
  ctx.fillStyle = vg;
  ctx.fillRect(0, 0, w, h);

  const { xmin, xmax, ymin, ymax } = tf.bounds;
  const lines = (step: number, style: string, dash: number[]) => {
    ctx.strokeStyle = style;
    ctx.setLineDash(dash);
    ctx.lineWidth = 1;
    ctx.beginPath();
    for (let x = Math.ceil(xmin / step) * step; x <= xmax + 1e-9; x += step) {
      const [px] = tf.toPx(x, 0);
      ctx.moveTo(Math.round(px) + 0.5, tf.top);
      ctx.lineTo(Math.round(px) + 0.5, tf.top + tf.size);
    }
    for (let y = Math.ceil(ymin / step) * step; y <= ymax + 1e-9; y += step) {
      const [, py] = tf.toPx(0, y);
      ctx.moveTo(tf.left, Math.round(py) + 0.5);
      ctx.lineTo(tf.left + tf.size, Math.round(py) + 0.5);
    }
    ctx.stroke();
    ctx.setLineDash([]);
  };
  ctx.fillStyle = TC.plot;
  ctx.fillRect(tf.left, tf.top, tf.size, tf.size);
  lines(0.05, TC.fine, [2, 5]);
  lines(0.25, TC.major, []);

  ctx.font = `600 9.5px ${MONO}`;
  ctx.fillStyle = TC.label;
  ctx.textBaseline = 'top';
  ctx.textAlign = 'center';
  for (let x = Math.ceil(xmin / 0.25) * 0.25; x <= xmax + 1e-9; x += 0.25) {
    const [px] = tf.toPx(x, 0);
    ctx.fillText(x.toFixed(2), px, tf.top + tf.size + 6);
  }
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let y = Math.ceil(ymin / 0.25) * 0.25; y <= ymax + 1e-9; y += 0.25) {
    const [, py] = tf.toPx(0, y);
    ctx.fillText(y.toFixed(2), tf.left - 6, py);
  }

  // Corner brackets around the plot.
  ctx.strokeStyle = 'rgba(210,230,210,.3)';
  ctx.strokeRect(tf.left + 0.5, tf.top + 0.5, tf.size - 1, tf.size - 1);
  ctx.strokeStyle = TC.frame;
  ctx.lineWidth = 1.6;
  const L = 18;
  for (const [x, y, sx, sy] of [
    [tf.left, tf.top, 1, 1],
    [tf.left + tf.size, tf.top, -1, 1],
    [tf.left, tf.top + tf.size, 1, -1],
    [tf.left + tf.size, tf.top + tf.size, -1, -1],
  ] as const) {
    ctx.beginPath();
    ctx.moveTo(x + L * sx, y);
    ctx.lineTo(x, y);
    ctx.lineTo(x, y + L * sy);
    ctx.stroke();
  }

  ctx.font = `700 12px ${MONO}`;
  ctx.fillStyle = 'rgba(240,240,230,.9)';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText('N ↑  (+y)', tf.left + tf.size - 4, tf.top - 8);

  // 0.25 m scale bar.
  const bw = 0.25 * tf.scale;
  const bx = tf.left;
  const by = tf.top - 12;
  ctx.fillStyle = 'rgba(226,233,224,.7)';
  ctx.fillRect(bx, by, bw, 2);
  ctx.fillRect(bx, by - 4, 1, 6);
  ctx.fillRect(bx + bw - 1, by - 4, 1, 6);
  ctx.font = `500 10px ${MONO}`;
  ctx.textAlign = 'left';
  ctx.fillStyle = 'rgba(210,230,210,.6)';
  ctx.fillText('25 cm', bx + bw + 8, by + 4);
}

/** Dashed perimeter through the node bounding box (the sensor square). */
export function drawPerimeter(ctx: CanvasRenderingContext2D, tf: Transform, nodes: Frame['nodes']): void {
  const ns = Object.values(nodes);
  if (ns.length < 2) return;
  const xs = ns.map((n) => n.x);
  const ys = ns.map((n) => n.y);
  const [x0, y0] = tf.toPx(Math.min(...xs), Math.max(...ys));
  const [x1, y1] = tf.toPx(Math.max(...xs), Math.min(...ys));
  ctx.strokeStyle = 'rgba(141,220,151,.35)';
  ctx.lineWidth = 1.2;
  ctx.setLineDash([6, 4]);
  ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
  ctx.setLineDash([]);
}

/** Heatmap bitmap, softened, with fade-in alpha. */
export function drawHeat(
  ctx: CanvasRenderingContext2D,
  tf: Transform,
  grid: Grid,
  bmp: CanvasImageSource,
  alpha: number,
): void {
  const half = grid.step / 2;
  const ext = (grid.n - 1) * grid.step;
  const [x0, y0] = tf.toPx(grid.x0 - half, grid.y0 + ext + half);
  const [x1, y1] = tf.toPx(grid.x0 + ext + half, grid.y0 - half);
  ctx.globalAlpha = alpha;
  ctx.imageSmoothingEnabled = true;
  ctx.imageSmoothingQuality = 'high';
  ctx.filter = `blur(${Math.max(1.5, grid.step * tf.scale * 0.35).toFixed(1)}px)`;
  ctx.drawImage(bmp, x0, y0, x1 - x0, y1 - y0);
  ctx.filter = 'none';
  ctx.globalAlpha = 1;
}

function strokeSegs(ctx: CanvasRenderingContext2D, tf: Transform, segs: readonly Segment[]): void {
  ctx.beginPath();
  for (const [a, b] of segs) {
    const [ax, ay] = tf.toPx(a[0], a[1]);
    const [bx, by] = tf.toPx(b[0], b[1]);
    ctx.moveTo(ax, ay);
    ctx.lineTo(bx, by);
  }
  ctx.stroke();
}

/** 90% (dashed amber) and 50% (solid red) highest-density contours. */
export function drawContours(ctx: CanvasRenderingContext2D, tf: Transform, s: GridStats): void {
  ctx.strokeStyle = 'rgba(255,190,80,.75)';
  ctx.lineWidth = 1.1;
  ctx.setLineDash([4, 4]);
  strokeSegs(ctx, tf, s.c90);
  ctx.setLineDash([]);
  ctx.strokeStyle = 'rgba(255,90,60,.95)';
  ctx.lineWidth = 1.6;
  strokeSegs(ctx, tf, s.c50);
}

/** Distance rings for active nodes (radius = node.d). */
export function drawRings(ctx: CanvasRenderingContext2D, tf: Transform, nodes: Frame['nodes']): void {
  ctx.strokeStyle = 'rgba(141,220,151,.4)';
  ctx.lineWidth = 1;
  ctx.setLineDash([3, 4]);
  for (const n of Object.values(nodes)) {
    if (!isNodeActive(n) || n.d == null || !(n.d > 0)) continue;
    const [px, py] = tf.toPx(n.x, n.y);
    ctx.beginPath();
    ctx.arc(px, py, n.d * tf.scale, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.setLineDash([]);
}

/** Node diamonds with name + RSSI; active nodes pulse, down nodes are grey with an X. */
export function drawNodes(ctx: CanvasRenderingContext2D, tf: Transform, nodes: Frame['nodes'], t: number): void {
  const [cx, cy] = tf.toPx((tf.bounds.xmin + tf.bounds.xmax) / 2, (tf.bounds.ymin + tf.bounds.ymax) / 2);
  Object.entries(nodes).forEach(([name, n]: [string, NodeInfo], i) => {
    const on = isNodeActive(n);
    const [x, y] = tf.toPx(n.x, n.y);
    const col = on ? TC.ok : TC.down;
    if (on) {
      const ph = (t / 1400 + i * 0.25) % 1;
      ctx.strokeStyle = col;
      ctx.globalAlpha = (1 - ph) * 0.6;
      ctx.lineWidth = 1.2;
      ctx.beginPath();
      ctx.arc(x, y, 9 + ph * 16, 0, Math.PI * 2);
      ctx.stroke();
      ctx.globalAlpha = 1;
    }
    const s = 8;
    ctx.fillStyle = 'rgba(8,12,10,.92)';
    ctx.strokeStyle = col;
    ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(x, y - s);
    ctx.lineTo(x + s, y);
    ctx.lineTo(x, y + s);
    ctx.lineTo(x - s, y);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
    if (!on) {
      ctx.beginPath();
      ctx.moveTo(x - 3.5, y - 3.5);
      ctx.lineTo(x + 3.5, y + 3.5);
      ctx.moveTo(x + 3.5, y - 3.5);
      ctx.lineTo(x - 3.5, y + 3.5);
      ctx.stroke();
    } else {
      ctx.fillStyle = col;
      ctx.fillRect(x - 2, y - 2, 4, 4);
    }
    // Label inward horizontally (stays inside the canvas), outward vertically.
    const right = x >= cx;
    const below = y >= cy;
    const lx = x + (right ? 10 : -10);
    const ly = y + (below ? 22 : -24);
    ctx.textAlign = right ? 'right' : 'left';
    ctx.textBaseline = 'alphabetic';
    ctx.font = `700 12px ${MONO}`;
    ctx.lineWidth = 3;
    ctx.strokeStyle = 'rgba(8,12,10,.9)';
    ctx.strokeText(name, lx, ly);
    ctx.fillStyle = on ? TC.text : 'rgba(160,175,165,.75)';
    ctx.fillText(name, lx, ly);
    const sub = on ? `${n.rssi!.toFixed(0)} dBm${n.d != null ? ` · ${n.d.toFixed(2)} m` : ''}` : 'NO SIGNAL';
    ctx.font = `500 10px ${MONO}`;
    ctx.strokeText(sub, lx, ly + 13);
    ctx.fillStyle = on ? 'rgba(141,220,151,.9)' : 'rgba(255,140,120,.8)';
    ctx.fillText(sub, lx, ly + 13);
  });
}

/** Grid-argmax estimate as a small amber cross. */
export function drawEst(ctx: CanvasRenderingContext2D, tf: Transform, est: Vec2): void {
  const [x, y] = tf.toPx(est[0], est[1]);
  ctx.strokeStyle = TC.amber;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x - 6, y);
  ctx.lineTo(x + 6, y);
  ctx.moveTo(x, y - 6);
  ctx.lineTo(x, y + 6);
  ctx.stroke();
}

/** Fading track of recent Kalman positions; reconnect gaps are not joined. */
export function drawTrack(ctx: CanvasRenderingContext2D, tf: Transform, trail: readonly TrailPoint[]): void {
  const n = trail.length;
  if (n < 2) return;
  ctx.lineWidth = 1.6;
  for (let i = 1; i < n; i++) {
    const a = trail[i - 1]!;
    const b = trail[i]!;
    if (a.seg !== b.seg) continue;
    const [x0, y0] = tf.toPx(a.pos[0], a.pos[1]);
    const [x1, y1] = tf.toPx(b.pos[0], b.pos[1]);
    ctx.strokeStyle = `rgba(255,140,110,${(0.08 + 0.5 * (i / n)).toFixed(3)})`;
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
  }
  trail.forEach((p, i) => {
    if (i % 3) return;
    const [x, y] = tf.toPx(p.pos[0], p.pos[1]);
    ctx.fillStyle = `rgba(255,140,110,${(0.15 + 0.6 * (i / n)).toFixed(3)})`;
    ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
  });
}

/** 2-sigma covariance ellipse. */
export function drawEllipse(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, cov: TrackingKalman['cov']): void {
  const e = covarianceEllipse(cov, 2);
  if (!e) return;
  const [x, y] = tf.toPx(pos[0], pos[1]);
  ctx.beginPath();
  // Canvas y is flipped, so the world CCW angle becomes CW.
  ctx.ellipse(x, y, Math.max(1, e.rx * tf.scale), Math.max(1, e.ry * tf.scale), -e.angle, 0, Math.PI * 2);
  ctx.fillStyle = 'rgba(255,74,58,.08)';
  ctx.fill();
  ctx.strokeStyle = 'rgba(255,120,100,.85)';
  ctx.lineWidth = 1.3;
  ctx.setLineDash([5, 3]);
  ctx.stroke();
  ctx.setLineDash([]);
}

function arrow(ctx: CanvasRenderingContext2D, x0: number, y0: number, x1: number, y1: number): void {
  const len = Math.hypot(x1 - x0, y1 - y0);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  if (len < 2) return;
  const a = Math.atan2(y1 - y0, x1 - x0);
  const h = Math.min(10, len * 0.6);
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - h * Math.cos(a - 0.45), y1 - h * Math.sin(a - 0.45));
  ctx.lineTo(x1 - h * Math.cos(a + 0.45), y1 - h * Math.sin(a + 0.45));
  ctx.closePath();
  ctx.fill();
}

/** Predicted position after dt seconds (pos + vel*dt) as a yellow dashed corridor. */
export function drawPrediction(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, vel: Vec2, dt: number): void {
  const [x0, y0] = tf.toPx(pos[0], pos[1]);
  const [x1, y1] = tf.toPx(pos[0] + vel[0] * dt, pos[1] + vel[1] * dt);
  if (Math.hypot(x1 - x0, y1 - y0) < 3) return;
  ctx.strokeStyle = 'rgba(255,215,90,.95)';
  ctx.fillStyle = 'rgba(255,215,90,.95)';
  ctx.lineWidth = 2;
  ctx.setLineDash([8, 5]);
  arrow(ctx, x0, y0, x1, y1);
  ctx.setLineDash([]);
  ctx.font = `600 9.5px ${MONO}`;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = 'rgba(255,225,140,.95)';
  ctx.fillText(`PRED +${dt.toFixed(1)}s`, x1 + 8, y1 + 12);
}

/** SLM suggestion (m displacement), blue dotted. */
export function drawSlm(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, slm: Slm): void {
  const [x0, y0] = tf.toPx(pos[0], pos[1]);
  const [x1, y1] = tf.toPx(pos[0] + slm.dx, pos[1] + slm.dy);
  ctx.strokeStyle = TC.slm;
  ctx.fillStyle = TC.slm;
  ctx.lineWidth = 1.8;
  ctx.setLineDash([2, 4]);
  arrow(ctx, x0, y0, x1, y1);
  ctx.setLineDash([]);
  ctx.font = `600 9.5px ${MONO}`;
  ctx.textAlign = 'left';
  ctx.fillText('SLM', x1 + 8, y1 - 6);
}

/** Hostile emitter marker with pulse and readout label. */
export function drawEmitter(
  ctx: CanvasRenderingContext2D,
  tf: Transform,
  pos: Vec2,
  t: number,
  label: string,
  sub: string,
): void {
  const [x, y] = tf.toPx(pos[0], pos[1]);
  const ph = (t / 1100) % 1;
  ctx.strokeStyle = TC.hostile;
  ctx.globalAlpha = (1 - ph) * 0.7;
  ctx.lineWidth = 1.2;
  ctx.beginPath();
  ctx.arc(x, y, 14 + ph * 20, 0, Math.PI * 2);
  ctx.stroke();
  ctx.globalAlpha = 1;
  const s = 13;
  ctx.fillStyle = 'rgba(255,74,58,.28)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(x, y - s);
  ctx.lineTo(x + s, y);
  ctx.lineTo(x, y + s);
  ctx.lineTo(x - s, y);
  ctx.closePath();
  ctx.fill();
  ctx.stroke();
  ctx.lineWidth = 1.8;
  ctx.beginPath();
  ctx.moveTo(x - 6, y - 2);
  ctx.lineTo(x, y + 3);
  ctx.lineTo(x + 6, y - 2);
  ctx.stroke();

  const right = x < tf.left + tf.size * 0.62;
  const tx = x + (right ? 22 : -22);
  ctx.textAlign = right ? 'left' : 'right';
  ctx.textBaseline = 'alphabetic';
  ctx.lineWidth = 3;
  ctx.strokeStyle = 'rgba(8,12,10,.85)';
  ctx.font = `700 11px ${MONO}`;
  ctx.strokeText(label, tx, y - 4);
  ctx.fillStyle = '#ff6a5c';
  ctx.fillText(label, tx, y - 4);
  ctx.font = `500 10px ${MONO}`;
  ctx.strokeText(sub, tx, y + 10);
  ctx.fillStyle = 'rgba(255,200,190,.9)';
  ctx.fillText(sub, tx, y + 10);
}

/** Idle radar sweep while there is no target. */
export function drawSweep(ctx: CanvasRenderingContext2D, tf: Transform, t: number, text: string): void {
  const cx = tf.left + tf.size / 2;
  const cy = tf.top + tf.size / 2;
  const R = tf.size * 0.75;
  const a0 = (t / 2600) * Math.PI * 2;
  for (let q = 0; q < 26; q++) {
    const a = a0 - q * 0.022;
    ctx.strokeStyle = `rgba(141,220,151,${(0.16 * (1 - q / 26)).toFixed(3)})`;
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(cx + Math.cos(a) * R, cy + Math.sin(a) * R);
    ctx.stroke();
  }
  ctx.font = `600 10px ${MONO}`;
  ctx.fillStyle = 'rgba(141,220,151,.8)';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(text, cx, tf.top + tf.size - 12);
}

/** Centred warning banner (e.g. no grid / all nodes down). */
export function drawBanner(ctx: CanvasRenderingContext2D, tf: Transform, l1: string, l2: string): void {
  const cx = tf.left + tf.size / 2;
  const cy = tf.top + tf.size * 0.44;
  ctx.font = `900 28px ${KR}`;
  const bw = Math.min(tf.size * 0.86, Math.max(260, ctx.measureText(l1).width + 60));
  const bh = 92;
  ctx.fillStyle = 'rgba(10,2,2,.82)';
  ctx.fillRect(cx - bw / 2, cy - bh / 2, bw, bh);
  ctx.strokeStyle = '#ff3b30';
  ctx.lineWidth = 1.5;
  ctx.strokeRect(cx - bw / 2 + 0.5, cy - bh / 2 + 0.5, bw - 1, bh - 1);
  ctx.fillStyle = '#ff3b30';
  ctx.fillRect(cx - bw / 2, cy - bh / 2, bw, 4);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#fff';
  ctx.fillText(l1, cx, cy + 6);
  ctx.font = `500 11px ${MONO}`;
  ctx.fillStyle = TC.amber;
  ctx.fillText(l2, cx, cy + 30);
}
