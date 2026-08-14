import { defineStore } from 'pinia'
import {
  openLogStream,
  tasksApi,
  type LiveLogLine,
  type TaskItemPayload,
  type TaskRunResult,
  type TaskStatus,
} from '@/api/tasks'

const MAX_LOG_LINES = 500

export const useTasksStore = defineStore('tasks', {
  state: () => ({
    status: null as TaskStatus | null,
    running: false,
    logs: [] as LiveLogLine[],
    ws: null as WebSocket | null,
    busy: false,
    error: '' as string,
  }),
  getters: {
    /** 当天日志（本地时区）：实时面板只显示今天，跨天自动从视图上消失（归档到历史）。
     * 无时间戳的客户端提示行（如「任务队列已启动」）视为当天。 */
    todayLogs(state): LiveLogLine[] {
      const p = (n: number) => String(n).padStart(2, '0')
      const d = new Date()
      const today = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
      return state.logs.filter((l) => {
        const t = l.ts ? new Date(l.ts) : null
        if (!t || Number.isNaN(t.getTime())) return true
        return `${t.getFullYear()}-${p(t.getMonth() + 1)}-${p(t.getDate())}` === today
      })
    },
  },
  actions: {
    /** 拉取指定设备的运行器状态快照 */
    async fetchStatus(deviceId: number) {
      try {
        this.status = await tasksApi.status(deviceId)
        if (this.status.status === 'running' || this.status.status === 'stopping') {
          this.running = true
        }
      } catch (e: unknown) {
        this.status = null
        this.error = (e as { message?: string })?.message ?? '获取任务状态失败'
      }
    },

    /** 启动任务队列；抛错给调用方展示 */
    async run(deviceId: number, tasks: TaskItemPayload[]): Promise<TaskRunResult> {
      this.busy = true
      this.error = ''
      try {
        const res = await tasksApi.run(deviceId, tasks)
        this.running = true
        this.pushLog({ level: 'info', message: res.message })
        return res
      } catch (e: unknown) {
        const msg = (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
          ?? (e as { message?: string })?.message
          ?? '启动失败'
        this.error = msg
        this.pushLog({ level: 'error', message: `✖ ${msg}` })
        throw e
      } finally {
        this.busy = false
      }
    },

    /** 停止运行中的队列 */
    async stop(deviceId: number) {
      this.busy = true
      try {
        const res = await tasksApi.stop(deviceId)
        this.pushLog({ level: 'warn', message: res.message })
      } catch (e: unknown) {
        this.error = (e as { message?: string })?.message ?? '停止失败'
      } finally {
        this.busy = false
      }
    },

    /** 连接设备的实时日志流；同一 store 只保留一个连接 */
    connectStream(deviceId: number) {
      this.closeStream()
      const ws = openLogStream(deviceId)
      this.ws = ws
      ws.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data as string) as LiveLogLine
          if (data.event === 'run_finished') {
            this.running = false
            this.pushLog({ level: 'warn', message: `■ 运行结束（${data.status ?? 'unknown'}）` })
          } else {
            this.pushLog(data)
          }
        } catch {
          /* malformed frame — ignore */
        }
      }
      ws.onclose = () => {
        if (this.ws === ws) {
          this.ws = null
          this.running = false
        }
      }
      ws.onerror = () => {
        this.pushLog({ level: 'error', message: '⚠ 日志流连接异常，尝试重连…' })
        this.closeStream()
        // 简单自动重连（仅当页面仍需要时）
        window.setTimeout(() => {
          if (this.status?.status === 'running' || this.running) this.connectStream(deviceId)
        }, 3000)
      }
    },

    /** 回填当天日志（DB 持久化，跨页面保留）。须在 connectStream 之后调用：
     * 先连流再取快照，连接期间到达的行都在快照里，替换后不会丢也不会重复。 */
    async loadToday(deviceId?: number) {
      try {
        const g = await tasksApi.today(deviceId)
        this.logs = g.entries.map((e) => ({
          id: e.id,
          level: e.level,
          message: e.message,
          ts: e.ts,
        }))
      } catch {
        /* 回填失败不阻塞实时流 */
      }
    },

    closeStream() {
      if (this.ws) {
        this.ws.onclose = null
        this.ws.close()
        this.ws = null
      }
    },

    pushLog(line: LiveLogLine) {
      // WS 与回填可能短暂重叠：按 DB id 去重
      if (line.id != null && this.logs.some((l) => l.id === line.id)) return
      this.logs.push(line)
      if (this.logs.length > MAX_LOG_LINES) this.logs = this.logs.slice(-MAX_LOG_LINES)
    },
  },
})
