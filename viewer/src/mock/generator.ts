// Mock hub frame generator (PRD F4). Shared by the in-browser mock mode and
// scripts/mock-server.mjs, so it must stay free of non-erasable TS syntax and of
// runtime imports (Node runs it via type stripping).
import type { Frame, Kalman, NodeInfo, Vec2 } from '../types/frame';

export interface MockOptions {
  /** Random source in [0, 1); injectable for tests. */
  rng?: () => number;
  /** Orbit radius (m). */
  radius?: number;
  /** Orbit period (s). */
  period?: number;
  /** Number of "init k/K" frames before tracking. */
  initFrames?: number;
  /** Emit a placeholder `slm` suggestion. */
  slm?: boolean;
  /** Probability per frame that a node goes down (when none is down). */
  dropoutProb?: number;
}

export const A0 = -34.5;
export const PATH_LOSS_N = 2.5;
const RSSI_SIGMA = 2;
// Wider sigma for the displayed likelihood so the blob is visible.
const LIK_SIGMA = 4;
const GRID_N = 25;
const GRID_STEP = 0.05;
const GRID_X0 = -0.6;

const NODE_LAYOUT: Record<string, Vec2> = {
  raspberrypi: [-0.5, -0.5],
  nu87a: [0.5, -0.5],
  nu87b: [0.5, 0.5],
  unoq: [-0.5, 0.5],
};

export function rssiAt(d: number): number {
  return A0 - 10 * PATH_LOSS_N * Math.log10(Math.max(d, 0.05));
}

export function distFromRssi(rssi: number): number {
  return Math.pow(10, (A0 - rssi) / (10 * PATH_LOSS_N));
}

export class MockGenerator {
  private readonly rng: () => number;
  private readonly radius: number;
  private readonly omega: number;
  private readonly initFrames: number;
  private readonly slm: boolean;
  private readonly dropoutProb: number;

  private k = 0;
  private down: { name: string; until: number } | null = null;
  private pos: Vec2 | null = null;
  private vel: Vec2 = [0, 0];

  constructor(opts: MockOptions = {}) {
    this.rng = opts.rng ?? Math.random;
    this.radius = opts.radius ?? 0.3;
    this.omega = (2 * Math.PI) / (opts.period ?? 20);
    this.initFrames = opts.initFrames ?? 5;
    this.slm = opts.slm ?? false;
    this.dropoutProb = opts.dropoutProb ?? 0.05;
  }

  /** True emitter position at elapsed time `ts` (s). Starts at (radius, 0), CCW. */
  truth(ts: number): Vec2 {
    return [this.radius * Math.cos(this.omega * ts), this.radius * Math.sin(this.omega * ts)];
  }

  /** Produce the next frame; `t` is the frame timestamp in unix seconds. */
  next(t: number = Date.now() / 1000): Frame {
    const step = this.k++;
    const truth = this.truth(step);
    this.updateDropout(step);

    const nodes: Record<string, NodeInfo> = {};
    for (const [name, [x, y]] of Object.entries(NODE_LAYOUT)) {
      if (this.down?.name === name) {
        nodes[name] = { x, y, rssi: null, d: null, fresh: false };
        continue;
      }
      const rssi = rssiAt(Math.hypot(truth[0] - x, truth[1] - y)) + this.gauss() * RSSI_SIGMA;
      nodes[name] = { x, y, rssi: round(rssi, 1), d: round(distFromRssi(rssi), 3), fresh: true };
    }

    const alive = Object.values(nodes).filter((n) => n.fresh && n.rssi != null);
    const { grid, argmax } = this.likelihood(alive);
    const est = alive.length >= 3 ? argmax : null;

    return {
      t: round(t, 3),
      nodes,
      grid,
      est,
      kalman: this.kalman(step, est, alive.length),
      slm: this.slm && this.pos ? this.slmHint() : null,
    };
  }

