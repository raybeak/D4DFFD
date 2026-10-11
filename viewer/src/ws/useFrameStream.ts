import { useEffect, useState, useSyncExternalStore } from 'react';
import { FrameStream, type StreamConfig, type StreamSnapshot } from './frameStream';

/**
 * Subscribe to the hub (or mock) for the given config. Changing url/mock tears
 * down the old connection and immediately opens a new one.
 */
export function useFrameStream(config: StreamConfig): StreamSnapshot {
  const { url, mock, mockSlm } = config;
  const [stream, setStream] = useState(() => new FrameStream(config));

  useEffect(() => {
    const s = new FrameStream({ url, mock, mockSlm });
    setStream(s);
    s.start();
    return () => s.stop();
  }, [url, mock, mockSlm]);

  return useSyncExternalStore(stream.subscribe, stream.getSnapshot);
}
