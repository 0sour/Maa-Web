/**
 * useTaskQueue — 任务队列编辑状态（作战总览 / 任务编排 两页复用）。
 *
 * 覆盖：添加任务、勾选启用、ONCE、选中、移除、拖拽排序、序列化
 * （即时保存 / 方案文件共用同一持久化形状）。每个任务独立参数，
 * 参数由 TaskParamsPanel 各类型表单直接编辑（无全局表单状态）。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  deserializeQueue,
  nextTaskId,
  queueToPayload,
  serializeQueue,
  type PersistedTask,
  type QueueTask,
  type TaskTypeDef,
} from './taskTypes'

export interface TaskQueue {
  /** 队列编辑期状态（ref 暴露给模板） */
  queue: Ref<QueueTask[]>
  adding: Ref<boolean>
  selectedTask: ComputedRef<QueueTask | undefined>
  countChecked: ComputedRef<number>
  addTask: (type: TaskTypeDef) => void
  selectTask: (id: number) => void
  toggleChecked: (id: number) => void
  removeTask: (id: number) => void
  onDragStart: (i: number) => void
  onDrop: (i: number) => void
  clearQueue: () => void
  /** 按勾选生成 API 下发载荷 */
  payload: () => ReturnType<typeof queueToPayload>
  /** 序列化为持久化形状（保存用） */
  serialize: () => PersistedTask[]
  /** 从持久化形状恢复（加载用，替换整个队列） */
  restore: (list: PersistedTask[]) => void
}

export function useTaskQueue(initial?: PersistedTask[]): TaskQueue {
  const queue = ref<QueueTask[]>(initial && initial.length ? deserializeQueue(initial) : [])
  const adding = ref(false)

  const selectedTask = computed(() => queue.value.find((t) => t.selected))
  const countChecked = computed(() => queue.value.filter((t) => t.checked).length)

  function addTask(type: TaskTypeDef) {
    const id = nextTaskId()
    queue.value.push({
      id,
      type: type.type,
      entry: type.entry,
      label: type.label,
      params: { ...type.params },
      checked: true,
      once: false,
      selected: true,
    })
    queue.value.forEach((t) => { t.selected = t.id === id })
    adding.value = false
  }

  function selectTask(id: number) {
    queue.value.forEach((t) => { t.selected = t.id === id })
  }

  function toggleChecked(id: number) {
    const t = queue.value.find((x) => x.id === id)
    if (t) t.checked = !t.checked
  }

  function removeTask(id: number) {
    queue.value = queue.value.filter((t) => t.id !== id)
  }

  let dragIndex = -1
  function onDragStart(i: number) { dragIndex = i }
  function onDrop(i: number) {
    if (dragIndex >= 0 && dragIndex !== i) {
      const [moved] = queue.value.splice(dragIndex, 1)
      queue.value.splice(i, 0, moved)
    }
    dragIndex = -1
  }

  function clearQueue() {
    queue.value = []
  }

  function payload() {
    return queueToPayload(queue.value)
  }

  function serialize() {
    return serializeQueue(queue.value)
  }

  function restore(list: PersistedTask[]) {
    queue.value = deserializeQueue(list)
  }

  return {
    queue, adding, selectedTask, countChecked,
    addTask, selectTask, toggleChecked, removeTask, onDragStart, onDrop,
    clearQueue, payload, serialize, restore,
  }
}
