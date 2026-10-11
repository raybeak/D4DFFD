import { DEFAULT_LAYERS, type LayerToggles } from './map/scene';

export const DEFAULT_WS_URL = 'ws://raspberrypi:8765';
const KEY_URL = 'rfviewer.wsUrl';
const KEY_PREFS = 'rfviewer.prefs';

export interface Prefs {
  layers: LayerToggles;
  predictDt: number;
  trailLength: number;
  smooth: boolean;
}

export const DEFAULT_PREFS: Prefs = { layers: DEFAULT_LAYERS, predictDt: 1, trailLength: 30, smooth: true };

// localStorage can throw (private mode, blocked storage); fall back to defaults.
function load(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch (e) {
    console.warn('[settings] localStorage unavailable', e);
    return null;
  }
}

function save(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch (e) {
    console.warn('[settings] could not persist', key, e);
  }
}

/**
 * Initial WebSocket URL. Priority: ?ws= → URL saved from the UI → VITE_WS_URL → default.
 */
export function initialWsUrl(): string {
  const q = new URLSearchParams(window.location.search).get('ws');
  return q || load(KEY_URL) || import.meta.env.VITE_WS_URL || DEFAULT_WS_URL;
}

export function saveWsUrl(url: string): void {
  save(KEY_URL, url);
}

export function initialMock(): boolean {
  const q = new URLSearchParams(window.location.search).get('mock');
  return q === '1' || q === 'true';
}

export function mockSlmEnabled(): boolean {
  return new URLSearchParams(window.location.search).get('slm') === '1';
}

export function loadPrefs(): Prefs {
  const raw = load(KEY_PREFS);
  if (!raw) return DEFAULT_PREFS;
  try {
    const p = JSON.parse(raw) as Partial<Prefs>;
    return {
      layers: { ...DEFAULT_LAYERS, ...(p.layers ?? {}) },
      predictDt: typeof p.predictDt === 'number' && p.predictDt > 0 ? p.predictDt : DEFAULT_PREFS.predictDt,
      trailLength:
        typeof p.trailLength === 'number' && p.trailLength >= 0 ? Math.round(p.trailLength) : DEFAULT_PREFS.trailLength,
      smooth: typeof p.smooth === 'boolean' ? p.smooth : DEFAULT_PREFS.smooth,
    };
  } catch (e) {
    console.warn('[settings] ignoring corrupt prefs', e);
    return DEFAULT_PREFS;
  }
}

export function savePrefs(p: Prefs): void {
  save(KEY_PREFS, JSON.stringify(p));
}
