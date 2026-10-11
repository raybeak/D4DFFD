import { describe, expect, it } from 'vitest';
import { covarianceEllipse } from './ellipse';

const noNaN = (e: ReturnType<typeof covarianceEllipse>) => {
  expect(e).not.toBeNull();
  for (const v of Object.values(e!)) expect(Number.isFinite(v)).toBe(true);
};

describe('covarianceEllipse', () => {
  it('diagonal cov: axes along x/y, 2-sigma semi-axes', () => {
    const e = covarianceEllipse([[0.04, 0], [0, 0.01]]);
    noNaN(e);
    expect(e!.rx).toBeCloseTo(0.4);
    expect(e!.ry).toBeCloseTo(0.2);
    expect(e!.angle).toBeCloseTo(0);
  });

  it('diagonal cov with larger y variance: major axis vertical', () => {
    const e = covarianceEllipse([[0.01, 0], [0, 0.04]]);
    noNaN(e);
    expect(e!.rx).toBeCloseTo(0.4);
    expect(e!.ry).toBeCloseTo(0.2);
    expect(Math.abs(e!.angle)).toBeCloseTo(Math.PI / 2);
  });

  it('45° rotated cov', () => {
    // R(45°) diag(0.04, 0.01) R^T
    const e = covarianceEllipse([[0.025, 0.015], [0.015, 0.025]]);
    noNaN(e);
    expect(e!.rx).toBeCloseTo(0.4);
    expect(e!.ry).toBeCloseTo(0.2);
    expect(e!.angle).toBeCloseTo(Math.PI / 4);
  });

  it('-45° rotated cov', () => {
    const e = covarianceEllipse([[0.025, -0.015], [-0.015, 0.025]]);
    noNaN(e);
    expect(e!.angle).toBeCloseTo(-Math.PI / 4);
  });

  it('singular cov (det ≈ 0): zero minor axis, no NaN', () => {
    const e = covarianceEllipse([[0.01, 0.01], [0.01, 0.01]]);
    noNaN(e);
    expect(e!.rx).toBeCloseTo(2 * Math.sqrt(0.02));
    expect(e!.ry).toBeCloseTo(0);
    expect(e!.angle).toBeCloseTo(Math.PI / 4);
  });

  it('slightly negative eigenvalue from rounding is clamped', () => {
    const e = covarianceEllipse([[0.01, 0.0100001], [0.0100001, 0.01]]);
    noNaN(e);
    expect(e!.ry).toBeGreaterThanOrEqual(0);
  });

  it('isotropic and zero cov', () => {
    noNaN(covarianceEllipse([[0.01, 0], [0, 0.01]]));
    const z = covarianceEllipse([[0, 0], [0, 0]]);
    noNaN(z);
    expect(z!.rx).toBe(0);
  });

  it('non-finite input returns null', () => {
    expect(covarianceEllipse([[NaN, 0], [0, 1]])).toBeNull();
    expect(covarianceEllipse([[1, 0]])).toBeNull();
  });
});
