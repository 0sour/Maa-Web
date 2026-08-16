import { http } from '@/api/http'

/** 工具箱工具类型（M5 第一批：三识别；抽卡/窥屏规划中） */
export type ToolboxTool = 'recruit' | 'depot' | 'operbox'

/** 公招识别结果（识别结果结构对齐 MAA 客户端） */
export interface RecruitResult {
  level: number
  tags: string[]
  opers: { id: string; name: string; level: number }[]
}

export interface RecognizeResult {
  /** recruit */
  tags?: string[]
  results?: RecruitResult[]
  /** depot */
  items?: Record<string, number>
  /** operbox */
  opers?: { id: string; rarity: number; elite: number; level: number; potential: number }[]
}

/** 识别任务状态（轮询） */
export interface ToolboxTaskStatus {
  status: 'running' | 'done' | 'error'
  result?: RecognizeResult | null
  error?: string | null
}

/** 历史识别记录 */
export interface ToolboxRecord {
  id: number
  tool: string
  device_id: number
  result: RecognizeResult
  summary: string
  created_at: string
}

export const toolboxApi = {
  /** 启动识别任务（异步，返回 task_id；前端轮询 taskStatus） */
  recognize: (deviceId: number, tool: ToolboxTool) =>
    http
      .post<{ ok: boolean; task_id: string; tool: string }>('/v1/toolbox/recognize', {
        device_id: deviceId,
        tool,
      })
      .then((r) => r.data),
  /** 识别任务状态（轮询） */
  taskStatus: (taskId: string) =>
    http.get<ToolboxTaskStatus>(`/v1/toolbox/tasks/${taskId}`).then((r) => r.data),
  /** 历史识别记录（按工具/设备过滤） */
  records: (tool?: string, deviceId?: number) =>
    http
      .get<{ records: ToolboxRecord[] }>('/v1/toolbox/records', {
        params: { tool, device_id: deviceId },
      })
      .then((r) => r.data),
  /** 单条记录详情（历史结果调用展示） */
  record: (id: number) =>
    http.get<ToolboxRecord>(`/v1/toolbox/records/${id}`).then((r) => r.data),
  /** 删除记录 */
  deleteRecord: (id: number) =>
    http.delete<{ ok: boolean }>(`/v1/toolbox/records/${id}`).then((r) => r.data),
  /** 按识别结果执行真实公招（联动，消耗招募许可） */
  executeRecruit: (deviceId: number, level: number) =>
    http
      .post<{ ok: boolean; run_id: number; message: string }>('/v1/toolbox/recruit/execute', {
        device_id: deviceId,
        level,
      })
      .then((r) => r.data),
}