  private updateDropout(step: number): void {
    if (this.down && step >= this.down.until) this.down = null;
    // Keep the first frames clean so init progress is easy to see.
    if (!this.down && step > this.initFrames && this.rng() < this.dropoutProb) {
      const names = Object.keys(NODE_LAYOUT);
      const name = names[Math.floor(this.rng() * names.length)] ?? names[0]!;
      this.down = { name, until: step + 3 + Math.floor(this.rng() * 4) };
    }
  }

  private likelihood(alive: NodeInfo[]): { grid: Frame['grid']; argmax: Vec2 | null } {
    if (alive.length === 0) return { grid: null, argmax: null };
    const logL: number[][] = [];
    let best = -Infinity;
    let argmax: Vec2 = [0, 0];
    for (let iy = 0; iy < GRID_N; iy++) {
      const row: number[] = [];
      const y = GRID_X0 + iy * GRID_STEP;
      for (let ix = 0; ix < GRID_N; ix++) {
        const x = GRID_X0 + ix * GRID_STEP;
        let l = 0;
        for (const n of alive) {
          const r = (rssiAt(Math.hypot(x - n.x, y - n.y)) - (n.rssi as number)) / LIK_SIGMA;
          l -= 0.5 * r * r;
        }
        row.push(l);
        if (l > best) {
          best = l;
          argmax = [round(x, 3), round(y, 3)];
        }
      }
      logL.push(row);
    }
    const v = logL.map((row) => row.map((l) => round(Math.exp(l - best), 4)));
    return { grid: { x0: GRID_X0, y0: GRID_X0, step: GRID_STEP, n: GRID_N, v }, argmax };
  }

  /** Low-pass position + differenced velocity; only imitates the real EKF. */
  private kalman(step: number, est: Vec2 | null, alive: number): Kalman {
    if (step < this.initFrames) return { state: `init ${step + 1}/${this.initFrames}` };
    const prev = this.pos;
    if (est) {
      this.pos = prev ? [prev[0] + 0.5 * (est[0] - prev[0]), prev[1] + 0.5 * (est[1] - prev[1])] : est;
    } else if (prev) {
      this.pos = [prev[0] + this.vel[0], prev[1] + this.vel[1]];
    } else {
      this.pos = [0, 0];
    }
    if (prev) {
      const raw: Vec2 = [this.pos[0] - prev[0], this.pos[1] - prev[1]];
      this.vel = [0.6 * this.vel[0] + 0.4 * raw[0], 0.6 * this.vel[1] + 0.4 * raw[1]];
    }
    // Fake covariance: grows when fewer nodes are used, rotates with the heading.
    const base = alive >= 4 ? 0.002 : alive === 3 ? 0.004 : 0.012;
    const ang = Math.atan2(this.vel[1], this.vel[0]);
    const major = base * 2.2;
    const minor = base;
    const c = Math.cos(ang);
    const s = Math.sin(ang);
    const cov: [Vec2, Vec2] = [
      [round(major * c * c + minor * s * s, 6), round((major - minor) * c * s, 6)],
      [round((major - minor) * c * s, 6), round(major * s * s + minor * c * c, 6)],
    ];
    return {
      state: 'track',
      pos: [round(this.pos[0], 4), round(this.pos[1], 4)],
      vel: [round(this.vel[0], 4), round(this.vel[1], 4)],
      cov,
      used: est ? alive : 0,
    };
  }

  private slmHint(): Frame['slm'] {
    // Velocity rotated slightly toward the orbit centre, as a stand-in suggestion.
    const [vx, vy] = this.vel;
    const a = 0.35;
    return {
      dx: round(1.5 * (vx * Math.cos(a) - vy * Math.sin(a)), 4),
      dy: round(1.5 * (vx * Math.sin(a) + vy * Math.cos(a)), 4),
      reason: 'mock: curving trajectory',
    };
  }

  /** Standard normal via Box-Muller. */
  private gauss(): number {
    const u = Math.max(this.rng(), 1e-12);
    const v = this.rng();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
}

function round(v: number, digits: number): number {
  const p = 10 ** digits;
  return Math.round(v * p) / p;
}
