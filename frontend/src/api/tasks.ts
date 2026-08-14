import { http } from '@/api/http'

/** 一次运行中的单个任务（对应 MAA AsstAppendTask 的任务类型 + 参数） */
export interface TaskItemPayload {
  name: string
  entry: string
  type: string
  params: Record<string, unknown>
}

export interface TaskRunResult {
  run_id: number
  device_id: number
  status: string
  message: string
}

/** GET /tasks/{device_id}/status 的运行器快照 */
export interface TaskStatus {
  device_id: number
  /** idle | running | stopping | finished | error | stopped */
  status: string
  run_id: number | null
  summary: string
  device_online: boolean
  engine_available: boolean
  resource_ready: boolean
  error: string | null
}

export interface LogEntry {
  id: number
  run_id: number
  device_id: number
  level: string
  message: string
  ts: string
}

/** 历史日志按天分组（/tasks/logs） */
export interface LogDayGroup {
  date: string
  count: number
  entries: LogEntry[]
}

export interface LogsByDay {
  days: LogDayGroup[]
}

/** WS /tasks/ws/logs 推送的行；event=run_finished 时携带 status/run_id；日志行携带 DB id */
export interface LiveLogLine {
  id?: number
  level?: string
  message?: string
  ts?: string
  event?: string
  status?: string
  run_id?: number
}

export const tasksApi = {
  /** 启动串行任务队列 */
  run: (deviceId: number, tasks: TaskItemPayload[]) =>
    http.post<TaskRunResult>(`/v1/tasks/${deviceId}/run`, { tasks }).then((r) => r.data),
  /** 停止运行中的队列 */
  stop: (deviceId: number) =>
    http.post<TaskRunResult>(`/v1/tasks/${deviceId}/stop`).then((r) => r.data),
  /** 运行器状态快照 */
  status: (deviceId: number) =>
    http.get<TaskStatus>(`/v1/tasks/${deviceId}/status`).then((r) => r.data),
  /** 某次运行的历史日志 */
  logs: (runId: number) =>
    http.get<LogEntry[]>(`/v1/tasks/runs/${runId}/logs`).then((r) => r.data),
  /** 当天日志（本地时区，时间正序）——实时面板回填，跨页面保留 */
  today: (deviceId?: number) =>
    http
      .get<LogDayGroup>('/v1/tasks/logs/today', { params: { device_id: deviceId } })
      .then((r) => r.data),
  /** 历史日志按天分组（仅今天之前，跨 run；deviceId 可选过滤） */
  logsByDay: (days: number, deviceId?: number) =>
    http
      .get<LogsByDay>('/v1/tasks/logs', { params: { days, device_id: deviceId } })
      .then((r) => r.data),
}

/** 打开设备实时日志流（S-05） */
export function openLogStream(deviceId: number): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  return new WebSocket(`${proto}://${location.host}/api/v1/tasks/ws/logs?device_id=${deviceId}`)
}
