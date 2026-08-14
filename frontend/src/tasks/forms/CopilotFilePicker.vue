<script setup lang="ts">
/** 作业导入工具：本地作业搜索下拉 + 从 prts.plus 作业站按代码导入（作业/作业集）。
 *  导入结果通过 import-jobs 交给父级作业列表（自动战斗参数里的勾选列表）。
 *  数据源：后端 /v1/copilot/list（resource/copilot/ 现有作业）与 /v1/copilot/prts/code。 */
import { computed, onBeforeUnmount, ref } from 'vue'
import { copilotApi, type CopilotFile } from '@/api/copilot'
import type { CopilotJob } from '@/tasks/taskTypes'

withDefaults(defineProps<{ disabled?: boolean }>(), {})

const emit = defineEmits<{
  (e: 'import-jobs', jobs: CopilotJob[]): void
}>()

// ── 本地作业下拉 ─────────────────────────────
const files = ref<CopilotFile[]>([])
let loaded = false
async function load() {
  if (loaded) return
  loaded = true
  try {
    const list = await copilotApi.list()
    if (Array.isArray(list)) files.value = list
  } catch {
    /* 后端不可用时仅保留作业站能力 */
  }
}

const open = ref(false)
const q = ref('')
const matched = computed(() => {
  const query = q.value.trim().toLowerCase()
  if (!query) return files.value.slice(0, 8)
  const hit = files.value.filter((f) => f.filename.toLowerCase().includes(query))
  hit.sort((a, b) => {
    const pa = a.filename.toLowerCase().startsWith(query) ? 0 : 1
    const pb = b.filename.toLowerCase().startsWith(query) ? 0 : 1
    return pa - pb || a.filename.localeCompare(b.filename)
  })
  return hit.slice(0, 8)
})

function onInput(e: Event) {
  q.value = (e.target as HTMLInputElement).value
  open.value = true
}

function pickLocal(f: CopilotFile) {
  emit('import-jobs', [{
    filename: f.filename,
    stage_name: f.stage_name || '',
    stage_display: f.stage_display || f.stage_name || '',
    enabled: true,
  }])
  q.value = ''
  open.value = false
}

function onFocus() {
  open.value = true
  load()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && matched.value.length) {
    e.preventDefault()
    pickLocal(matched.value[0])
  } else if (e.key === 'Escape') {
    open.value = false
  }
}
let blurTimer: ReturnType<typeof setTimeout> | undefined
function onBlur() {
  blurTimer = setTimeout(() => (open.value = false), 120)
}
onBeforeUnmount(() => clearTimeout(blurTimer))

// ── prts.plus 作业站导入 ─────────────────────
const panelOpen = ref(false)
const code = ref('')
const fetching = ref(false)
const err = ref('')
const okMsg = ref('')

function togglePanel() {
  panelOpen.value = !panelOpen.value
  err.value = ''
  if (panelOpen.value) load()
}

async function fetchByCode() {
  const c = code.value.trim()
  if (!c) {
    err.value = '请输入作业站代码（如 prts://99359、prts://s51251、s51251、99359）'
    return
  }
  fetching.value = true
  err.value = ''
  okMsg.value = ''
  try {
    const r = await copilotApi.resolveCode(c)
    if (r.type === 'copilot' && r.filename) {
      emit('import-jobs', [{
        filename: r.filename,
        stage_name: r.stage_name ?? '',
        stage_display: r.stage_display || r.stage_name || '',
        enabled: true,
      }])
      okMsg.value = `✔ 已导入作业「${r.stage_display || r.stage_name || r.id}」`
    } else if (r.type === 'set') {
      emit('import-jobs', r.jobs.map((j) => ({
        filename: j.filename,
        stage_name: j.stage_name,
        stage_display: j.stage_display || j.stage_name,
        enabled: true,
      })))
      okMsg.value = `✔ 已导入作业集「${r.name}」共 ${r.jobs.length} 个作业`
      if (r.skipped.length) err.value = `跳过 ${r.skipped.length} 个下载失败的作业（ID：${r.skipped.join(', ')}）`
    }
    code.value = ''
  } catch (e: any) {
    err.value = e?.response?.data?.detail ?? '获取失败，请稍后重试'
  } finally {
    fetching.value = false
  }
}
</script>

