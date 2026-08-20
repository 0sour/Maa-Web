import { http } from '@/api/http'

/** MAA 资源包状态（S-07）：本地 + 远端 + 后台更新任务 + 动态资源同步 */
export interface ResourceStatus {
  installed: boolean
  local_version: string | null
  pipelines: number
  ready: boolean
  dir: string
  source: string
  updating: boolean
  progress: number
  /** idle | fetch | download | extract | swap | done | error */
  stage: string
  update_error: string | null
  remote_latest: string | null
  remote_url: string | null
  remote_size: number
  update_available: boolean
  source_hint: string
  // 动态资源（MaaResource 增量同步）
  dynamic_syncing: boolean
  dynamic_stage: string
  dynamic_error: string | null
  dynamic_synced_at: string | null
  dynamic_commit: string | null
  dynamic_pending: number
  dynamic_done: number
  dynamic_mode: string
}

export interface ResourceUpdateResult {
  updating: boolean
  progress: number
  stage: string
  message: string
}

/** 引擎包材料/物品表条目（item_index.json） */
export interface ResourceItem {
  id: string
  name: string
  classify_type: string
}

/** 今日开放关卡（/resources/stages/today，对齐 MAA 客户端主界面提示） */
export interface TodayStages {
  game_day: { date: string; weekday: string }
  /** web | cache | local */
  source: string
  fetched_at: string
  resource_collection: { name: string; days_left: number | null } | null
  activities: {
    name: string
    days_left: number | null
    stages: { stage: string; drop: string }[]
  }[]
  open_stages: { stage: string; label: string; drops: string[][] }[]
}

export const resourcesApi = {
  status: () =>
    http.get<ResourceStatus>('/v1/resources/status').then((r) => r.data),
  update: () =>
    http.post<ResourceUpdateResult>('/v1/resources/update').then((r) => r.data),
  /** 动态资源增量同步（MaaResource 活动/模板热更新） */
  sync: () =>
    http.post<ResourceUpdateResult>('/v1/resources/sync').then((r) => r.data),
  /** 引擎包关卡代号列表（任务参数「目标关卡」搜索选择） */
  stages: () =>
    http.get<string[]>('/v1/resources/stages').then((r) => r.data),
  /** 今日开放关卡（活动 + 资源收集 + 常用资源/芯片本） */
  stagesToday: () =>
    http.get<TodayStages>('/v1/resources/stages/today').then((r) => r.data),
  /** 引擎包材料表（任务参数「指定掉落」搜索选择） */
  items: () =>
    http.get<ResourceItem[]>('/v1/resources/items').then((r) => r.data),
  /** 引擎包干员表（Copilot「追加干员」搜索选择） */
  operators: () =>
    http.get<ResourceItem[]>('/v1/resources/operators').then((r) => r.data),
  /** 引擎包公招 Tag 列表（「首选/保留 Tags」多选） */
  recruitTags: () =>
    http.get<string[]>('/v1/resources/recruit-tags').then((r) => r.data),
  /** 指定肉鸽主题的开局核心干员（「开局干员」搜索选择，随主题联动） */
  roguelikeCoreChars: (theme: string) =>
    http.get<string[]>('/v1/resources/roguelike-core-chars', { params: { theme } }).then((r) => r.data),
}
