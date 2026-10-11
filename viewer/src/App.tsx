import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { ErrorBoundary } from './ErrorBoundary';
import { MapCanvas } from './map/MapCanvas';
import type { LayerToggles } from './map/scene';
import { buildTrail } from './map/trail';
import { StatusPanel } from './panel/StatusPanel';
import { initialMock, initialWsUrl, loadPrefs, mockSlmEnabled, savePrefs, saveWsUrl, type Prefs } from './settings';
import { useFrameStream } from './ws/useFrameStream';

const LAYER_LABELS: [keyof LayerToggles, string][] = [
  ['heatmap', 'Heatmap'],
  ['rings', 'Rings'],
  ['est', 'Estimate'],
  ['ellipse', 'Ellipse'],
  ['trail', 'Trail'],
  ['prediction', 'Prediction'],
  ['slm', 'SLM'],
];

export default function App() {
  const [url, setUrl] = useState(initialWsUrl);
  const [urlDraft, setUrlDraft] = useState(url);
  const [mock, setMock] = useState(initialMock);
  const [mockSlm] = useState(mockSlmEnabled);
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  // Sequence number of the frame frozen on screen; null = follow live.
  const [pausedSeq, setPausedSeq] = useState<number | null>(null);

  const snap = useFrameStream({ url, mock, mockSlm });
  const { history } = snap;

  useEffect(() => savePrefs(prefs), [prefs]);

  // Resolve the displayed history index (clamped if the paused frame was evicted).
  const viewIndex = useMemo(() => {
    if (history.length === 0) return -1;
    if (pausedSeq == null) return history.length - 1;
    const first = history[0]!.seq;
    return Math.min(history.length - 1, Math.max(0, pausedSeq - first));
  }, [history, pausedSeq]);

  const entry = viewIndex >= 0 ? history[viewIndex]! : null;
  const frame = entry?.frame ?? null;
  const trail = useMemo(
    () => (viewIndex >= 0 ? buildTrail(history, viewIndex, prefs.trailLength) : []),
    [history, viewIndex, prefs.trailLength],
  );

  const paused = pausedSeq != null;

  const applyUrl = (e?: FormEvent) => {
    e?.preventDefault();
    const next = urlDraft.trim();
    if (!next || next === url) return;
    setUrl(next);
    saveWsUrl(next);
    setMock(false);
    setPausedSeq(null);
  };

  const togglePause = () => setPausedSeq(paused ? null : (entry?.seq ?? null));
  const setLayer = (key: keyof LayerToggles, on: boolean) =>
    setPrefs((p) => ({ ...p, layers: { ...p.layers, [key]: on } }));

  return (
    <div className="app">
      <header className="toolbar">
        <h1>RF Emitter Tracker</h1>
        <form className="url-form" onSubmit={applyUrl}>
          <label htmlFor="ws-url" className="sr-only">
            Hub WebSocket URL
          </label>
          <input
            id="ws-url"
            className="mono"
            value={urlDraft}
            onChange={(e) => setUrlDraft(e.target.value)}
            onBlur={() => applyUrl()}
            placeholder="ws://raspberrypi:8765"
            spellCheck={false}
            disabled={mock}
          />
          <button type="submit" disabled={mock}>
            Connect
          </button>
        </form>
        <label className="check">
          <input
            type="checkbox"
            checked={mock}
            onChange={(e) => {
              setMock(e.target.checked);
              setPausedSeq(null);
            }}
          />
          Mock
        </label>
        <button type="button" onClick={togglePause} disabled={!entry} aria-pressed={paused}>
          {paused ? '▶ Resume' : '❚❚ Pause'}
        </button>
      </header>

      <main className="main">
        <section className="map-col">
          <ErrorBoundary name="Map">
            <MapCanvas
              frame={frame}
              frameRecvAt={paused ? null : (entry?.recvAt ?? null)}
              trail={trail}
              layers={prefs.layers}
              predictDt={prefs.predictDt}
              smooth={prefs.smooth && !paused}
            />
          </ErrorBoundary>

          {paused && history.length > 0 && (
            <div className="replay">
              <label htmlFor="replay">
                Replay {viewIndex + 1}/{history.length}
              </label>
              <input
                id="replay"
                type="range"
                min={0}
                max={history.length - 1}
                value={viewIndex}
                onChange={(e) => setPausedSeq(history[Number(e.target.value)]?.seq ?? null)}
              />
            </div>
          )}

          <div className="layers" role="group" aria-label="Map layers">
            {LAYER_LABELS.map(([key, label]) => (
              <label key={key} className="check">
                <input type="checkbox" checked={prefs.layers[key]} onChange={(e) => setLayer(key, e.target.checked)} />
                {label}
              </label>
            ))}
            <label className="check">
              <input
                type="checkbox"
                checked={prefs.smooth}
                onChange={(e) => setPrefs((p) => ({ ...p, smooth: e.target.checked }))}
              />
              Smooth
            </label>
            <label className="num">
              Δt
              <input
                type="number"
                min={0.1}
                max={10}
                step={0.1}
                value={prefs.predictDt}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (v > 0) setPrefs((p) => ({ ...p, predictDt: v }));
                }}
              />
              s
            </label>
            <label className="num">
              Trail
              <input
                type="number"
                min={0}
                max={120}
                step={1}
                value={prefs.trailLength}
                onChange={(e) => {
                  const v = Math.round(Number(e.target.value));
                  if (v >= 0) setPrefs((p) => ({ ...p, trailLength: Math.min(120, v) }));
                }}
              />
            </label>
          </div>
        </section>

        <ErrorBoundary name="Status panel">
          <StatusPanel snap={snap} frame={frame} paused={paused} />
        </ErrorBoundary>
      </main>
    </div>
  );
}
