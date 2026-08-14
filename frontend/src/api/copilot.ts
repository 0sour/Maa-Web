import { http } from '@/api/http'

/** 本地作业列表项：文件名 + 关卡名（从作业内容读取） */
export interface CopilotFile {
  filename: string
  stage_name: string
  stage_display: string
  /** copilot（普通/悖论标准格式）| sss（保全专用格式） */
  job_type?: string
}

/** prts.plus 作业获取结果：已保存到本地 + 元信息 */
export interface CopilotFetchResult {
  id: number
  filename: string
  stage_name: string
  stage_display: string
  job_type?: string
  uploader: string
  views: number
  rating: number
  upload_time: string
}

/** 作业站代码解析结果：单个作业（type=copilot）或作业集（type=set） */
export interface CopilotCodeResult {
  type: 'copilot' | 'set'
  // ── copilot ──
  id?: number | null
  filename?: string | null
  stage_name?: string | null
  stage_display?: string
  uploader?: string
  views?: number
  rating?: number
  upload_time?: string
  // ── set ──
  name?: string | null
  description?: string
  jobs: CopilotFetchResult[]
  skipped: number[]
}

export const copilotApi = {
  /** 本地已有作业 JSON 列表（含关卡名） */
  list: () => http.get<CopilotFile[]>('/v1/copilot/list').then((r) => r.data),
  /** 从 prts.plus 按作业 ID 拉取并保存到 resource/copilot/ */
  fetchPrts: (id: number) =>
    http.post<CopilotFetchResult>(`/v1/copilot/prts/${id}`).then((r) => r.data),
  /** 解析作业站代码：prts://99359 / prts://s51251 / s51251 / 99359 → 作业或作业集 */
  resolveCode: (code: string) =>
    http.post<CopilotCodeResult>('/v1/copilot/prts/code', { code }).then((r) => r.data),
}
