import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react';
import { ErrorBoundary } from '../ErrorBoundary';
import { buildTrail } from '../map/trail';
import { initialMock, initialWsUrl, mockSlmEnabled, saveWsUrl } from '../settings';
import { initProgress, isNodeActive, isTracking, type Frame, type NodeInfo } from '../types/frame';
import type { ConnStatus, HistoryEntry } from '../ws/frameStream';
import { useFrameStream } from '../ws/useFrameStream';
import { bearingDeg, cardinal, frameEvents, gridStats, nodeCentroid, targetPos, type LogLevel } from './metrics';
import { DEFAULT_TACTICAL_LAYERS, TacticalMap, type TacticalLayers } from './TacticalMap';

const KEY_PREFS = 'rfviewer.heatmap.prefs';
const TRAIL_LEN = 30;
const PREDICT_DT = 1;
const LOG_MAX = 60;

interface LogItem {
  id: number;
  time: string;
  level: LogLevel;
  msg: string;
}

const LAYER_LABELS: [keyof TacticalLayers, string][] = [
  ['heatmap', '히트맵'],
  ['contours', '50/90% 등고선'],
  ['rings', '거리 링'],
  ['est', 'Grid 추정'],
  ['ellipse', '2σ 타원'],
  ['trail', '항적'],
  ['prediction', '예측 화살표'],
];

const STATUS_TEXT: Record<ConnStatus, string> = {
  connecting: 'CONNECTING',
  live: 'LIVE',
  stale: 'STALE',
  disconnected: 'DISCONNECTED',
};

const hms = () => new Date().toLocaleTimeString('en-GB', { hour12: false, timeZone: 'Asia/Seoul' });
const fmt3 = (deg: number) => String(Math.round(deg) % 360).padStart(3, '0');

function loadLayers(): TacticalLayers {
  try {
    const raw = window.localStorage.getItem(KEY_PREFS);
    if (raw) return { ...DEFAULT_TACTICAL_LAYERS, ...(JSON.parse(raw) as Partial<TacticalLayers>) };
  } catch (e) {
    console.warn('[heatmap] ignoring stored prefs', e);
  }
  return DEFAULT_TACTICAL_LAYERS;
}

function saveLayers(l: TacticalLayers): void {
  try {
    window.localStorage.setItem(KEY_PREFS, JSON.stringify(l));
  } catch (e) {
    console.warn('[heatmap] could not persist prefs', e);
  }
}

