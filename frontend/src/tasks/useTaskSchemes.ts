/**
 * useTaskSchemes — 任务方案「任务文件」管理（任务编排页用）。
 *
 * 方案 = 命名后的任务队列（含固化参数/勾选/ONCE），**存后端 task_schemes 表**
 * （2026-08-16 起；此前存 localStorage 换浏览器/设备丢失）。首次加载时
 * 自动把旧 localStorage 数据迁移到后端（后端为空且本地有 → 上传 → 清理本地）。
 */
import { ref } from 'vue'
import { taskSchemesApi, type TaskScheme } from '@/api/task-schemes'
import type { PersistedTask } from './taskTypes'

const LEGACY_KEY = 'maaweb.task.schemes'

function loadLegacy(): { name: string; tasks: PersistedTask[]; updatedAt: string }[] {
  try {
    const raw = localStorage.getItem(LEGACY_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as { name: string; tasks: PersistedTask[]; updatedAt: string }[]) : []
  } catch {
    return []
  }
}

function clearLegacy() {
  try {
    localStorage.removeItem(LEGACY_KEY)
  } catch {
    /* 忽略 */
  }
}

export function useTaskSchemes() {
  const schemes = ref<TaskScheme[]>([])
  const loaded = ref(false)

  /** 从后端加载；后端为空时迁移旧 localStorage 数据（一次性） */
  async function load() {
    try {
      schemes.value = await taskSchemesApi.list()
      if (schemes.value.length === 0) {
        const legacy = loadLegacy()
        if (legacy.length) {
          for (const s of legacy) {
            try {
              schemes.value.push(
                await taskSchemesApi.save(s.name, s.tasks as unknown as Record<string, unknown>[]),
              )
            } catch {
              /* 单条迁移失败不阻塞其余 */
            }
          }
          if (schemes.value.length) clearLegacy()
        }
      }
    } catch {
      /* 后端不可达：保留空列表，不阻塞页面 */
    } finally {
      loaded.value = true
    }
  }

  /** 保存当前队列为方案；同名覆盖（upsert）。返回该方案 */
  async function saveScheme(name: string, tasks: PersistedTask[]): Promise<TaskScheme> {
    const trimmed = name.trim()
    const saved = await taskSchemesApi.save(trimmed, tasks as unknown as Record<string, unknown>[])
    const idx = schemes.value.findIndex((s) => s.name === trimmed)
    if (idx >= 0) schemes.value[idx] = saved
    else schemes.value.push(saved)
    return saved
  }

  async function removeScheme(name: string) {
    const s = schemes.value.find((x) => x.name === name)
    if (!s) return
    await taskSchemesApi.remove(s.id)
    schemes.value = schemes.value.filter((x) => x.name !== name)
  }

  return { schemes, loaded, load, saveScheme, removeScheme }
}
