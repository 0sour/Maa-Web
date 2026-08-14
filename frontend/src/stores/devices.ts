import { defineStore } from 'pinia'
import {
  devicesApi,
  type Device,
  type DeviceDetectResult,
  type DevicePayload,
} from '@/api/devices'

export const useDevicesStore = defineStore('devices', {
  state: () => ({
    list: [] as Device[],
    loading: false,
    busyId: null as number | null, // 正在连接/断开/删除的设备
    error: '' as string,
    detecting: false,
    detect: null as DeviceDetectResult | null,
  }),
  getters: {
    onlineCount: (s) => s.list.filter((d) => d.status === 'online').length,
    errorCount: (s) => s.list.filter((d) => d.status === 'error').length,
  },
  actions: {
    /** 替换/插入单台设备到本地列表（保持稳定排序） */
    _upsert(dev: Device) {
      const i = this.list.findIndex((d) => d.id === dev.id)
      if (i >= 0) this.list[i] = dev
      else this.list.push(dev)
    },
    async fetchList() {
      this.loading = true
      this.error = ''
      try {
        this.list = await devicesApi.list()
      } catch (e: unknown) {
        this.error = (e as { message?: string })?.message ?? '获取设备列表失败'
      } finally {
        this.loading = false
      }
    },
    async add(payload: DevicePayload) {
      this.error = ''
      const dev = await devicesApi.create(payload)
      this._upsert(dev)
      return dev
    },
    async update(id: number, payload: Partial<DevicePayload>) {
      this.error = ''
      const dev = await devicesApi.update(id, payload)
      this._upsert(dev)
      return dev
    },
    async remove(id: number) {
      this.error = ''
      this.busyId = id
      try {
        await devicesApi.remove(id)
        this.list = this.list.filter((d) => d.id !== id)
      } finally {
        this.busyId = null
      }
    },
    async connect(id: number) {
      this.error = ''
      this.busyId = id
      try {
        const { device } = await devicesApi.connect(id)
        this._upsert(device)
      } catch (e: unknown) {
        this.error = (e as { message?: string })?.message ?? '连接失败'
      } finally {
        this.busyId = null
      }
    },
    async disconnect(id: number) {
      this.error = ''
      this.busyId = id
      try {
        const { device } = await devicesApi.disconnect(id)
        this._upsert(device)
      } catch (e: unknown) {
        this.error = (e as { message?: string })?.message ?? '断开失败'
      } finally {
        this.busyId = null
      }
    },
    async detectDevices() {
      this.detecting = true
      try {
        this.detect = await devicesApi.detect()
      } catch (e: unknown) {
        this.error = (e as { message?: string })?.message ?? '设备扫描失败'
        this.detect = null
      } finally {
        this.detecting = false
      }
    },
    // ── 分辨率（MAA 需要 16:9；真机临时调整后需 reset 恢复） ──
    getResolution(id: number) {
      return devicesApi.resolution(id)
    },
    setResolution(id: number, width: number, height: number) {
      return devicesApi.setResolution(id, width, height)
    },
    resetResolution(id: number) {
      return devicesApi.resetResolution(id)
    },
  },
})
