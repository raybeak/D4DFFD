import { describe, expect, it } from 'vitest';
import type { Frame, Grid } from '../types/frame';
import { bearingDeg, cardinal, contour, frameEvents, gridStats, nodeCentroid, targetPos } from './metrics';
import { heatColor } from './tactical';

function grid(n: number, f: (x: number, y: number) => number, x0 = -0.6, step = 0.05): Grid {
  const v: number[][] = [];
  for (let iy = 0; iy < n; iy++) {
    const row: number[] = [];
    for (let ix = 0; ix < n; ix++) row.push(f(x0 + ix * step, x0 + iy * step));
    v.push(row);
  }
  return { x0, y0: x0, step, n, v };
}

const NODES: Frame['nodes'] = {
  a: { x: -0.5, y: -0.5, rssi: -40, d: 0.5, fresh: true },
  b: { x: 0.5, y: -0.5, rssi: -45, d: 0.6, fresh: true },
  c: { x: 0.5, y: 0.5, rssi: -50, d: 0.7, fresh: true },
  d: { x: -0.5, y: 0.5, rssi: null, d: null, fresh: false },
};

function frame(over: Partial<Frame> = {}): Frame {
  return { t: 0, nodes: NODES, grid: null, est: null, kalman: null, slm: null, ...over };
}

describe('bearingDeg', () => {
  it('is 0 for +y, 90 for +x, clockwise', () => {
    expect(bearingDeg([0, 0], [0, 1])).toBeCloseTo(0);
    expect(bearingDeg([0, 0], [1, 0])).toBeCloseTo(90);
    expect(bearingDeg([0, 0], [0, -1])).toBeCloseTo(180);
    expect(bearingDeg([0, 0], [-1, 0])).toBeCloseTo(270);
  });
  it('maps to cardinal labels', () => {
    expect(cardinal(0)).toMatch(/^N /);
    expect(cardinal(359)).toMatch(/^N /);
    expect(cardinal(135)).toMatch(/^SE/);
  });
});

describe('gridStats', () => {
  it('returns null for missing or all-zero grids', () => {
    expect(gridStats(null)).toBeNull();
    expect(gridStats(grid(5, () => 0))).toBeNull();
  });

  it('CEP50 of a single hot cell is the equal-area radius of one cell', () => {
    const g = grid(5, (x, y) => (Math.abs(x + 0.5) < 1e-9 && Math.abs(y + 0.5) < 1e-9 ? 1 : 0));
    const s = gridStats(g)!;
    expect(s.cep50).toBeCloseTo(Math.sqrt((0.05 * 0.05) / Math.PI));
  });

  it('wider blobs have larger CEP50, and the 50% contour encloses the peak', () => {
    const blob = (sig: number) => grid(25, (x, y) => Math.exp(-((x - 0.1) ** 2 + y ** 2) / (2 * sig * sig)));
    const narrow = gridStats(blob(0.05))!;
    const wide = gridStats(blob(0.15))!;
    expect(wide.cep50).toBeGreaterThan(narrow.cep50);
    expect(narrow.t90).toBeLessThanOrEqual(narrow.t50);
    expect(narrow.c50.length).toBeGreaterThan(0);
    const xs = narrow.c50.flatMap(([a, b]) => [a[0], b[0]]);
    expect(Math.min(...xs)).toBeLessThan(0.1);
    expect(Math.max(...xs)).toBeGreaterThan(0.1);
  });

  it('tolerates null and NaN cells', () => {
    const g: Grid = { x0: 0, y0: 0, step: 1, n: 2, v: [[null, 1], [Number.NaN as unknown as number, 0.5]] };
    const s = gridStats(g)!;
    expect(Number.isFinite(s.cep50)).toBe(true);
  });
});

describe('contour', () => {
  it('places iso-line crossings in world coordinates (y up)', () => {
    // Value rises with y: level 0.5 sits halfway between rows 0 and 1.
    const g = grid(3, (_x, y) => (y > -0.58 ? 1 : 0));
    const segs = contour(g, 0.5);
    expect(segs.length).toBe(2);
    for (const [a, b] of segs) {
      expect(a[1]).toBeCloseTo(-0.575);
      expect(b[1]).toBeCloseTo(-0.575);
    }
  });
});

describe('targetPos / nodeCentroid', () => {
  it('prefers the Kalman position when tracking, else est, else null', () => {
    const k = { state: 'track', pos: [0.1, 0.2] as [number, number], vel: [0, 0] as [number, number], cov: [[1, 0], [0, 1]] as [[number, number], [number, number]], used: 3 };
    expect(targetPos(frame({ kalman: k, est: [0, 0] }))).toEqual({ pos: [0.1, 0.2], src: 'kalman' });
    expect(targetPos(frame({ kalman: { state: 'init 2/5' }, est: [0.3, 0] }))).toEqual({ pos: [0.3, 0], src: 'est' });
    expect(targetPos(frame())).toBeNull();
    expect(targetPos(null)).toBeNull();
  });
  it('averages node positions', () => {
    expect(nodeCentroid(frame())).toEqual([0, 0]);
    expect(nodeCentroid(frame({ nodes: {} }))).toEqual([0, 0]);
  });
});

describe('frameEvents', () => {
  const tracking = { state: 'track', pos: [0, 0] as [number, number], vel: [0, 0] as [number, number], cov: [[1, 0], [0, 1]] as [[number, number], [number, number]], used: 3 };

  it('reports track start and node down / recovery', () => {
    const a = frame({ kalman: { state: 'init 4/5' } });
    const b = frame({
      kalman: tracking,
      nodes: { ...NODES, a: { ...NODES.a!, fresh: false }, d: { x: -0.5, y: 0.5, rssi: -60, d: 1, fresh: true } },
    });
    const msgs = frameEvents(a, b).map((e) => e.msg).join('\n');
    expect(msgs).toMatch(/추적 개시/);
    expect(msgs).toMatch(/노드 a 신호 끊김/);
    expect(msgs).toMatch(/노드 d 복귀/);
  });

  it('warns when the grid disappears and on track loss', () => {
    const a = frame({ kalman: tracking, grid: grid(2, () => 1) });
    const ev = frameEvents(a, frame({ kalman: { state: 'init 1/5' } }));
    expect(ev.some((e) => /재초기화 · 1\/5/.test(e.msg))).toBe(true);
    expect(ev.some((e) => /확률 지도 없음/.test(e.msg))).toBe(true);
  });

  it('is quiet for identical frames', () => {
    const f = frame({ grid: grid(2, () => 1) });
    expect(frameEvents(f, f)).toEqual([]);
  });
});

describe('heatColor', () => {
  it('is transparent below the cut and opaque-ish at the peak', () => {
    expect(heatColor(0)[3]).toBe(0);
    expect(heatColor(0.05)[3]).toBe(0);
    expect(heatColor(1)[3]).toBeGreaterThan(200);
    expect(heatColor(Number.NaN)[3]).toBe(0);
  });
});
