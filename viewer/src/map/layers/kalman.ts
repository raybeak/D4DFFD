import { covarianceEllipse } from '../../math/ellipse';
import type { Slm, TrackingKalman, Vec2 } from '../../types/frame';
import type { Transform } from '../transform';
import { COLORS, drawArrow } from './style';

/** One trail point; points with different `seg` are not connected (reconnect gap). */
export interface TrailPoint {
  pos: Vec2;
  seg: number;
}

/** Grid-argmax estimate as a "+" cross. */
export function drawEstimate(ctx: CanvasRenderingContext2D, tf: Transform, est: Vec2): void {
  const [px, py] = tf.toPx(est[0], est[1]);
  const r = 7;
  ctx.save();
  ctx.strokeStyle = COLORS.est;
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  ctx.moveTo(px - r, py);
  ctx.lineTo(px + r, py);
  ctx.moveTo(px, py - r);
  ctx.lineTo(px, py + r);
  ctx.stroke();
  ctx.restore();
}

/** Recent Kalman positions; older segments fade out. */
export function drawTrail(ctx: CanvasRenderingContext2D, tf: Transform, trail: readonly TrailPoint[]): void {
  if (trail.length < 2) return;
  ctx.save();
  ctx.strokeStyle = COLORS.kalman;
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  const total = trail.length - 1;
  for (let i = 1; i < trail.length; i++) {
    const a = trail[i - 1]!;
    const b = trail[i]!;
    if (a.seg !== b.seg) continue;
    ctx.globalAlpha = 0.08 + 0.72 * (i / total);
    const [x0, y0] = tf.toPx(a.pos[0], a.pos[1]);
    const [x1, y1] = tf.toPx(b.pos[0], b.pos[1]);
    ctx.beginPath();
    ctx.moveTo(x0, y0);
    ctx.lineTo(x1, y1);
    ctx.stroke();
  }
  ctx.restore();
}

/** 2-sigma covariance ellipse centred at `pos`. */
export function drawCovEllipse(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, cov: TrackingKalman['cov']): void {
  const e = covarianceEllipse(cov, 2);
  if (!e) return;
  const [px, py] = tf.toPx(pos[0], pos[1]);
  ctx.save();
  ctx.strokeStyle = COLORS.ellipse;
  ctx.fillStyle = COLORS.ellipseFill;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  // Canvas y points down, so world CCW rotation becomes negative.
  ctx.ellipse(px, py, Math.max(e.rx * tf.scale, 0.5), Math.max(e.ry * tf.scale, 0.5), -e.angle, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

/** Velocity arrow from pos to the predicted position pos + vel * dt. */
export function drawVelocity(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, vel: Vec2, dt: number): void {
  const [x0, y0] = tf.toPx(pos[0], pos[1]);
  const [x1, y1] = tf.toPx(pos[0] + vel[0] * dt, pos[1] + vel[1] * dt);
  ctx.save();
  ctx.strokeStyle = COLORS.velocity;
  ctx.fillStyle = COLORS.velocity;
  ctx.lineWidth = 2;
  drawArrow(ctx, x0, y0, x1, y1);
  ctx.restore();
}

/** Kalman position marker: filled circle with a dark outline. */
export function drawKalmanMarker(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2): void {
  const [px, py] = tf.toPx(pos[0], pos[1]);
  ctx.save();
  ctx.fillStyle = COLORS.kalman;
  ctx.strokeStyle = COLORS.background;
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.arc(px, py, 7, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.restore();
}

/** SLM suggestion: dashed arrow from pos by (dx, dy) metres, distinct colour. */
export function drawSlm(ctx: CanvasRenderingContext2D, tf: Transform, pos: Vec2, slm: Slm): void {
  const [x0, y0] = tf.toPx(pos[0], pos[1]);
  const [x1, y1] = tf.toPx(pos[0] + slm.dx, pos[1] + slm.dy);
  ctx.save();
  ctx.strokeStyle = COLORS.slm;
  ctx.fillStyle = COLORS.slm;
  ctx.lineWidth = 2;
  ctx.setLineDash([5, 4]);
  drawArrow(ctx, x0, y0, x1, y1);
  ctx.restore();
}
