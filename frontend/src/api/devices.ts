import { http } from '@/api/http'

/** 设备状态机：offline → connecting → online | error */
export type DeviceStatus = 'online' | 'offline' | 'connecting' | 'error'

export interface Device {
  id: number
  name: string
  adb_host: string
  adb_port: number
  touch_mode: 'Minitouch' | 'MaaTouch' | 'Adb'
  client_type: string
  status: DeviceStatus
  /** 最近一次连接失败 / 引擎降级原因（健康时为 null） */
  last_error: string | null
  last_online_at: string | null
  created_at: string
}

export interface DevicePayload {
  name: string
  adb_host: string
  adb_port?: number
  touch_mode?: Device['touch_mode']
  client_type?: string
}

/** connect / disconnect 统一返回：更新后的设备 + 人话消息 */
export interface DeviceConnectResult {
  device: Device
  message: string
}

/** 分辨率查询/设置/重置结果 */
export interface DeviceResolutionResult {
  device_id: number
  width: number | null
  height: number | null
  message: string
}

export interface DetectedDevice {
  serial: string
  state: string
  model: string
  host: string
  port: number
}

export interface DeviceDetectResult {
  adb_available: boolean
  adb_path: string | null
  adb_version: string | null
  /** adb 不可用 / 扫描失败时的说明 */
  reason: string | null
  devices: DetectedDevice[]
  /** MaaFw 识别引擎（仅 ADB 也能连设备，但识别任务不可用） */
  engine_available: boolean
  engine_version: string
}

/** 设备 CRUD + 连接状态 + 扫描 API（C-01）。路径 /api/v1/devices → baseURL '/api' */
export const devicesApi = {
  list: () => http.get<Device[]>('/v1/devices').then((r) => r.data),
  create: (payload: DevicePayload) => http.post<Device>('/v1/devices', payload).then((r) => r.data),
  update: (id: number, payload: Partial<DevicePayload>) =>
    http.put<Device>(`/v1/devices/${id}`, payload).then((r) => r.data),
  remove: (id: number) => http.delete(`/v1/devices/${id}`),
  detect: () => http.post<DeviceDetectResult>('/v1/devices/detect').then((r) => r.data),
  connect: (id: number) =>
    http.post<DeviceConnectResult>(`/v1/devices/${id}/connect`).then((r) => r.data),
  disconnect: (id: number) =>
    http.post<DeviceConnectResult>(`/v1/devices/${id}/disconnect`).then((r) => r.data),
  // 分辨率（MAA 需要 16:9；真机临时调整后需 reset 恢复）
  resolution: (id: number) =>
    http.get<DeviceResolutionResult>(`/v1/devices/${id}/resolution`).then((r) => r.data),
  setResolution: (id: number, width: number, height: number) =>
    http.post<DeviceResolutionResult>(`/v1/devices/${id}/resolution`, { width, height }).then((r) => r.data),
  resetResolution: (id: number) =>
    http.post<DeviceResolutionResult>(`/v1/devices/${id}/resolution/reset`).then((r) => r.data),
}
