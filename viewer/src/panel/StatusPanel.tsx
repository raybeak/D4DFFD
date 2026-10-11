import { useEffect, useState } from 'react';
import { initProgress, isNodeActive, isTracking, type Frame } from '../types/frame';
import type { ConnStatus, StreamSnapshot } from '../ws/frameStream';

interface Props {
  snap: StreamSnapshot;
  /** Frame currently shown (latest, or the replayed one when paused). */
  frame: Frame | null;
  paused: boolean;
}

const STATUS_LABEL: Record<ConnStatus, { icon: string; text: string }> = {
  connecting: { icon: '○', text: 'Connecting' },
  live: { icon: '●', text: 'Live' },
  stale: { icon: '◐', text: 'Stale' },
  disconnected: { icon: '✕', text: 'Disconnected' },
};

/** Re-render periodically so ages and countdowns tick between frames. */
function useNow(periodMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), periodMs);
    return () => clearInterval(id);
  }, [periodMs]);
  return now;
}

const fmt = (v: number | null | undefined, digits = 2) => (v == null || !Number.isFinite(v) ? '—' : v.toFixed(digits));
const fmtXY = (p: readonly number[] | null | undefined) => (p ? `(${fmt(p[0])}, ${fmt(p[1])})` : '—');

export function StatusPanel({ snap, frame, paused }: Props) {
  const now = useNow(250);
  const st = STATUS_LABEL[snap.status];
  const age = snap.lastRecvAt != null ? Math.max(0, (now - snap.lastRecvAt) / 1000) : null;
  const retryIn = snap.retryAt != null ? Math.max(0, (snap.retryAt - now) / 1000) : null;

  const nodes = frame ? Object.entries(frame.nodes) : [];
  const activeCount = nodes.filter(([, n]) => isNodeActive(n)).length;
  const k = frame?.kalman;
  const tracking = isTracking(k);
  const init = initProgress(k);
  const speed = tracking ? Math.hypot(k.vel[0], k.vel[1]) : null;
  // Compass-style heading: 0° = +y, clockwise.
  const heading = tracking && speed! > 1e-6 ? ((Math.atan2(k.vel[0], k.vel[1]) * 180) / Math.PI + 360) % 360 : null;

  const warnings: string[] = [];
  if (frame) {
    if (nodes.length > 0 && activeCount === 0) warnings.push('No active nodes');
    if (!frame.grid) warnings.push('No heatmap (grid null)');
    if (!frame.est) warnings.push('No estimate (< 3 nodes)');
    if (!k) warnings.push('No Kalman data');
  }

  return (
    <aside className="panel">
      <section>
        <h2>Connection</h2>
        <div className={`status status-${snap.status}`} role="status" aria-live="polite">
          <span className="status-icon" aria-hidden>{st.icon}</span>
          {st.text}
          {paused && <span className="badge">PAUSED</span>}
        </div>
        <dl className="kv">
          <dt>Source</dt>
          <dd className="mono ellipsis" title={snap.mode === 'mock' ? 'built-in mock' : snap.url}>
            {snap.mode === 'mock' ? 'built-in mock' : snap.url}
          </dd>
          <dt>Last frame</dt>
          <dd className="mono">{frame ? `${new Date(frame.t * 1000).toLocaleTimeString()} (Pi)` : '—'}</dd>
          <dt>Age</dt>
          <dd className="mono">{age != null ? `${age.toFixed(1)} s` : '—'}</dd>
          <dt>Interval</dt>
          <dd className="mono">{snap.intervalMs != null ? `${snap.intervalMs} ms` : '—'}</dd>
          <dt>Frames</dt>
          <dd className="mono">
            {snap.frameCount}
            {snap.droppedCount > 0 && <span className="warn"> ({snap.droppedCount} invalid)</span>}
          </dd>
          {snap.status === 'disconnected' && retryIn != null && (
            <>
              <dt>Retry</dt>
              <dd className="mono">in {retryIn.toFixed(1)} s</dd>
            </>
          )}
        </dl>
        {snap.lastError && snap.status !== 'live' && <p className="warn small">{snap.lastError}</p>}
      </section>

      <section>
        <h2>Kalman</h2>
        {tracking ? (
          <div className="kalman-state">
            <span className="tag tag-track">TRACK</span>
            <span className="mono">
              used {k.used}/{nodes.length}
            </span>
          </div>
        ) : init ? (
          <div className="kalman-state">
            <span className="tag tag-init">INIT</span>
            <span className="mono">{k?.state}</span>
            {init.total > 0 && (
              <progress max={init.total} value={init.k} aria-label="Kalman initialisation progress" />
            )}
          </div>
        ) : (
          <div className="kalman-state">
            <span className="tag">{k ? k.state : 'n/a'}</span>
          </div>
        )}
        <dl className="kv">
          <dt>Est (grid)</dt>
          <dd className="mono">{fmtXY(frame?.est)}</dd>
          <dt>Kalman pos</dt>
          <dd className="mono">{tracking ? fmtXY(k.pos) : '—'}</dd>
          <dt>Speed</dt>
          <dd className="mono">{speed != null ? `${fmt(speed, 3)} m/s` : '—'}</dd>
          <dt>Heading</dt>
          <dd className="mono">{heading != null ? `${heading.toFixed(0)}° (0°=+y, CW)` : '—'}</dd>
          {frame?.slm && (
            <>
              <dt>SLM</dt>
              <dd className="mono">
                Δ({fmt(frame.slm.dx)}, {fmt(frame.slm.dy)}){frame.slm.reason ? ` · ${frame.slm.reason}` : ''}
              </dd>
            </>
          )}
        </dl>
      </section>

      <section>
        <h2>
          Nodes <span className="muted">{activeCount}/{nodes.length} active</span>
        </h2>
        {nodes.length === 0 ? (
          <p className="muted small">No nodes in frame.</p>
        ) : (
          <ul className="nodes">
            {nodes.map(([name, n]) => {
              const active = isNodeActive(n);
              return (
                <li key={name} className={active ? 'node' : 'node node-down'}>
                  <span className="node-mark" aria-hidden>{active ? '◆' : '◇'}</span>
                  <span className="node-name">{name}</span>
                  <span className="mono">{n.rssi != null ? `${n.rssi.toFixed(1)} dBm` : '—'}</span>
                  <span className="mono">{n.d != null ? `${n.d.toFixed(2)} m` : '—'}</span>
                  <span className="node-fresh">{active ? 'fresh' : 'down'}</span>
                </li>
              );
            })}
          </ul>
        )}
      </section>

      {warnings.length > 0 && (
        <section>
          <h2>Warnings</h2>
          <ul className="warnings">
            {warnings.map((w) => (
              <li key={w}>⚠ {w}</li>
            ))}
          </ul>
        </section>
      )}
    </aside>
  );
}
