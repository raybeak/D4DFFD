import { describe, expect, it } from 'vitest';
import { MockGenerator } from '../mock/generator';
import type { Frame } from '../types/frame';
import { DEFAULT_LAYERS, drawScene } from './scene';
import { DEFAULT_BOUNDS, makeTransform } from './transform';

/** Canvas 2D stand-in that accepts any call/property, for crash testing in Node. */
function fakeCtx(): CanvasRenderingContext2D {
  const handler: ProxyHandler<object> = {
    get: (t, p) => (p in t ? (t as Record<string | symbol, unknown>)[p] : () => undefined),
    set: (t, p, v) => {
      (t as Record<string | symbol, unknown>)[p] = v;
      return true;
    },
  };
  return new Proxy({}, handler) as CanvasRenderingContext2D;
}

const tf = makeTransform(DEFAULT_BOUNDS, 400, 400);
const draw = (frame: Frame | null) =>
  drawScene(fakeCtx(), tf, 400, 400, { frame, trail: [], layers: DEFAULT_LAYERS, predictDt: 1, heatmapBitmap: null });

describe('drawScene robustness', () => {
  it('handles no frame', () => {
    expect(() => draw(null)).not.toThrow();
  });

  it('handles all-null degraded frame (acceptance 5)', () => {
    expect(() =>
      draw({
        t: 1,
        nodes: { a: { x: -0.5, y: -0.5, rssi: null, d: null, fresh: false } },
        grid: null,
        est: null,
        kalman: { state: 'init 2/5' },
        slm: null,
      }),
    ).not.toThrow();
    expect(() => draw({ t: 1, nodes: {} })).not.toThrow();
  });

  it('draws mock frames with all layers', () => {
    const gen = new MockGenerator({ slm: true });
    for (let i = 0; i < 10; i++) expect(() => draw(gen.next())).not.toThrow();
  });
});
