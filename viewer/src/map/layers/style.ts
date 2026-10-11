/** Shared colours for the canvas layers (dark theme). */
export const COLORS = {
  background: '#0b0f14',
  plot: '#10161d',
  gridLine: 'rgba(160, 180, 200, 0.12)',
  axisLine: 'rgba(160, 180, 200, 0.35)',
  label: 'rgba(200, 214, 228, 0.7)',
  square: 'rgba(220, 230, 240, 0.55)',
  nodeActive: '#4cc9f0',
  nodeDown: '#6b7785',
  ring: 'rgba(76, 201, 240, 0.45)',
  est: '#ffd166',
  kalman: '#ff5d8f',
  ellipse: 'rgba(255, 93, 143, 0.9)',
  ellipseFill: 'rgba(255, 93, 143, 0.12)',
  velocity: '#ff9eb8',
  slm: '#b8f2a0',
  text: '#e6edf3',
} as const;

export const FONT = '12px system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

/** Draw a line with a filled arrowhead from (x0, y0) to (x1, y1) in canvas px. */
export function drawArrow(
  ctx: CanvasRenderingContext2D,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  head = 9,
): void {
  const len = Math.hypot(x1 - x0, y1 - y0);
  ctx.beginPath();
  ctx.moveTo(x0, y0);
  ctx.lineTo(x1, y1);
  ctx.stroke();
  if (len < 1) return;
  const ang = Math.atan2(y1 - y0, x1 - x0);
  const h = Math.min(head, len * 0.6);
  ctx.save();
  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x1 - h * Math.cos(ang - 0.45), y1 - h * Math.sin(ang - 0.45));
  ctx.lineTo(x1 - h * Math.cos(ang + 0.45), y1 - h * Math.sin(ang + 0.45));
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}
