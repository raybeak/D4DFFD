import { describe, expect, it } from 'vitest';
import { boundsForFrame, DEFAULT_BOUNDS, makeTransform } from './transform';

describe('makeTransform', () => {
  const tf = makeTransform(DEFAULT_BOUNDS, 500, 500, { left: 0, right: 0, top: 0, bottom: 0 });
  const [cx, cy] = tf.toPx(0, 0);

  it('maps origin to canvas centre', () => {
    expect(cx).toBeCloseTo(250);
    expect(cy).toBeCloseTo(250);
  });

  it('+x is to the right of centre (acceptance 6)', () => {
    const [px, py] = tf.toPx(0.3, 0);
    expect(px).toBeGreaterThan(cx);
    expect(py).toBeCloseTo(cy);
  });

  it('+y is above centre, i.e. smaller canvas y (acceptance 6)', () => {
    const [px, py] = tf.toPx(0, 0.3);
    expect(py).toBeLessThan(cy);
    expect(px).toBeCloseTo(cx);
  });

  it('toWorld inverts toPx', () => {
    const [x, y] = tf.toWorld(...tf.toPx(0.12, -0.34));
    expect(x).toBeCloseTo(0.12);
    expect(y).toBeCloseTo(-0.34);
  });

  it('keeps square aspect in a non-square canvas', () => {
    const t = makeTransform(DEFAULT_BOUNDS, 800, 400, { left: 0, right: 0, top: 0, bottom: 0 });
    expect(t.size).toBe(400);
    expect(t.left).toBe(200);
  });
});

describe('boundsForFrame', () => {
  it('falls back without a frame or content', () => {
    expect(boundsForFrame(null)).toEqual(DEFAULT_BOUNDS);
    expect(boundsForFrame({ t: 0, nodes: {} })).toEqual(DEFAULT_BOUNDS);
  });

  it('uses grid extent', () => {
    const b = boundsForFrame({ t: 0, nodes: {}, grid: { x0: -0.6, y0: -0.6, step: 0.05, n: 25, v: [] } });
    expect(b.xmin).toBeCloseTo(-0.6);
    expect(b.xmax).toBeCloseTo(0.6);
  });

  it('keeps the default view when grid is null', () => {
    const node = { x: 0.5, y: -0.5, rssi: null, d: null, fresh: false };
    expect(boundsForFrame({ t: 0, nodes: { a: node }, grid: null })).toEqual(DEFAULT_BOUNDS);
  });
});
