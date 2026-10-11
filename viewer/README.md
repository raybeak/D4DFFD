# RF Emitter Tracker — Heatmap Viewer

Read-only React viewer for the Pi hub (`hub.py`) WebSocket frames: likelihood heatmap,
sensor nodes, and the EKF track (covariance ellipse, velocity arrow, trail). See `../prd.md`.

Requires Node >= 22.18 (the mock server imports the TypeScript generator via type stripping).

```bash
npm install
npm run dev                       # http://localhost:5173/?mock=1  (built-in mock)
npm run mock-server               # ws://localhost:8765 stand-in for the Pi
                                  # then open /?ws=ws://localhost:8765
npm test                          # vitest (ellipse math, parsing, transform, mock, stream)
npm run build                     # static, offline-capable files in dist/
```

## URL / options

| Query        | Effect                                                         |
|--------------|----------------------------------------------------------------|
| `?ws=<url>`  | Hub URL. Priority: `?ws=` → URL saved from the UI → `VITE_WS_URL` → `ws://raspberrypi:8765` |
| `?mock=1`    | Use the in-browser mock generator (also a toolbar toggle)      |
| `?slm=1`     | Mock also emits a placeholder `slm` arrow (`mock-server --slm` for the server) |

`mock-server.mjs` flags: `--port 8765`, `--period-ms 1000`, `--slm`.

## Heatmap view (`heatmap.html`)

A second page with the tactical look of `../히트맵.html`, but driven by the same hub frames
(no change to `hub.py`). Same connection logic, mock, and `?ws=` / `?mock=1` / `?slm=1` options.

```bash
npm run dev    # http://localhost:5173/heatmap.html?mock=1
```

- Large heatmap (amber→red→white), 50% / 90% highest-density contours, CEP50 from the grid.
- Node cards with RSSI sparklines; target panel (bearing/range from the node centroid, speed, heading); compass; event log.
- Keys: `C`/`H` settings and layer toggles, `Space` pause/replay, `F` fullscreen.
- Code: `src/heatmap/` (`metrics.ts` = pure math + tests, `tactical.ts` = pure canvas layers).

## Layout

- `src/types/frame.ts` — zod schema; invalid frames are dropped (last good frame stays on screen).
- `src/ws/frameStream.ts` — connect, backoff reconnect (0.5 s → 5 s), stale after 3 s, 120-frame ring buffer.
- `src/map/layers/*.ts`, `src/map/scene.ts` — pure canvas drawing, no React (reusable for other renderers).
- `src/map/transform.ts` — world (m, y up) ↔ canvas (px, y down).
- `src/math/ellipse.ts` — 2×2 covariance → 2σ ellipse.
- `src/mock/generator.ts` — mock frames (shared by browser mock and `scripts/mock-server.mjs`).
