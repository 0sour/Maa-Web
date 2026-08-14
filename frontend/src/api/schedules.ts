import { http } from '@/api/http'
import type { TaskItemPayload } from './tasks'

/** 定时执行任务（schedule_jobs：星期 × 时间 → 自动跑任务方案快照） */
export interface ScheduleJob {
  id: number
  device_id: number
  name: string
  enabled: boolean
  /** Mon..Sun（%a 缩略，与周计划一致） */
  weekdays: string[]
  /** "HH:MM"（本地时区） */
  time: string
  /** 来源方案名（展示） */
  plan_name: string
  /** 方案内容快照（保存时固化，方案后续改动不影响定时） */
  tasks: TaskItemPayload[]
  last_run_at: string | null
  created_at: string
}

export const schedulesApi = {
  /** 定时任务列表 */
  list: () => http.get<ScheduleJob[]>('/v1/schedules').then((r) => r.data),
  /** 新建定时任务 */
  create: (payload: Partial<ScheduleJob>) =>
    http.post<ScheduleJob>('/v1/schedules', payload).then((r) => r.data),
  /** 更新（部分字段） */
  update: (id: number, payload: Partial<ScheduleJob>) =>
    http.put<ScheduleJob>(`/v1/schedules/${id}`, payload).then((r) => r.data),
  /** 删除 */
  remove: (id: number) =>
    http.delete<{ ok: boolean }>(`/v1/schedules/${id}`).then((r) => r.data),
  /** 立即触发一次（试跑，不走星期/时间匹配） */
  runNow: (id: number) =>
    http.post<ScheduleJob>(`/v1/schedules/${id}/run`).then((r) => r.data),
}
