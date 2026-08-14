/**
 * useFormParams — 各任务类型参数表单的共用逻辑。
 *
 * `params` 是选中任务的 params 对象（响应式，直接编辑即写回队列任务）。
 * 提供数组字段 toggle / 包含判断 / 标签文本 ↔ 数组的双向绑定。
 */
import { computed, ref, watch } from 'vue'

export function useFormParams(params: Record<string, unknown>) {
  const p = computed(() => params)

  /** 数组字段（多选）切换元素 */
  function toggle(key: string, value: unknown) {
    const arr = Array.isArray(p.value[key]) ? (p.value[key] as unknown[]) : []
    const i = arr.indexOf(value)
    if (i >= 0) arr.splice(i, 1)
    else arr.push(value)
    p.value[key] = arr
  }

  function has(key: string, value: unknown): boolean {
    const arr = p.value[key]
    return Array.isArray(arr) && arr.includes(value)
  }

  /** 对象布尔字段（如 collectible_mode_start_list）切换 */
  function toggleObj(key: string, subKey: string) {
    const cur = p.value[key] && typeof p.value[key] === 'object' ? { ...(p.value[key] as Record<string, unknown>) } : {}
    cur[subKey] = !cur[subKey]
    p.value[key] = cur
  }

  function hasObj(key: string, subKey: string): boolean {
    const o = p.value[key]
    return !!o && typeof o === 'object' && !!(o as Record<string, unknown>)[subKey]
  }

  function tags(key: string): string {
    const v = p.value[key]
    return Array.isArray(v) ? (v as string[]).join(', ') : ''
  }

  function setTags(key: string, text: string) {
    p.value[key] = text
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean)
  }

  /** 标签字段的 v-model ref（自动双向同步） */
  function tagRef(key: string) {
    const text = ref(tags(key))
    watch(text, (v) => setTags(key, v))
    watch(
      () => p.value[key],
      (v) => {
        const next = Array.isArray(v) ? (v as string[]).join(', ') : ''
        if (text.value !== next) text.value = next
      },
      { deep: true },
    )
    return text
  }

  return { p, toggle, has, toggleObj, hasObj, tags, setTags, tagRef }
}
