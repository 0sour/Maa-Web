import axios from 'axios'

// ── Axios wrapper ────────────────────────────────────────
// Dev:  Vite proxy forwards /api → http://localhost:8000
// Prod: Same-origin via nginx (/api → api:8000 internal)
export const http = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Accept': 'application/json',
  },
})

// Also expose an alias for direct non-REST probes (e.g. /healthz lives at root)
// NOTE: healthz intentionally returns 503/5xx during startup/degraded phases, which
//       are still valid JSON payloads. Do NOT treat those as network errors — let the
//       caller inspect response.data.status to render the correct UI chip.
export const httpRoot = axios.create({
  baseURL: '/',
  timeout: 8000,
  validateStatus: (status) => status >= 200 && status < 600,
})

// ── Simple response type guard helper ────────────────────
export function isOk<T extends { status?: string }>(r: T | undefined): boolean {
  return r?.status === 'ok'
}
