import { http } from '@/api/http'

/** 镜像源设置（更新源 + ghproxy 前缀 + MirrorChyan CDK 状态） */
export interface MirrorSourceSettings {
  /** 资源更新源：github | mirrorchyan */
  update_source: string
  /** 编辑用的原始文本（逗号/换行分隔） */
  mirror_prefixes: string
  /** 已保存的前缀列表（后端解析回显） */
  mirror_prefix_list: string[]
  /** 当前生效前缀（含 .env 回退，仅展示） */
  effective_prefix_list: string[]
  /** CDK 脱敏展示 */
  mirrorchyan_cdk_masked: string
  /** CDK 明文（保存后回显，默认以掩码输入框展示） */
  mirrorchyan_cdk: string
  /** CDK 是否已配置 */
  mirrorchyan_cdk_configured: boolean
  /** CDK 有效期（unix 秒；0 = 未检查） */
  mirrorchyan_cdk_expired_time: number
  /** 剩余天数；null = 未知/未配置 */
  mirrorchyan_cdk_remaining_days: number | null
  /** 上次检查提示（如「已过期」「剩余 12.3 天」） */
  mirrorchyan_cdk_message: string
  /** HTTP 代理（clash 等场景）；空 = 直连 */
  http_proxy: string
  /** 动态资源（MaaResource）独立源：空 = 跟随 update_source；github | mirrorchyan */
  dynamic_source: string
}

export interface MirrorSourceUpdate {
  /** 资源更新源：github | mirrorchyan */
  update_source?: string
  /** 逗号/换行分隔的镜像前缀；空字符串 = 清空（官方直连） */
  mirror_prefixes?: string
  /** MirrorChyan CDK；空字符串 = 清除 */
  mirrorchyan_cdk?: string
  /** HTTP 代理；空字符串 = 清除（恢复直连） */
  http_proxy?: string
  /** 动态资源源：空 = 跟随引擎包源；github | mirrorchyan 显式指定 */
  dynamic_source?: string
}

export interface MirrorCdkCheckResult {
  ok: boolean
  message: string
  code: number
  cdk_expired_time: number
  remaining_days: number | null
}

/** 账号组条目（自动任务的账号来源；client_type 对齐 MAA 客户端） */
export interface AccountGroupItem {
  name: string
  client_type: string
}

/** 通用设置分组（S-04/§4.4 设置中心，SQLite Setting 表） */
export interface SettingsGroups {
  game: Record<string, unknown>
  connection: Record<string, unknown>
  ui: Record<string, unknown>
  notify: Record<string, unknown>
  accounts: Record<string, unknown>
}

/** 读取账号组列表（accounts.list；解析失败返回空） */
export function parseAccountGroups(groups: SettingsGroups | null): AccountGroupItem[] {
  const raw = groups?.accounts?.list
  if (!Array.isArray(raw)) return []
  return raw.filter(
    (x): x is AccountGroupItem =>
      typeof x === 'object' && x !== null && typeof (x as AccountGroupItem).name === 'string',
  )
}

/** IP 定位结果（/settings/geoip，NAS 出口 IP） */
export interface GeoIpResult {
  lat: number
  lon: number
  city?: string
  country?: string
}

export const settingsApi = {
  mirror: () => http.get<MirrorSourceSettings>('/v1/settings/mirror').then((r) => r.data),
  saveMirror: (payload: MirrorSourceUpdate) =>
    http.put<MirrorSourceSettings>('/v1/settings/mirror', payload).then((r) => r.data),
  /** 检查 MirrorChyan CDK 有效期（对齐 MAA 客户端 cdk_expired_time 机制） */
  checkCdk: (cdk: string) =>
    http.post<MirrorCdkCheckResult>('/v1/settings/mirror/check', { cdk }).then((r) => r.data),
  /** 读取全部设置分组（运行/连接/界面） */
  getAll: () => http.get<SettingsGroups>('/v1/settings').then((r) => r.data),
  /** 保存一组设置（game/connection/ui） */
  saveGroup: (group: string, values: Record<string, unknown>) =>
    http.put<SettingsGroups>(`/v1/settings/${group}`, { values }).then((r) => r.data),
  /** IP 定位（NAS 出口 IP → 当地经纬度；浏览器 geolocation 不可用时的兜底） */
  geoip: () => http.get<GeoIpResult>('/v1/settings/geoip').then((r) => r.data),
  /** 测试 HTTP 代理连通性（经代理访问 GitHub API） */
  proxyTest: (proxy: string) =>
    http
      .post<{ ok: boolean; latency_ms: number | null; error: string | null }>(
        '/v1/settings/proxy-test',
        { proxy },
      )
      .then((r) => r.data),
  /** 导出日志 zip（问题反馈） */
  exportLogs: async (): Promise<Blob> => {
    const r = await http.get('/v1/settings/logs-export', { responseType: 'blob' })
    return r.data as Blob
  },
  /** 导出全部配置 zip（设备/方案/草稿/自动任务/设置/运行时设置，备份与迁移用） */
  exportConfig: async (): Promise<Blob> => {
    const r = await http.get('/v1/settings/export-config', { responseType: 'blob' })
    return r.data as Blob
  },
  /** 导入配置（覆盖恢复；支持 zip 或 config.json；导入前后端自动备份当前配置） */
  importConfig: async (file: File): Promise<{ ok: boolean; message: string; backup?: string }> => {
    const fd = new FormData()
    fd.append('file', file)
    const r = await http.post<{ ok: boolean; message: string; backup?: string }>(
      '/v1/settings/import-config',
      fd,
    )
    return r.data
  },
}
