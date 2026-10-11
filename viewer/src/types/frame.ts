import { z } from 'zod';

/**
 * Frame schema published by the Pi hub (`hub.py`), PRD §4.2.
 * z.object() strips unknown keys, so extra fields from newer hubs are ignored.
 */

const finite = z.number().finite();
const Vec2Schema = z.tuple([finite, finite]);

export const NodeSchema = z.object({
  x: finite,
  y: finite,
  rssi: finite.nullish(),
  d: finite.nullish(),
  fresh: z.boolean().catch(false),
});

export const GridSchema = z.object({
  x0: finite,
  y0: finite,
  step: finite.positive(),
  n: z.number().int().positive(),
  // v[iy][ix], 0..1; tolerate null cells (treated as 0 when drawing).
  v: z.array(z.array(finite.nullable())),
});

export const KalmanSchema = z.object({
  state: z.string(),
  pos: Vec2Schema.optional(),
  vel: Vec2Schema.optional(),
  cov: z.tuple([Vec2Schema, Vec2Schema]).optional(),
  used: z.number().int().nonnegative().optional(),
});

export const SlmSchema = z.object({
  dx: finite,
  dy: finite,
  reason: z.string().optional(),
});

export const FrameSchema = z.object({
  t: finite,
  nodes: z.record(z.string(), NodeSchema),
  grid: GridSchema.nullish(),
  est: Vec2Schema.nullish(),
  kalman: KalmanSchema.nullish(),
  slm: SlmSchema.nullish(),
});

export type Vec2 = z.infer<typeof Vec2Schema>;
export type NodeInfo = z.infer<typeof NodeSchema>;
export type Grid = z.infer<typeof GridSchema>;
export type Kalman = z.infer<typeof KalmanSchema>;
export type Slm = z.infer<typeof SlmSchema>;
export type Frame = z.infer<typeof FrameSchema>;

/** Kalman with all track fields present (state is not "init ..."). */
export type TrackingKalman = Kalman & { pos: Vec2; vel: Vec2; cov: [Vec2, Vec2]; used: number };

export type ParseResult = { ok: true; frame: Frame } | { ok: false; error: string };

/**
 * Parse one WebSocket text message. Python's json.dumps emits bare NaN/Infinity,
 * which JSON.parse rejects, so on failure we retry with those tokens mapped to null.
 */
export function parseFrame(text: string): ParseResult {
  let raw: unknown;
  try {
    raw = JSON.parse(text);
  } catch {
    try {
      raw = JSON.parse(text.replace(/-?\bInfinity\b|\bNaN\b/g, 'null'));
    } catch (e) {
      return { ok: false, error: `invalid JSON: ${(e as Error).message}` };
    }
  }
  const result = FrameSchema.safeParse(raw);
  if (!result.success) {
    const issue = result.error.issues[0];
    return { ok: false, error: `schema: ${issue?.path.join('.') || '(root)'}: ${issue?.message ?? 'invalid'}` };
  }
  return { ok: true, frame: result.data };
}

export function isTracking(k: Kalman | null | undefined): k is TrackingKalman {
  return !!k && !k.state.trim().startsWith('init') && !!k.pos && !!k.vel && !!k.cov && k.used !== undefined;
}

/** Parse "init k/K" into progress, or null if the state is not an init state. */
export function initProgress(k: Kalman | null | undefined): { k: number; total: number } | null {
  if (!k) return null;
  const m = /^\s*init\s+(\d+)\s*\/\s*(\d+)/.exec(k.state);
  if (!m) return k.state.trim().startsWith('init') ? { k: 0, total: 0 } : null;
  return { k: Number(m[1]), total: Number(m[2]) };
}

export function isNodeActive(n: NodeInfo): boolean {
  return n.fresh && n.rssi != null;
}
