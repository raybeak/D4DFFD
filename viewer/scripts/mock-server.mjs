#!/usr/bin/env node
// Stand-in for the Pi hub: broadcasts mock frames (PRD §4.2 schema) over
// WebSocket at 1 Hz so the real network path can be tested without hardware.
//
//   node scripts/mock-server.mjs [--port 8765] [--slm] [--period-ms 1000]
//
// Requires Node >= 22.18 (imports the TypeScript generator via type stripping).
import { WebSocketServer } from 'ws';
import { MockGenerator } from '../src/mock/generator.ts';

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i >= 0 && process.argv[i + 1] && !process.argv[i + 1].startsWith('--') ? process.argv[i + 1] : fallback;
}

const port = Number(arg('port', process.env.PORT ?? 8765));
const periodMs = Number(arg('period-ms', 1000));
const slm = process.argv.includes('--slm');
if (!Number.isInteger(port) || port <= 0 || port > 65535) {
  console.error(`invalid --port: ${port}`);
  process.exit(1);
}
if (!(periodMs > 0)) {
  console.error(`invalid --period-ms: ${periodMs}`);
  process.exit(1);
}

const gen = new MockGenerator({ slm });
const wss = new WebSocketServer({ port });

wss.on('listening', () => console.log(`mock hub broadcasting on ws://localhost:${port} every ${periodMs} ms${slm ? ' (with slm)' : ''}`));
wss.on('error', (err) => {
  console.error('server error:', err.message);
  process.exit(1);
});
wss.on('connection', (ws, req) => {
  console.log(`client connected: ${req.socket.remoteAddress} (${wss.clients.size} total)`);
  // Viewer is read-only; ignore anything clients send.
  ws.on('message', () => {});
  ws.on('close', () => console.log(`client disconnected (${wss.clients.size} total)`));
});

const timer = setInterval(() => {
  const msg = JSON.stringify(gen.next());
  for (const client of wss.clients) {
    if (client.readyState === client.OPEN) client.send(msg);
  }
}, periodMs);

function shutdown() {
  clearInterval(timer);
  for (const client of wss.clients) client.terminate();
  wss.close(() => process.exit(0));
}
process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);
