import { afterEach, describe, expect, it, vi } from 'vitest';
import { MockGenerator } from '../mock/generator';
import { backoffDelay, FrameStream, HISTORY_SIZE, STALE_MS } from './frameStream';

afterEach(() => {
  vi.useRealTimers();
});

describe('backoffDelay', () => {
  it('starts at 0.5 s, doubles, caps at 5 s', () => {
    expect([0, 1, 2, 3, 4, 5, 10].map(backoffDelay)).toEqual([500, 1000, 2000, 4000, 5000, 5000, 5000]);
  });
});

describe('FrameStream ingest', () => {
  it('goes live on a valid frame, drops invalid ones and keeps the last frame', () => {
    const s = new FrameStream({ url: 'ws://x', mock: false });
    const gen = new MockGenerator();
    s.ingest(JSON.stringify(gen.next()));
    expect(s.getSnapshot().status).toBe('live');
    const before = s.getSnapshot().history;
    s.ingest('{"bad": true}');
    expect(s.getSnapshot().history).toBe(before);
    expect(s.getSnapshot().droppedCount).toBe(1);
  });

  it('caps history at the ring buffer size', () => {
    const s = new FrameStream({ url: 'ws://x', mock: false });
    const gen = new MockGenerator();
    for (let i = 0; i < HISTORY_SIZE + 10; i++) s.ingest(JSON.stringify(gen.next()));
    const h = s.getSnapshot().history;
    expect(h.length).toBe(HISTORY_SIZE);
    expect(h[h.length - 1]!.seq).toBe(HISTORY_SIZE + 9);
  });

  it('mock mode emits 1 Hz frames', () => {
    vi.useFakeTimers();
    const s = new FrameStream({ url: '', mock: true });
    s.start();
    expect(s.getSnapshot().status).toBe('live');
    vi.advanceTimersByTime(2000);
    expect(s.getSnapshot().frameCount).toBe(3);
    s.stop();
  });

  it('becomes stale after STALE_MS without frames', () => {
    const s = new FrameStream({ url: 'ws://x', mock: false });
    s.ingest(JSON.stringify(new MockGenerator().next()));
    const t = s.getSnapshot().lastRecvAt!;
    s.checkStale(t + STALE_MS - 1);
    expect(s.getSnapshot().status).toBe('live');
    s.checkStale(t + STALE_MS + 1);
    expect(s.getSnapshot().status).toBe('stale');
  });
});
