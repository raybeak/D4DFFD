import { MockGenerator } from '../mock/generator';
import { parseFrame, type Frame } from '../types/frame';

export type ConnStatus = 'connecting' | 'live' | 'stale' | 'disconnected';

export interface HistoryEntry {
  /** Monotonic sequence number (survives ring-buffer eviction). */
  seq: number;
  frame: Frame;
  /** Local receive time, ms since epoch. */
  recvAt: number;
  /** Connection segment; bumps on every disconnect so the trail is not joined across gaps. */
  seg: number;
}

export interface StreamSnapshot {
  status: ConnStatus;
  mode: 'ws' | 'mock';
  url: string;
  history: readonly HistoryEntry[];
  frameCount: number;
  droppedCount: number;
  lastRecvAt: number | null;
  /** Gap between the last two received frames (ms). */
  intervalMs: number | null;
  /** When the next reconnect attempt fires (ms since epoch), if waiting. */
  retryAt: number | null;
  lastError: string | null;
}

export interface StreamConfig {
  url: string;
  mock: boolean;
  mockSlm?: boolean;
}

export const STALE_MS = 3000;
export const HISTORY_SIZE = 120;
const BACKOFF_START_MS = 500;
const BACKOFF_MAX_MS = 5000;
const MOCK_PERIOD_MS = 1000;

export function backoffDelay(attempt: number): number {
  return Math.min(BACKOFF_MAX_MS, BACKOFF_START_MS * 2 ** attempt);
}

/**
 * Read-only subscriber to the hub's frame broadcast (or the built-in mock).
 * Handles reconnect with exponential backoff, stale detection and a frame
 * ring buffer. Framework-agnostic; React binds via useFrameStream.
 */
export class FrameStream {
  private snap: StreamSnapshot;
  private listeners = new Set<() => void>();
  private ws: WebSocket | null = null;
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private mockTimer: ReturnType<typeof setInterval> | null = null;
  private staleTimer: ReturnType<typeof setInterval> | null = null;
  private attempt = 0;
  private seq = 0;
  private seg = 0;
  private closed = false;
  private readonly config: StreamConfig;

  constructor(config: StreamConfig) {
    this.config = config;
    this.snap = {
      status: 'connecting',
      mode: config.mock ? 'mock' : 'ws',
      url: config.url,
      history: [],
      frameCount: 0,
      droppedCount: 0,
      lastRecvAt: null,
      intervalMs: null,
      retryAt: null,
      lastError: null,
    };
  }

  getSnapshot = (): StreamSnapshot => this.snap;

  subscribe = (fn: () => void): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  start(): void {
    this.closed = false;
    this.staleTimer = setInterval(() => this.checkStale(), 250);
    if (this.config.mock) this.startMock();
    else this.connect();
  }

  stop(): void {
    this.closed = true;
    if (this.retryTimer) clearTimeout(this.retryTimer);
    if (this.mockTimer) clearInterval(this.mockTimer);
    if (this.staleTimer) clearInterval(this.staleTimer);
    this.retryTimer = this.mockTimer = this.staleTimer = null;
    if (this.ws) {
      this.ws.onopen = this.ws.onclose = this.ws.onerror = this.ws.onmessage = null;
      this.ws.close();
      this.ws = null;
    }
    this.listeners.clear();
  }

  /** Feed one raw text message (used by WebSocket and mock paths alike). */
  ingest(text: string): void {
    const res = parseFrame(text);
    if (!res.ok) {
      console.warn('[stream] dropped invalid frame:', res.error);
      this.update({ droppedCount: this.snap.droppedCount + 1, lastError: res.error });
      return;
    }
    const now = Date.now();
    const entry: HistoryEntry = { seq: this.seq++, frame: res.frame, recvAt: now, seg: this.seg };
    const history = this.snap.history.length >= HISTORY_SIZE
      ? [...this.snap.history.slice(this.snap.history.length - HISTORY_SIZE + 1), entry]
      : [...this.snap.history, entry];
    this.update({
      status: 'live',
      history,
      frameCount: this.snap.frameCount + 1,
      intervalMs: this.snap.lastRecvAt != null ? now - this.snap.lastRecvAt : null,
      lastRecvAt: now,
    });
  }

  private startMock(): void {
    const gen = new MockGenerator({ slm: this.config.mockSlm });
    // Round-trip through JSON so the mock exercises the exact parsing path.
    const tick = () => this.ingest(JSON.stringify(gen.next()));
    tick();
    this.mockTimer = setInterval(tick, MOCK_PERIOD_MS);
  }

  private connect(): void {
    if (this.closed) return;
    this.update({ retryAt: null });
    let ws: WebSocket;
    try {
      ws = new WebSocket(this.config.url);
    } catch (e) {
      // Malformed URL throws synchronously; treat like a failed connection.
      this.update({ status: 'disconnected', lastError: `bad URL: ${(e as Error).message}` });
      this.scheduleReconnect();
      return;
    }
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.update({ lastError: null, status: this.snap.status === 'live' ? 'live' : 'connecting' });
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') this.ingest(ev.data);
    };
    ws.onerror = () => {
      this.update({ lastError: 'WebSocket error' });
    };
    ws.onclose = () => {
      if (this.ws !== ws) return;
      this.ws = null;
      this.seg++;
      this.update({ status: 'disconnected' });
      this.scheduleReconnect();
    };
  }

  private scheduleReconnect(): void {
    if (this.closed) return;
    const delay = backoffDelay(this.attempt++);
    this.update({ retryAt: Date.now() + delay });
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  /** Flip live → stale when no frame arrived for STALE_MS. Called by an internal timer. */
  checkStale(now: number = Date.now()): void {
    const { status, lastRecvAt } = this.snap;
    if (status === 'live' && lastRecvAt != null && now - lastRecvAt > STALE_MS) {
      this.update({ status: 'stale' });
    }
  }

  private update(patch: Partial<StreamSnapshot>): void {
    this.snap = { ...this.snap, ...patch };
    for (const fn of this.listeners) fn();
  }
}
