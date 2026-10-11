import { initProgress, isNodeActive, isTracking, type Frame, type Grid, type Vec2 } from '../types/frame';

/** One contour segment in world metres. */
export type Segment = [Vec2, Vec2];

export interface GridStats {
  /** Value threshold enclosing 50% / 90% of the (sum-normalised) mass. */
  t50: number;
  t90: number;
  /** Radius (m) of a circle with the same area as the 50% region. */
  cep50: number;
  c50: Segment[];
  c90: Segment[];
}

/** Bearing in degrees, 0 = +y (north), clockwise. */
export function bearingDeg(from: Vec2, to: Vec2): number {
  const deg = (Math.atan2(to[0] - from[0], to[1] - from[1]) * 180) / Math.PI;
  return (deg + 360) % 360;
}

const CARD8 = ['N · 북', 'NE · 북동', 'E · 동', 'SE · 남동', 'S · 남', 'SW · 남서', 'W · 서', 'NW · 북서'];
export function cardinal(deg: number): string {
  return CARD8[Math.round(((deg % 360) + 360) % 360 / 45) % 8]!;
}

/** Centroid of node positions; (0, 0) when there are none. */
export function nodeCentroid(frame: Frame | null): Vec2 {
  const ns = frame ? Object.values(frame.nodes) : [];
  if (ns.length === 0) return [0, 0];
  let sx = 0;
  let sy = 0;
  for (const n of ns) {
    sx += n.x;
    sy += n.y;
  }
  return [sx / ns.length, sy / ns.length];
}

/** Display target: Kalman position when tracking, otherwise the grid argmax estimate. */
export function targetPos(frame: Frame | null): { pos: Vec2; src: 'kalman' | 'est' } | null {
  if (!frame) return null;
  if (isTracking(frame.kalman)) return { pos: frame.kalman.pos, src: 'kalman' };
  if (frame.est) return { pos: frame.est, src: 'est' };
  return null;
}

function cell(g: Grid, ix: number, iy: number): number {
  const v = g.v[iy]?.[ix];
  return v != null && Number.isFinite(v) && v > 0 ? v : 0;
}

/**
 * Marching-squares iso-line at `level` over the grid (v[iy][ix], y up).
 * Saddle cells are resolved with a fixed pairing; good enough for display.
 */
export function contour(g: Grid, level: number): Segment[] {
  const n = g.n;
  const out: Segment[] = [];
  const w = (ix: number, iy: number): Vec2 => [g.x0 + ix * g.step, g.y0 + iy * g.step];
  const lerp = (p: number, q: number) => (q === p ? 0.5 : Math.min(1, Math.max(0, (level - p) / (q - p))));
  for (let iy = 0; iy < n - 1; iy++) {
    for (let ix = 0; ix < n - 1; ix++) {
      // Corners: a=(ix,iy) b=(ix+1,iy) c=(ix+1,iy+1) d=(ix,iy+1)
      const a = cell(g, ix, iy);
      const b = cell(g, ix + 1, iy);
      const c = cell(g, ix + 1, iy + 1);
      const d = cell(g, ix, iy + 1);
      const idx = (a > level ? 8 : 0) | (b > level ? 4 : 0) | (c > level ? 2 : 0) | (d > level ? 1 : 0);
      if (idx === 0 || idx === 15) continue;
      const B = w(ix + lerp(a, b), iy); // bottom edge a-b
      const R = w(ix + 1, iy + lerp(b, c)); // right edge b-c
      const T = w(ix + lerp(d, c), iy + 1); // top edge d-c
      const L = w(ix, iy + lerp(a, d)); // left edge a-d
      switch (idx) {
        case 1: case 14: out.push([L, T]); break;
        case 2: case 13: out.push([T, R]); break;
        case 3: case 12: out.push([L, R]); break;
        case 4: case 11: out.push([B, R]); break;
        case 5: out.push([B, R], [L, T]); break;
        case 6: case 9: out.push([B, T]); break;
        case 7: case 8: out.push([B, L]); break;
        case 10: out.push([B, L], [T, R]); break;
      }
    }
  }
  return out;
}

/** Highest-density-region thresholds, CEP50 and contours for a grid. Null if the grid is empty. */
export function gridStats(g: Grid | null | undefined): GridStats | null {
  if (!g) return null;
  const vals: number[] = [];
  let sum = 0;
  for (let iy = 0; iy < g.n; iy++) {
    for (let ix = 0; ix < g.n; ix++) {
      const v = cell(g, ix, iy);
      vals.push(v);
      sum += v;
    }
  }
  if (!(sum > 0)) return null;
  vals.sort((p, q) => q - p);
  let acc = 0;
  let t50 = 0;
  let t90 = 0;
  let n50 = 0;
  for (let i = 0; i < vals.length; i++) {
    acc += vals[i]!;
    if (!n50 && acc >= 0.5 * sum) {
      t50 = vals[i]!;
      n50 = i + 1;
    }
    if (acc >= 0.9 * sum) {
      t90 = vals[i]!;
      break;
    }
  }
  // Iso-lines sit just below the threshold so the threshold cells are inside.
  const eps = 1e-9;
  return {
    t50,
    t90,
    cep50: Math.sqrt((n50 * g.step * g.step) / Math.PI),
    c50: contour(g, t50 - eps),
    c90: contour(g, t90 - eps),
  };
}

export type LogLevel = 'crit' | 'warn' | 'ok' | 'info';
export interface LogEvent {
  level: LogLevel;
  msg: string;
}

/** Human-readable events from one frame to the next (first frame: prev = null). */
export function frameEvents(prev: Frame | null, next: Frame): LogEvent[] {
  const ev: LogEvent[] = [];
  const pk = prev?.kalman;
  const nk = next.kalman;
  const wasTracking = isTracking(pk);
  const tracking = isTracking(nk);
  if (tracking && !wasTracking) ev.push({ level: 'crit', msg: `EKF 추적 개시 · 측정 ${nk.used}개 사용` });
  if (!tracking && wasTracking) {
    const p = initProgress(nk);
    ev.push({ level: 'warn', msg: p ? `EKF 재초기화 · ${p.k}/${p.total}` : 'EKF 추적 중단' });
  }
  if (!prev || (prev.grid != null) !== (next.grid != null)) {
    if (next.grid == null) ev.push({ level: 'warn', msg: '확률 지도 없음 · 활성 노드 0' });
    else if (prev) ev.push({ level: 'ok', msg: '확률 지도 수신 재개' });
  }
  for (const [name, n] of Object.entries(next.nodes)) {
    const before = prev?.nodes[name];
    const on = isNodeActive(n);
    if (!before) {
      if (prev) ev.push({ level: 'info', msg: `노드 등록 · ${name}` });
      continue;
    }
    const was = isNodeActive(before);
    if (was && !on) ev.push({ level: 'warn', msg: `노드 ${name} 신호 끊김` });
    if (!was && on) ev.push({ level: 'ok', msg: `노드 ${name} 복귀 · ${n.rssi?.toFixed(0)} dBm` });
  }
  if (prev) {
    for (const name of Object.keys(prev.nodes)) {
      if (!(name in next.nodes)) ev.push({ level: 'warn', msg: `노드 제거 · ${name}` });
    }
  }
  return ev;
}
