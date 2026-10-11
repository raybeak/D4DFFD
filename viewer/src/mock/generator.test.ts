import { describe, expect, it } from 'vitest';
import { isTracking, parseFrame } from '../types/frame';
import { distFromRssi, MockGenerator, rssiAt } from './generator';

// Deterministic LCG so tests are reproducible.
function lcg(seed = 1) {
  let s = seed >>> 0;
  return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32);
}

describe('MockGenerator', () => {
  it('emits schema-valid frames', () => {
    const gen = new MockGenerator({ rng: lcg(), slm: true });
    for (let i = 0; i < 60; i++) {
      const r = parseFrame(JSON.stringify(gen.next(1000 + i)));
      expect(r.ok).toBe(true);
    }
  });

  it('first 5 frames are "init k/5" without track fields', () => {
    const gen = new MockGenerator({ rng: lcg() });
    for (let i = 1; i <= 5; i++) {
      const k = gen.next().kalman;
      expect(k?.state).toBe(`init ${i}/5`);
      expect(k?.pos).toBeUndefined();
    }
    expect(isTracking(gen.next().kalman)).toBe(true);
  });

  it('target starts at (0.3, 0) and moves CCW', () => {
    const gen = new MockGenerator();
    const [x0, y0] = gen.truth(0);
    expect(x0).toBeCloseTo(0.3);
    expect(y0).toBeCloseTo(0);
    expect(gen.truth(5)[1]).toBeGreaterThan(0);
  });

  it('eventually drops a node (fresh=false, rssi null)', () => {
    const gen = new MockGenerator({ rng: lcg(7), dropoutProb: 0.5 });
    let sawDown = false;
    for (let i = 0; i < 40 && !sawDown; i++) {
      sawDown = Object.values(gen.next().nodes).some((n) => !n.fresh && n.rssi === null && n.d === null);
    }
    expect(sawDown).toBe(true);
  });

  it('grid argmax estimate tracks the target', () => {
    const gen = new MockGenerator({ rng: () => 0.25, dropoutProb: 0 }); // v=0.25 -> cos(pi/2) = 0 noise
    const f = gen.next();
    expect(f.grid?.n).toBe(25);
    expect(f.est).not.toBeNull();
    expect(Math.hypot(f.est![0] - 0.3, f.est![1])).toBeLessThan(0.1);
  });

  it('RSSI model round-trips', () => {
    expect(rssiAt(1)).toBeCloseTo(-34.5);
    expect(distFromRssi(rssiAt(0.7))).toBeCloseTo(0.7);
  });
});
