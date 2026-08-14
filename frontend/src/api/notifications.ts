import { http } from '@/api/http'

/** 外部通知发送记录（notify_logs） */
export interface NotifyLogEntry {
  id: number
  /** serverchan | dingtalk | custom */
  channel: string
  /** complete | error | test */
  event: string
  title: string
  content: string
  ok: boolean
  error: string | null
  ts: string
}

/** 发送结果（逐渠道） */
export interface NotifySendResult {
  results: { channel: string; ok: boolean; error: string | null }[]
}

export const notificationsApi = {
  /** 发送记录（最近 N 条，倒序） */
  logs: (limit = 50) =>
    http.get<NotifyLogEntry[]>('/v1/notifications/logs', { params: { limit } }).then((r) => r.data),
  /** 测试发送（按当前配置逐渠道发一条测试消息） */
  testSend: () =>
    http.post<NotifySendResult>('/v1/notifications/test').then((r) => r.data),
  /** 重发某条记录（按当前配置渠道） */
  resend: (id: number) =>
    http.post<NotifySendResult>(`/v1/notifications/logs/${id}/resend`).then((r) => r.data),
}
