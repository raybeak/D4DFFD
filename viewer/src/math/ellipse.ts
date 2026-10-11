/** Result of decomposing a 2x2 position covariance into a confidence ellipse. */
export interface Ellipse {
  /** Semi-major axis (m). */
  rx: number;
  /** Semi-minor axis (m). */
  ry: number;
  /** Rotation of the major axis, radians CCW from +x (world frame, y up). */
  angle: number;
}

/**
 * Eigen-decompose a symmetric 2x2 covariance [[a, b], [b, c]] and return the
 * k-sigma ellipse (semi-axes k*sqrt(lambda_i)). Off-diagonals are averaged to
 * symmetrize; tiny negative eigenvalues from rounding are clamped to 0.
 * Returns null if the input is not finite.
 */
export function covarianceEllipse(cov: readonly (readonly number[])[], k = 2): Ellipse | null {
  const a = cov[0]?.[0];
  const c = cov[1]?.[1];
  const b01 = cov[0]?.[1];
  const b10 = cov[1]?.[0];
  if (![a, c, b01, b10, k].every((v) => typeof v === 'number' && Number.isFinite(v))) return null;
  const b = ((b01 as number) + (b10 as number)) / 2;
  const aa = a as number;
  const cc = c as number;

  const mean = (aa + cc) / 2;
  const radius = Math.hypot((aa - cc) / 2, b);
  const l1 = Math.max(0, mean + radius);
  const l2 = Math.max(0, mean - radius);
  // Major eigenvector angle; atan2(0, 0) = 0 for isotropic covariance.
  const angle = 0.5 * Math.atan2(2 * b, aa - cc);

  return { rx: k * Math.sqrt(l1), ry: k * Math.sqrt(l2), angle };
}