<template>
  <div class="cfp">
    <div class="cfp-line">
      <div class="cfp-pick">
        <input
          class="cfp-input"
          :value="q"
          :disabled="disabled"
          placeholder="搜索本地作业"
          @input="onInput"
          @focus="onFocus"
          @blur="onBlur"
          @keydown="onKeydown"
        />
        <ul v-if="open && matched.length" class="cfp-list">
          <li
            v-for="f in matched" :key="f.filename"
            class="cfp-item"
            @mousedown.prevent="pickLocal(f)"
          >
            <span class="stage">{{ f.stage_display || f.stage_name || '—' }}</span>
            <span v-if="f.job_type === 'sss'" class="jtype sss">保全</span>
            <span v-else class="jtype">作业</span>
            <span class="fn">{{ f.filename }}</span>
          </li>
        </ul>
      </div>
      <button class="cfp-btn" type="button" :disabled="disabled" @click="togglePanel">
        {{ panelOpen ? '收起作业站' : '作业站导入' }}
      </button>
    </div>

    <div v-if="panelOpen" class="cfp-panel">
      <div class="cfp-fetch">
        <input class="cfp-input" v-model="code" placeholder="作业站代码" @keydown.enter="fetchByCode" />
        <button class="cfp-btn go" type="button" :disabled="fetching" @click="fetchByCode">
          {{ fetching ? '获取中…' : '导入' }}
        </button>
      </div>
      <div v-if="okMsg" class="cfp-meta">{{ okMsg }}</div>
      <div v-if="err" class="cfp-err">{{ err }}</div>
      <div class="cfp-hint">支持代码：prts://99359（作业）、prts://s51251（作业集）、s51251、99359</div>
    </div>
  </div>
</template>

<style scoped>
.cfp { flex-shrink: 0; }

.cfp-line { display: flex; align-items: center; gap: 6px; }

.cfp-pick { position: relative; }

.cfp-input {
  width: 150px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 6px 11px;
  font-size: var(--font-size-md); outline: none; font-family: inherit;
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard);
  clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px);
}
.cfp-input:focus { border-color: var(--color-brand); }
.cfp-input:disabled { opacity: 0.4; cursor: not-allowed; }

.cfp-btn {
  background: var(--color-bg-subtle); color: var(--color-text-secondary);
  border: 1px solid var(--color-border-default);
  padding: 6px 12px; font-size: var(--font-size-sm); cursor: pointer;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
  clip-path: polygon(5px 0, 100% 0, 100% calc(100% - 5px), calc(100% - 5px) 100%, 0 100%, 0 5px);
}
.cfp-btn:hover:not(:disabled) { border-color: var(--color-brand); color: var(--color-brand); background: var(--color-bg-active); }
.cfp-btn.go { color: var(--color-brand); border-color: var(--color-brand-strong); }
.cfp-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.cfp-list {
  position: absolute; z-index: 40; top: calc(100% + 4px); left: 0; min-width: 100%;
  max-height: 240px; overflow-y: auto;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  list-style: none; margin: 0; padding: 4px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.35);
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
}
.cfp-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px; font-size: var(--font-size-md); cursor: pointer;
  color: var(--color-text-secondary); font-family: var(--font-family-mono);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.cfp-item:hover { background: var(--color-bg-active); color: var(--color-brand); }
.cfp-item .stage { color: var(--color-text-primary); font-weight: 600; flex-shrink: 0; }
.cfp-item .jtype {
  flex-shrink: 0;
  font-size: var(--font-size-2xs); letter-spacing: 0.5px;
  border: 1px solid var(--color-border-default);
  color: var(--color-text-tertiary); padding: 0 5px;
}
.cfp-item .jtype.sss { color: var(--color-warning); border-color: var(--color-warning); }
.cfp-item .fn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.cfp-panel {
  margin-top: 6px; padding: 8px;
  border: 1px dashed var(--color-border-default);
  background: var(--color-bg-subtle);
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
}
.cfp-fetch { display: flex; align-items: center; gap: 6px; }
.cfp-fetch .cfp-input { width: 110px; }
.cfp-meta { margin-top: 6px; font-size: var(--font-size-xs); color: var(--color-success); }
.cfp-err { margin-top: 6px; font-size: var(--font-size-xs); color: var(--color-danger); }
.cfp-hint { margin-top: 6px; font-size: var(--font-size-2xs); color: var(--color-text-tertiary); }
</style>
