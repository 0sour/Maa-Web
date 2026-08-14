/**
 * useTaskSchemes — 任务方案「任务文件」管理（任务编排页用）。
 *
 * 方案 = 命名后的任务队列（含固化参数/勾选/ONCE），存 localStorage，
 * 之后可在任务编排页随时调出复用。作战总览不依赖此模块（走即时保存）。
 */
import { ref } from 'vue'
import type { PersistedTask } from './taskTypes'

export interface TaskScheme {
  name: string
  tasks: PersistedTask[]
  updatedAt: string
}

const STORAGE_KEY = 'maaweb.task.schemes'

function load(): TaskScheme[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as unknown
    return Array.isArray(parsed) ? parsed as TaskScheme[] : []
  } catch {
    return []
  }
}

function persist(list: TaskScheme[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    /* quota / 隐私模式 —— 忽略，仅本次会话有效 */
  }
}

export function useTaskSchemes() {
  const schemes = ref<TaskScheme[]>(load())

  /** 保存当前队列为方案；同名覆盖。返回该方案 */
  function saveScheme(name: string, tasks: PersistedTask[]): TaskScheme {
    const trimmed = name.trim()
    const now = new Date().toISOString()
    const idx = schemes.value.findIndex((s) => s.name === trimmed)
    const scheme: TaskScheme = { name: trimmed, tasks, updatedAt: now }
    if (idx >= 0) schemes.value[idx] = scheme
    else schemes.value.push(scheme)
    persist(schemes.value)
    return scheme
  }

  function removeScheme(name: string) {
    schemes.value = schemes.value.filter((s) => s.name !== name)
    persist(schemes.value)
  }

  function renameScheme(oldName: string, newName: string): boolean {
    const s = schemes.value.find((x) => x.name === oldName)
    if (!s) return false
    s.name = newName.trim()
    persist(schemes.value)
    return true
  }

  return { schemes, saveScheme, removeScheme, renameScheme }
}
