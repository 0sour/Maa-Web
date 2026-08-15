import { http } from '@/api/http'
import type { TaskItemPayload } from './tasks'

/** 时间槽的账号绑定（AutoSlotAccount）：账号（来自设置·账号组）+ 方案快照 */
export interface AutoSlotAccount {
  id: number
  /** 账号名（引用设置·账号组 accounts.list 的 name；引擎侧 = StartUp.account_name） */
  account_name: string
  /** 客户端类型（官服 Official / B服 Bilibili / txwy / 悠星系列） */
  client_type: string
  /** 勾选启用（取消勾选 = 停用但保留配置） */
  enabled: boolean
  /** 来源方案名（展示） */
  plan_name: string
  /** 方案内容快照（含参数微调后的结果） */
  tasks: TaskItemPayload[]
  /** 槽内执行顺序 */
  position: number
  last_run_at: string | null
  last_ok: boolean | null
}

/** 时间槽（AutoSlot） */
export interface AutoSlot {
  id: number
  name: string
  enabled: boolean
  /** Mon..Sun（%a 缩略，与周计划一致） */
  weekdays: string[]
  /** "HH:MM"（本地时区） */
  time: string
  /** 到点冲突策略：queue 排队等待 | skip 跳过本次 | force 强制结束上一任务 */
  conflict: 'queue' | 'skip' | 'force'
  accounts: AutoSlotAccount[]
  last_run_at: string | null
}

/** 自动任务（组）：多个时间槽的集合 */
export interface AutoTask {
  id: number
  name: string
  enabled: boolean
  device_id: number
  slots: AutoSlot[]
  created_at: string
}

/** 保存用载荷（与读取同构；账号不带 id/last_*） */
export interface AutoSlotAccountIn {
  account_name: string
  client_type: string
  enabled: boolean
  plan_name: string
  tasks: TaskItemPayload[]
}

export interface AutoSlotIn {
  name: string
  enabled: boolean
  weekdays: string[]
  time: string
  conflict: 'queue' | 'skip' | 'force'
  accounts: AutoSlotAccountIn[]
}

export interface AutoTaskIn {
  name: string
  device_id: number
  enabled: boolean
  slots: AutoSlotIn[]
}

export const autoTasksApi = {
  /** 自动任务列表（含时间槽与账号，嵌套） */
  list: () => http.get<AutoTask[]>('/v1/auto-tasks').then((r) => r.data),
  /** 新建自动任务（slots 全量嵌套） */
  create: (payload: AutoTaskIn) =>
    http.post<AutoTask>('/v1/auto-tasks', payload).then((r) => r.data),
  /** 整体保存（slots 全量替换） */
  update: (id: number, payload: AutoTaskIn) =>
    http.put<AutoTask>(`/v1/auto-tasks/${id}`, payload).then((r) => r.data),
  /** 删除（级联删槽与账号绑定） */
  remove: (id: number) =>
    http.delete<{ ok: boolean }>(`/v1/auto-tasks/${id}`).then((r) => r.data),
  /** 测试运行某时间槽（手动，日志带「自动任务(手动运行)」标签） */
  runTest: (id: number, slotId: number) =>
    http
      .post<{ ok: boolean; message: string }>(`/v1/auto-tasks/${id}/run-test`, { slot_id: slotId })
      .then((r) => r.data),
}
