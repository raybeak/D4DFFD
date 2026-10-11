import { isTracking } from '../types/frame';
import type { HistoryEntry } from '../ws/frameStream';
import type { TrailPoint } from './layers/kalman';

/**
 * Last `n` Kalman positions up to and including history index `upto`.
 * Points keep their connection segment so reconnect gaps are not joined.
 */
export function buildTrail(history: readonly HistoryEntry[], upto: number, n: number): TrailPoint[] {
  const out: TrailPoint[] = [];
  for (let i = Math.min(upto, history.length - 1); i >= 0 && out.length < n; i--) {
    const e = history[i]!;
    const k = e.frame.kalman;
    if (isTracking(k)) out.push({ pos: k.pos, seg: e.seg });
  }
  return out.reverse();
}
