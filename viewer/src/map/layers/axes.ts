import type { Transform } from '../transform';
import { COLORS, FONT } from './style';

const GRID_STEP = 0.25;
const SQUARE_HALF = 0.5;

/** Plot background, 0.25 m guide lines, 1 m sensor square and axis labels (m). */
export function drawAxes(ctx: CanvasRenderingContext2D, tf: Transform): void {
  const { bounds: b, left, top, size } = tf;
  ctx.save();
  ctx.fillStyle = COLORS.plot;
  ctx.fillRect(left, top, size, size);

  ctx.font = FONT;
  ctx.lineWidth = 1;
  const start = (v: number) => Math.ceil((v - 1e-9) / GRID_STEP) * GRID_STEP;

  ctx.fillStyle = COLORS.label;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'top';
  for (let x = start(b.xmin); x <= b.xmax + 1e-9; x += GRID_STEP) {
    const [px] = tf.toPx(x, 0);
    ctx.strokeStyle = Math.abs(x) < 1e-9 ? COLORS.axisLine : COLORS.gridLine;
    ctx.beginPath();
    ctx.moveTo(Math.round(px) + 0.5, top);
    ctx.lineTo(Math.round(px) + 0.5, top + size);
    ctx.stroke();
    ctx.fillText(fmtTick(x), px, top + size + 6);
  }

  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (let y = start(b.ymin); y <= b.ymax + 1e-9; y += GRID_STEP) {
    const [, py] = tf.toPx(0, y);
    ctx.strokeStyle = Math.abs(y) < 1e-9 ? COLORS.axisLine : COLORS.gridLine;
    ctx.beginPath();
    ctx.moveTo(left, Math.round(py) + 0.5);
    ctx.lineTo(left + size, Math.round(py) + 0.5);
    ctx.stroke();
    ctx.fillText(fmtTick(y), left - 6, py);
  }

  // 1 m sensor square.
  const [sx0, sy0] = tf.toPx(-SQUARE_HALF, SQUARE_HALF);
  const [sx1, sy1] = tf.toPx(SQUARE_HALF, -SQUARE_HALF);
  ctx.strokeStyle = COLORS.square;
  ctx.setLineDash([6, 4]);
  ctx.strokeRect(sx0, sy0, sx1 - sx0, sy1 - sy0);
  ctx.setLineDash([]);

  // Axis unit hints.
  ctx.fillStyle = COLORS.label;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'bottom';
  ctx.fillText('x (m) →', left + size - 4, top + size - 4);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'top';
  ctx.fillText('↑ y (m)', left + 4, top + 4);
  ctx.restore();
}

function fmtTick(v: number): string {
  const r = Math.round(v * 100) / 100;
  return (Object.is(r, -0) ? 0 : r).toString();
}
