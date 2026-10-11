import { isNodeActive, type NodeInfo } from '../../types/frame';
import type { Transform } from '../transform';
import { COLORS, FONT } from './style';

/** Distance rings (radius = estimated distance d) for active nodes. */
export function drawRings(ctx: CanvasRenderingContext2D, tf: Transform, nodes: Record<string, NodeInfo>): void {
  ctx.save();
  ctx.strokeStyle = COLORS.ring;
  ctx.lineWidth = 1;
  for (const n of Object.values(nodes)) {
    if (!isNodeActive(n) || n.d == null || !(n.d > 0)) continue;
    const [px, py] = tf.toPx(n.x, n.y);
    ctx.beginPath();
    ctx.arc(px, py, n.d * tf.scale, 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.restore();
}

/**
 * Node markers. Active: filled diamond in accent colour. Down/stale: hollow grey
 * diamond with an X, so state is readable without relying on colour.
 */
export function drawNodes(ctx: CanvasRenderingContext2D, tf: Transform, nodes: Record<string, NodeInfo>): void {
  const r = 8;
  ctx.save();
  ctx.font = FONT;
  ctx.textBaseline = 'middle';
  for (const [name, n] of Object.entries(nodes)) {
    const [px, py] = tf.toPx(n.x, n.y);
    const active = isNodeActive(n);
    const color = active ? COLORS.nodeActive : COLORS.nodeDown;

    ctx.beginPath();
    ctx.moveTo(px, py - r);
    ctx.lineTo(px + r, py);
    ctx.lineTo(px, py + r);
    ctx.lineTo(px - r, py);
    ctx.closePath();
    ctx.lineWidth = 2;
    ctx.strokeStyle = color;
    if (active) {
      ctx.fillStyle = color;
      ctx.fill();
    } else {
      ctx.fillStyle = COLORS.plot;
      ctx.fill();
      ctx.stroke();
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(px - 3.5, py - 3.5);
      ctx.lineTo(px + 3.5, py + 3.5);
      ctx.moveTo(px + 3.5, py - 3.5);
      ctx.lineTo(px - 3.5, py + 3.5);
      ctx.stroke();
    }

    // Label on the outward side of the node so it stays inside the plot.
    const [cx] = tf.toPx((tf.bounds.xmin + tf.bounds.xmax) / 2, 0);
    const outward = px >= cx ? -1 : 1;
    ctx.textAlign = outward > 0 ? 'left' : 'right';
    const label = active ? name : `${name} (down)`;
    ctx.fillStyle = active ? COLORS.text : COLORS.nodeDown;
    ctx.fillText(label, px + outward * (r + 5), py + (n.y >= 0 ? 14 : -14));
  }
  ctx.restore();
}
