import { describe, expect, it } from 'vitest';
import { initProgress, isTracking, parseFrame } from './frame';

const SAMPLE = {
  t: 1760140000.123,
  nodes: {
    raspberrypi: { x: -0.5, y: -0.5, rssi: -41.0, d: 0.62, fresh: true },
    nu87a: { x: 0.5, y: -0.5, rssi: null, d: null, fresh: false },
  },
  grid: { x0: -0.6, y0: -0.6, step: 0.05, n: 2, v: [[0, 0.01], [0.5, 1]] },
  est: [0.12, -0.05],
  kalman: { state: 'track', pos: [0.11, -0.04], vel: [0.02, 0.01], cov: [[0.004, 0], [0, 0.005]], used: 3 },
  slm: null,
};

describe('parseFrame', () => {
  it('accepts the PRD sample frame', () => {
    const r = parseFrame(JSON.stringify(SAMPLE));
    expect(r.ok).toBe(true);
    if (r.ok) expect(isTracking(r.frame.kalman)).toBe(true);
  });

  it('ignores unknown fields', () => {
    const r = parseFrame(JSON.stringify({ ...SAMPLE, extra: { foo: 1 }, nodes: { a: { ...SAMPLE.nodes.raspberrypi, snr: 3 } } }));
    expect(r.ok).toBe(true);
    if (r.ok) expect('extra' in r.frame).toBe(false);
  });

  it('accepts the all-null degraded frame (acceptance 5)', () => {
    const r = parseFrame(
      JSON.stringify({
        t: 1,
        nodes: { a: { x: 0, y: 0, rssi: null, d: null, fresh: false } },
        grid: null,
        est: null,
        kalman: { state: 'init 2/5' },
        slm: null,
      }),
    );
    expect(r.ok).toBe(true);
    if (r.ok) {
      expect(isTracking(r.frame.kalman)).toBe(false);
      expect(initProgress(r.frame.kalman)).toEqual({ k: 2, total: 5 });
    }
  });

  it('tolerates Python NaN/Infinity tokens', () => {
    const r = parseFrame('{"t": 1, "nodes": {"a": {"x": 0, "y": 0, "rssi": NaN, "d": Infinity, "fresh": true}}}');
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.frame.nodes.a?.rssi).toBeNull();
  });

  it('rejects invalid JSON and schema violations', () => {
    expect(parseFrame('not json').ok).toBe(false);
    expect(parseFrame(JSON.stringify({ nodes: {} })).ok).toBe(false);
    expect(parseFrame(JSON.stringify({ ...SAMPLE, est: [1] })).ok).toBe(false);
  });
});

describe('initProgress', () => {
  it('parses init state and ignores track', () => {
    expect(initProgress({ state: 'init 3/5' })).toEqual({ k: 3, total: 5 });
    expect(initProgress({ state: 'track' })).toBeNull();
    expect(initProgress(null)).toBeNull();
  });
});
