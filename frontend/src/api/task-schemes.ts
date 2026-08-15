import { http } from '@/api/http'

/** 任务方案（后端 task_schemes 表；2026-08-16 起存后端，跨浏览器一致） */
export interface TaskScheme {
  id: number
  name: string
  /** PersistedTask 形状（type/entry/label/params/checked/once） */
  tasks: Record<string, unknown>[]
  updated_at: string
  created_at: string
}

export const taskSchemesApi = {
  /** 方案列表（updated_at 倒序） */
  list: () => http.get<TaskScheme[]>('/v1/task-schemes').then((r) => r.data),
  /** 保存方案：同名覆盖（upsert by name） */
  save: (name: string, tasks: Record<string, unknown>[]) =>
    http.post<TaskScheme>('/v1/task-schemes', { name, tasks }).then((r) => r.data),
  /** 更新方案（改名/换任务；改名冲突 409） */
  update: (id: number, name: string, tasks: Record<string, unknown>[]) =>
    http.put<TaskScheme>(`/v1/task-schemes/${id}`, { name, tasks }).then((r) => r.data),
  /** 删除方案 */
  remove: (id: number) =>
    http.delete<{ ok: boolean }>(`/v1/task-schemes/${id}`).then((r) => r.data),
}
