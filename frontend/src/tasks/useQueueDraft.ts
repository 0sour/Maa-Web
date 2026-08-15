/**
 * useQueueDraft — 队列草稿（后端化，跨浏览器一致）。
 *
 * 草稿 = 未保存为方案的编辑中队列：首页「作战部署」（daily）与任务编排页（tasks）
 * 各一份，存后端（/tasks/queue-drafts）。任何队列改动防抖 600ms 保存；
 * 首次加载自动迁移旧 localStorage 数据（maaweb.daily.queue / maaweb.tasks.draft）。
 */
import { watch, type Ref } from 'vue'
import { tasksApi, type QueueDraftKey } from '@/api/tasks'
import type { PersistedTask, QueueTask } from './taskTypes'

const LEGACY_KEYS: Record<QueueDraftKey, string> = {
  daily: 'maaweb.daily.queue',
  tasks: 'maaweb.tasks.draft',
}

function loadLegacy(key: QueueDraftKey): PersistedTask[] | undefined {
  try {
    const raw = localStorage.getItem(LEGACY_KEYS[key])
    if (!raw) return undefined
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? (parsed as PersistedTask[]) : undefined
  } catch {
    return undefined
  }
}

function clearLegacy(key: QueueDraftKey) {
  try {
    localStorage.removeItem(LEGACY_KEYS[key])
  } catch {
    /* 忽略 */
  }
}

export function useQueueDraft(key: QueueDraftKey) {
  let loaded = false
  let timer: number | null = null

  /** 从后端加载草稿（空/失败返回 undefined → 页面保持空队列） */
  async function loadDraft(): Promise<PersistedTask[] | undefined> {
    try {
      const drafts = await tasksApi.queueDrafts()
      const list = drafts[key]
      loaded = true
      const tasks = Array.isArray(list) ? (list as PersistedTask[]) : []
      // 旧 localStorage 数据迁移（仅当后端为空且本地有）
      if (tasks.length === 0) {
        const legacy = loadLegacy(key)
        if (legacy && legacy.length) {
          await tasksApi.saveQueueDraft(key, legacy).catch(() => undefined)
          clearLegacy(key)
          return legacy
        }
      }
      return tasks.length ? tasks : undefined
    } catch {
      return undefined
    }
  }

  /** 监听队列变化 → 防抖 600ms 保存到后端（加载完成前不覆盖） */
  function watchSave(queue: Ref<QueueTask[]>, serialize: () => PersistedTask[]) {
    watch(
      queue,
      () => {
        if (!loaded) return
        if (timer !== null) window.clearTimeout(timer)
        timer = window.setTimeout(() => {
          void tasksApi.saveQueueDraft(key, serialize()).catch(() => undefined)
        }, 600)
      },
      { deep: true },
    )
  }

  return { loadDraft, watchSave }
}
