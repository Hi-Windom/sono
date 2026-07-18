export const API_BASE = '/api/v1';
export const HEALTH_URL = '/health';
export const CHUNK_SIZE = 5 * 1024 * 1024;

const LOG_ENABLED = true;

export function log(tag: string, ...args: unknown[]) {
  if (!LOG_ENABLED) return;
  const ts = new Date().toISOString().substr(11, 12);
  const msg = `[${ts}][backendApi][${tag}] ${args.map(a => typeof a === 'object' ? JSON.stringify(a) : String(a)).join(' ')}`;
  console.log(msg);
}

export const DEFAULT_TERMINAL_STATES = new Set(['completed', 'detected', 'error', 'timeout']);