function useClock(): string {
  const [now, setNow] = useState(hms);
  useEffect(() => {
    const id = setInterval(() => setNow(hms()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

export default function HeatmapApp() {
  const [url, setUrl] = useState(initialWsUrl);
  const [urlDraft, setUrlDraft] = useState(url);
  const [mock, setMock] = useState(initialMock);
  const [mockSlm] = useState(mockSlmEnabled);
  const [layers, setLayers] = useState(loadLayers);
  const [pausedSeq, setPausedSeq] = useState<number | null>(null);
  const [modal, setModal] = useState(false);
  const [log, setLog] = useState<LogItem[]>([]);
  const clock = useClock();

  const snap = useFrameStream({ url, mock, mockSlm });
  const { history, status } = snap;

  useEffect(() => saveLayers(layers), [layers]);

  const viewIndex = useMemo(() => {
    if (history.length === 0) return -1;
    if (pausedSeq == null) return history.length - 1;
    return Math.min(history.length - 1, Math.max(0, pausedSeq - history[0]!.seq));
  }, [history, pausedSeq]);
  const entry = viewIndex >= 0 ? history[viewIndex]! : null;
  const frame = entry?.frame ?? null;
  const paused = pausedSeq != null;
  const trail = useMemo(() => (viewIndex >= 0 ? buildTrail(history, viewIndex, TRAIL_LEN) : []), [history, viewIndex]);
  const stats = useMemo(() => gridStats(frame?.grid), [frame]);

  // Event log: diff each newly received frame against the previous one, plus status changes.
  const idRef = useRef(0);
  const lastSeqRef = useRef<number | null>(null);
  const push = (items: { level: LogLevel; msg: string }[]) => {
    if (items.length === 0) return;
    const time = hms();
    setLog((l) => [...items.map((it) => ({ ...it, time, id: idRef.current++ })).reverse(), ...l].slice(0, LOG_MAX));
  };
  useEffect(() => push([{ level: 'ok', msg: '시스템 기동 · 히트맵 뷰어' }]), []);
  useEffect(() => {
    const last = history[history.length - 1];
    if (!last || last.seq === lastSeqRef.current) return;
    const prev = history.length > 1 ? history[history.length - 2]!.frame : null;
    lastSeqRef.current = last.seq;
    push(frameEvents(prev, last.frame));
  }, [history]);
  const prevStatus = useRef<ConnStatus | null>(null);
  useEffect(() => {
    if (prevStatus.current === status) return;
    prevStatus.current = status;
    const where = mock ? 'MOCK' : url;
    if (status === 'live') push([{ level: 'ok', msg: `데이터 수신 · ${where}` }]);
    else if (status === 'stale') push([{ level: 'warn', msg: '3초 이상 프레임 없음 · STALE' }]);
    else if (status === 'disconnected') push([{ level: 'crit', msg: '연결 끊김 · 자동 재연결 중' }]);
    else push([{ level: 'info', msg: `연결 시도 · ${where}` }]);
  }, [status, mock, url]);

  const applyUrl = () => {
    const next = urlDraft.trim();
    if (!next) return;
    if (next !== url) {
      setUrl(next);
      saveWsUrl(next);
    }
    setMock(false);
    setPausedSeq(null);
  };
  const togglePause = () => setPausedSeq(paused ? null : (entry?.seq ?? null));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      const k = e.key.toLowerCase();
      if (k === 'escape') setModal(false);
      else if (k === 'c' || k === 'h') setModal((m) => !m);
      else if (k === ' ') {
        e.preventDefault();
        togglePause();
      } else if (k === 'f') {
        if (document.fullscreenElement) void document.exitFullscreen();
        else document.documentElement.requestFullscreen().catch((err) => console.warn('[heatmap] fullscreen', err));
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  const nodes = frame ? Object.entries(frame.nodes) : [];
  const activeCount = nodes.filter(([, n]) => isNodeActive(n)).length;

  return (
    <div className="tapp">
      <div className="banner">RF EMITTER TRACKER · 4-NODE RSSI FUSION · HEATMAP VIEW</div>
      <header className="top">
        <div className="brand">
          <Logo />
          <div>
            <div className="b1">
              RF<em>·</em>HEATMAP
            </div>
            <div className="b2">분산 RSSI 확률 위치추정 · EKF 추적</div>
          </div>
        </div>
        <div className="mid">
          {paused && <span className="pill warn">PAUSED · SPACE</span>}
          {mock && <span className="pill">MOCK</span>}
        </div>
        <div className="meta">
          <div className="clock">
            {clock}
            <small>KST</small>
          </div>
          <button type="button" className={`chip ${status}`} onClick={() => setModal(true)} title="C: 연결 설정">
            <i />
            <span>
              {STATUS_TEXT[status]}
              {mock ? ' · MOCK' : ''}
            </span>
          </button>
        </div>
      </header>

      <main className="tmain">
        <section className="col">
          <div className="panel nodesP">
            <div className="ph">
              <span>
                <b>NODES</b> · 센서 노드
              </span>
              <span className="tag">
                {activeCount} / {nodes.length} ACTIVE
              </span>
            </div>
            <div className="ncards">
              {nodes.length === 0 && <div className="empty">노드 데이터 없음</div>}
              {nodes.map(([name, n]) => (
                <NodeCard key={name} name={name} node={n} history={history} upto={viewIndex} />
              ))}
            </div>
          </div>
        </section>

        <section className="mapcol">
          <ErrorBoundary name="Map">
            <TacticalMap
              frame={frame}
              recvAt={paused ? null : (entry?.recvAt ?? null)}
              trail={layers.trail ? trail : []}
              stats={stats}
              layers={layers}
              predictDt={PREDICT_DT}
            />
          </ErrorBoundary>
          {paused && history.length > 0 && (
            <div className="replay">
              <label htmlFor="replay">
                REPLAY {viewIndex + 1}/{history.length}
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
        </section>

        <section className="col">
          <ErrorBoundary name="Threat">
            <ThreatPanel frame={frame} cep50={stats?.cep50 ?? null} />
          </ErrorBoundary>
          <ErrorBoundary name="Compass">
            <CompassPanel frame={frame} cep50={stats?.cep50 ?? null} />
          </ErrorBoundary>
          <div className="panel logP">
            <div className="ph">
              <span>
                <b>EVENT LOG</b> · 상황 일지
              </span>
              <span className="tag">
                {snap.frameCount} FR · {snap.droppedCount} DROP
              </span>
            </div>
            <ol className="log">
              {log.map((it) => (
                <li key={it.id} className={it.level}>
                  <time>{it.time}</time>
                  <span>{it.msg}</span>
                </li>
              ))}
            </ol>
          </div>
        </section>
      </main>

      {modal && (
        <div className="modal" onClick={(e) => e.target === e.currentTarget && setModal(false)}>
          <div className="panel" role="dialog" aria-label="연결 설정">
            <div className="ph">
              <span>
                <b>CONFIG</b> · 연결 설정 / 레이어
              </span>
              <span className="tag">ESC 닫기</span>
            </div>
            <div className="mb">
              <h3>Hub WebSocket</h3>
              <form
                className="row"
                onSubmit={(e) => {
                  e.preventDefault();
                  applyUrl();
                  setModal(false);
                }}
              >
                <input
                  className="url"
                  value={urlDraft}
                  onChange={(e) => setUrlDraft(e.target.value)}
                  placeholder="ws://raspberrypi:8765"
                  spellCheck={false}
                />
                <button type="submit" className="btn pri">
                  연결
                </button>
              </form>
              <div className="row">
                <button
                  type="button"
                  className={`btn ${mock ? 'pri' : ''}`}
                  onClick={() => {
                    setMock((m) => !m);
                    setPausedSeq(null);
                  }}
                >
                  {mock ? 'Mock 끄기' : 'Mock 시작'}
                </button>
                <button type="button" className="btn" onClick={togglePause} disabled={!entry}>
                  {paused ? '▶ 재개' : '❚❚ 일시정지'}
                </button>
                <button type="button" className="btn" onClick={() => setModal(false)}>
                  닫기
                </button>
              </div>
              <div className="dim">
                상태 <b>{STATUS_TEXT[status]}</b> · 마지막 간격{' '}
                {snap.intervalMs != null ? `${(snap.intervalMs / 1000).toFixed(2)} s` : '—'}
                {snap.lastError && <> · 오류 {snap.lastError}</>}
              </div>
              <h3>레이어</h3>
              <div className="layers">
                {LAYER_LABELS.map(([key, label]) => (
                  <label key={key} className="check">
                    <input
                      type="checkbox"
                      checked={layers[key]}
                      onChange={(e) => setLayers((l) => ({ ...l, [key]: e.target.checked }))}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <h3>단축키</h3>
              <div className="keys">
                <kbd>Space</kbd>
                <span>일시정지 / 재개 (최근 120 프레임 되감기)</span>
                <kbd>C · H</kbd>
                <span>이 창</span>
                <kbd>F</kbd>
                <span>전체화면</span>
              </div>
              <div className="dim">
                URL 옵션: <code>?ws=ws://host:8765</code> · <code>?mock=1</code> · <code>?slm=1</code>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Logo() {
  return (
    <svg width="38" height="38" viewBox="0 0 38 38" aria-hidden="true">
      <circle cx="19" cy="19" r="17" fill="none" stroke="#2f4036" />
      <circle cx="19" cy="19" r="11" fill="none" stroke="#2f4036" />
      <path d="M19 19 L19 2 A17 17 0 0 1 33.7 10.5 Z" fill="rgba(255,178,30,.22)" />
      <line x1="19" y1="19" x2="33.7" y2="10.5" stroke="#ffb21e" strokeWidth="1.5" />
      <rect x="3.5" y="3.5" width="5" height="5" fill="#8ddc97" />
      <rect x="29.5" y="3.5" width="5" height="5" fill="#8ddc97" />
      <rect x="3.5" y="29.5" width="5" height="5" fill="#8ddc97" />
      <rect x="29.5" y="29.5" width="5" height="5" fill="#8ddc97" />
      <circle cx="25" cy="12" r="2.2" fill="#ff4a3a" />
    </svg>
  );
}

/** Map RSSI (-90..-30 dBm) to a 0..1 bar. */
const rssiBar = (r: number) => Math.min(1, Math.max(0, (r + 90) / 60));

function NodeCard({
  name,
  node,
  history,
  upto,
}: {
  name: string;
  node: NodeInfo;
  history: readonly HistoryEntry[];
  upto: number;
}) {
  const on = isNodeActive(node);
  const series = useMemo(() => {
    const out: (number | null)[] = [];
    for (let i = Math.max(0, upto - 59); i <= upto; i++) {
      const n = history[i]?.frame.nodes[name];
      out.push(n && isNodeActive(n) ? n.rssi! : null);
    }
    return out;
  }, [history, upto, name]);

  return (
    <div className={`ncard ${on ? 'on' : 'off'}`}>
      <div className="nh">
        <span>
          <i />
          {name}
        </span>
        <span className="pos">
          ({node.x.toFixed(2)}, {node.y.toFixed(2)})
        </span>
      </div>
      <div className="nvals">
        <div>
          <label>RSSI</label>
          <div className="v">
            {on ? node.rssi!.toFixed(0) : '—'}
            <small>dBm</small>
          </div>
        </div>
        <div>
          <label>거리 · d</label>
          <div className="v">
            {on && node.d != null ? node.d.toFixed(2) : '—'}
            <small>m</small>
          </div>
        </div>
      </div>
      <div className="pbar">
        <i style={{ width: `${on ? rssiBar(node.rssi!) * 100 : 0}%` }} />
      </div>
      <Sparkline values={series} />
      <div className="nst">{on ? 'FRESH · 측정 수신' : node.fresh ? 'RSSI NULL' : 'STALE · 신호 없음'}</div>
    </div>
  );
}

function Sparkline({ values }: { values: readonly (number | null)[] }) {
  const W = 200;
  const H = 30;
  const lo = -90;
  const hi = -30;
  const n = Math.max(2, values.length);
  let d = '';
  let pen = false;
  values.forEach((v, i) => {
    if (v == null) {
      pen = false;
      return;
    }
    const x = (i / (n - 1)) * W;
    const y = H - ((Math.min(hi, Math.max(lo, v)) - lo) / (hi - lo)) * H;
    d += `${pen ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`;
    pen = true;
  });
  return (
    <svg className="spark" viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" aria-hidden="true">
      <path d={d} fill="none" stroke="currentColor" strokeWidth="1.4" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

function ThreatPanel({ frame, cep50 }: { frame: Frame | null; cep50: number | null }) {
  const tgt = targetPos(frame);
  const k = frame?.kalman;
  const tracking = isTracking(k);
  const init = initProgress(k);
  const total = frame ? Object.keys(frame.nodes).length : 0;
  const c = nodeCentroid(frame);

  let state = 'STANDBY';
  let name = 'NO CONTACT';
  let sub = `RF 감시 중 · ${total}개 노드`;
  let cls = '';
  if (tgt) {
    cls = 'hot';
    state = tracking ? 'TRACKING' : 'ESTIMATE';
    name = 'RF EMITTER';
    sub = tracking
      ? `EKF 추적 · 측정 ${k.used}/${total} 사용`
      : init
        ? `EKF 초기화 ${init.k}/${init.total} · grid 추정만`
        : 'grid argmax 추정';
  } else if (init) {
    cls = 'unk';
    state = 'INIT';
    sub = `EKF 초기화 ${init.k}/${init.total}`;
  }

  const brg = tgt ? bearingDeg(c, tgt.pos) : null;
  const rng = tgt ? Math.hypot(tgt.pos[0] - c[0], tgt.pos[1] - c[1]) : null;
  const speed = tracking ? Math.hypot(k.vel[0], k.vel[1]) : null;
  const heading = tracking && speed! > 1e-4 ? bearingDeg([0, 0], k.vel) : null;

  return (
    <div className={`panel threat ${cls}`}>
      <div className="ph">
        <span>
          <b>TARGET</b> · 표적
        </span>
        <span className="tag">{state}</span>
      </div>
      <div className="th-id">
        <svg width="46" height="46" viewBox="-23 -23 46 46" aria-hidden="true">
          <path d="M0 -19 L19 0 L0 19 L-19 0 Z" fill="rgba(255,74,58,.16)" stroke="#ff4a3a" strokeWidth="1.8" />
          <path d="M-9 -2 L0 4 L9 -2" fill="none" stroke="#ff4a3a" strokeWidth="2" strokeLinejoin="round" />
        </svg>
        <div>
          <b>{name}</b>
          <span>{sub}</span>
        </div>
      </div>
      {init && init.total > 0 && !tracking && (
        <div className="initbar" aria-label={`EKF init ${init.k}/${init.total}`}>
          <i style={{ width: `${(init.k / init.total) * 100}%` }} />
        </div>
      )}
      <div className="th-grid">
        <div>
          <label>방위 · BEARING</label>
          <div className="v">
            {brg != null ? fmt3(brg) : '---'}
            <small>°</small>
          </div>
          <small>{brg != null ? `${cardinal(brg)} · 노드 중심 기준` : '노드 중심 기준'}</small>
        </div>
        <div>
          <label>거리 · RANGE</label>
          <div className="v">
            {rng != null ? rng.toFixed(2) : '---'}
            <small>m</small>
          </div>
          <small>노드 중심 기준</small>
        </div>
        <div>
          <label>위치 오차 · CEP50</label>
          <div className="v">
            {cep50 != null ? `±${Math.round(cep50 * 100)}` : '---'}
            <small>cm</small>
          </div>
          <small>50% 확률 반경 (grid)</small>
        </div>
        <div>
          <label>속도 · SPEED</label>
          <div className="v">
            {speed != null ? speed.toFixed(2) : '---'}
            <small>m/s</small>
          </div>
          <small>{heading != null ? `진행 ${fmt3(heading)}° · ${cardinal(heading)}` : '진행 방향 —'}</small>
        </div>
      </div>
      <div className="predrow">
        <label>위치 · POSITION</label>
        <div className="pt">
          {tracking ? (
            <>
              EKF <b>({k.pos[0].toFixed(2)}, {k.pos[1].toFixed(2)})</b>
            </>
          ) : (
            'EKF —'
          )}
          {' · '}
          {frame?.est ? (
            <>
              grid <b>({frame.est[0].toFixed(2)}, {frame.est[1].toFixed(2)})</b>
            </>
          ) : (
            'grid —'
          )}
        </div>
      </div>
      {frame?.slm && (
        <div className="advice">
          <label>SLM 제안</label>
          <div className="at">
            Δ ({frame.slm.dx.toFixed(2)}, {frame.slm.dy.toFixed(2)}) m{frame.slm.reason ? ` · ${frame.slm.reason}` : ''}
          </div>
        </div>
      )}
    </div>
  );
}

function CompassPanel({ frame, cep50 }: { frame: Frame | null; cep50: number | null }) {
  const tgt = targetPos(frame);
  const c = nodeCentroid(frame);
  const brg = tgt ? bearingDeg(c, tgt.pos) : null;
  const rng = tgt ? Math.hypot(tgt.pos[0] - c[0], tgt.pos[1] - c[1]) : 0;
  const half = cep50 != null && tgt ? Math.min(75, Math.max(4, (Math.atan2(cep50, Math.max(rng, 0.02)) * 180) / Math.PI)) : null;

  // Animate the needle along the shortest arc.
  const [needle, setNeedle] = useState(0);
  const target = useRef<number | null>(null);
  target.current = brg;
  useEffect(() => {
    let raf = 0;
    const tick = () => {
      setNeedle((n) => {
        const t = target.current;
        if (t == null) return n;
        const d = ((t - n + 540) % 360) - 180;
        return Math.abs(d) < 0.05 ? t : n + d * 0.14;
      });
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const ticks = useMemo(() => {
    const out: ReactElement[] = [];
    for (let d = 0; d < 360; d += 5) {
      const a = (d * Math.PI) / 180;
      const r2 = d % 30 === 0 ? 92 : d % 10 === 0 ? 97 : 100;
      out.push(
        <line
          key={d}
          x1={104 * Math.sin(a)}
          y1={-104 * Math.cos(a)}
          x2={r2 * Math.sin(a)}
          y2={-r2 * Math.cos(a)}
          stroke={d % 30 === 0 ? '#8b988f' : '#3a4a40'}
          strokeWidth={d % 30 === 0 ? 1.4 : 1}
        />,
      );
    }
    (
      [
        ['N', 0, '#ff6a5c'],
        ['E', 90, '#e3e9e0'],
        ['S', 180, '#e3e9e0'],
        ['W', 270, '#e3e9e0'],
      ] as const
    ).forEach(([ch, d, fill]) => {
      const a = (d * Math.PI) / 180;
      out.push(
        <text key={ch} x={78 * Math.sin(a)} y={-78 * Math.cos(a) + 6} textAnchor="middle" className="cmp-l" fill={fill}>
          {ch}
        </text>,
      );
    });
    return out;
  }, []);

  const wedge = (h: number) => {
    const r = 96;
    const a = (h * Math.PI) / 180;
    const p = (ang: number) => `${(r * Math.sin(ang)).toFixed(2)} ${(-r * Math.cos(ang)).toFixed(2)}`;
    return `M0 0 L${p(-a)} A${r} ${r} 0 0 1 ${p(a)} Z`;
  };

  return (
    <div className="panel">
      <div className="ph">
        <span>
          <b>COMPASS</b> · 방위
        </span>
        <span className="tag">+y = N</span>
      </div>
      <div className="cp">
        <svg viewBox="-110 -110 220 220" aria-hidden="true">
          <circle r="104" fill="rgba(6,9,7,.8)" stroke="#2a382f" />
          <circle r="72" fill="none" stroke="#1c2620" strokeDasharray="2 4" />
          {ticks}
          {brg != null && (
            <g transform={`rotate(${needle.toFixed(2)})`}>
              {half != null && <path d={wedge(half)} fill="rgba(255,74,58,.16)" stroke="rgba(255,74,58,.45)" />}
              <line x1="0" y1="0" x2="0" y2="-84" stroke="#ff4a3a" strokeWidth="2.4" />
              <path d="M0 -98 L7 -82 L-7 -82 Z" fill="#ff4a3a" />
              <line x1="0" y1="0" x2="0" y2="26" stroke="#5a675e" strokeWidth="2" />
            </g>
          )}
          <circle r="4" fill="#e3e9e0" />
        </svg>
        <div className="ro">
          <label>표적 방위 · BRG</label>
          <div className="bb">
            {brg != null ? fmt3(brg) : '---'}
            <small>°</small>
          </div>
          <div className="cd">{brg != null ? cardinal(brg) : '대기'}</div>
          <div className="ce">{half != null ? `방위 오차 ± ${Math.round(half)}° · ${rng.toFixed(2)} m` : '방위 오차 ± —'}</div>
        </div>
      </div>
    </div>
  );
}
