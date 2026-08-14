import { defineStore } from 'pinia'
import { httpRoot } from '@/api/http'

export interface HealthInfo {
  status: 'ok' | 'starting' | 'degraded' | 'error' | 'unknown'
  message?: string | null
  checks?: Record<string, unknown>
  version?: string
}

export interface SystemStatus {
  api: HealthInfo
  lastCheckedAt: number | null
}

export const useAppStore = defineStore('app', {
  state: (): SystemStatus => ({
    api: { status: 'unknown' },
    lastCheckedAt: null,
  }),
  actions: {
    async probeBackend() {
      try {
        // NOTE: /healthz/* lives at ROOT (not under /api) — use httpRoot.
        // httpRoot.validateStatus accepts 2xx..5xx, so 503 (starting/degraded)
        // resolves normally with response.data containing the real status.
        const { data, status: httpStatus } = await httpRoot.get<HealthInfo>('/healthz/ready')

        // Safety net: if server returned a completely empty body for some reason,
        // synthesize a status from the HTTP code so the UI still renders correctly.
        if (!data || typeof data !== 'object' || !data.status) {
          this.api = {
            status: httpStatus === 200 ? 'ok' : httpStatus < 500 ? 'degraded' : 'starting',
            message: `HTTP ${httpStatus} (empty JSON body)`,
          }
        } else {
          this.api = data
        }
      } catch (e: unknown) {
        // Only true network errors land here (DNS, TCP reset, CORS blocked, etc.)
        // Valid HTTP responses with 4xx/5xx codes do NOT reach this block thanks
        // to httpRoot.validateStatus.
        const err = e as { message?: string; code?: string }
        this.api = {
          status: 'error',
          message: err?.message ?? 'Backend unreachable',
          checks: { reason: err?.code ?? 'network_error' },
        }
      } finally {
        this.lastCheckedAt = Date.now()
      }
    },
  },
})
