<script setup lang="ts">
/**
 * 账号组设置面板 —— 维护自动任务的账号来源（accounts.list）。
 * 账号名须与游戏内登录账号一致（引擎 AccountSwitchTask 按此切换目标账号）；
 * 客户端类型对齐 MAA 客户端 StartUpTask 下拉（官服/B服/txwy/悠星系列）。
 */
import { onMounted, reactive, ref } from 'vue'
import './panel.css'
import { settingsApi, type AccountGroupItem } from '@/api/settings'
import DropSelect, { type DropOption } from '@/tasks/forms/DropSelect.vue'

const CLIENT_OPTS: DropOption[] = [
  { value: 'Official', label: '官服' },
  { value: 'Bilibili', label: 'B服' },
  { value: 'txwy', label: 'txwy' },
  { value: 'YoStarEN', label: '悠星EN' },
  { value: 'YoStarKR', label: '悠星KR' },
  { value: 'YoStarJP', label: '悠星JP' },
  { value: 'YoStarTW', label: '悠星TW' },
]

const form = reactive({ list: [] as AccountGroupItem[] })
const loading = ref(false)
const saving = ref(false)
const saved = ref(false)
const error = ref('')

async function load() {
  loading.value = true
  error.value = ''
  try {
    const groups = await settingsApi.getAll()
    const raw = groups.accounts?.list
    form.list = Array.isArray(raw)
      ? raw.filter(
          (x): x is AccountGroupItem =>
            typeof x === 'object' && x !== null && typeof (x as AccountGroupItem).name === 'string',
        )
      : []
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '读取账号组失败'
  } finally {
    loading.value = false
  }
}

async function save() {
  const invalid = form.list.filter((a) => !a.name.trim())
  if (invalid.length) {
    error.value = '账号名不能为空'
    return
  }
  saving.value = true
  error.value = ''
  saved.value = false
  try {
    await settingsApi.saveGroup('accounts', {
      list: form.list.map((a) => ({ name: a.name.trim(), client_type: a.client_type })),
    })
    saved.value = true
    window.setTimeout(() => { saved.value = false }, 2500)
  } catch (e: unknown) {
    error.value =
      (e as { response?: { data?: { detail?: string } }; message?: string })?.response?.data?.detail
      ?? '保存失败'
  } finally {
    saving.value = false
  }
}

function addAccount() {
  form.list.push({ name: '', client_type: 'Official' })
}

function removeAccount(i: number) {
  form.list.splice(i, 1)
}

function clientLabel(ct: string): string {
  return CLIENT_OPTS.find((o) => o.value === ct)?.label ?? ct
}

onMounted(load)
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <div>
        <b>账号组</b>
        <small>自动任务页的账号来源（StartUp 注入 account_name，引擎负责切换）</small>
      </div>
      <div class="hd-btns">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving" @click="save">
          {{ saving ? '保存中…' : '保存设置' }}
        </button>
      </div>
    </div>

    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 账号组已保存</div>

    <div class="f-row">
      <div class="f-label">
        <span>账号列表</span>
        <small>每个账号一行：名称 + 客户端类型；账号名须与游戏内登录账号一致</small>
      </div>
      <div class="f-col" style="flex: 2.2">
        <div v-if="form.list.length === 0" class="hint empty-hint">
          还没有账号——点「＋ 添加账号」新增，之后在「自动任务」页为时间槽选择账号
        </div>
        <div v-for="(a, i) in form.list" :key="i" class="acc-row">
          <input
            v-model="a.name"
            class="acc-name"
            type="text"
            placeholder="账号名（游戏内登录账号，如：账号A）"
          />
          <DropSelect v-model="a.client_type" :options="CLIENT_OPTS" />
          <span class="acc-tag">{{ clientLabel(a.client_type) }}</span>
          <button class="btn btn-sm btn-del" @click="removeAccount(i)">删除</button>
        </div>
        <button class="btn btn-ghost" style="align-self: flex-start" @click="addAccount">
          ＋ 添加账号
        </button>
      </div>
    </div>

    <p class="hint">
      行为说明：自动任务执行时按时间槽的账号顺序逐个执行——每个账号的 StartUp 任务注入
      account_name（+ client_type），引擎 AccountSwitchTask 自动切换到对应账号；
      切换/执行失败会跳过该账号并写入自动任务日志（不中断后续账号）。删除账号组条目不会
      影响已绑定到时间槽的账号（时间槽里可再删除）。
    </p>
  </div>
</template>

<style scoped>
.hd-btns { margin-left: auto; display: flex; gap: 8px; }
.btn { border: 1px solid var(--color-border-strong); background: var(--color-bg-subtle); color: var(--color-text-primary); padding: 6px 14px; font-size: var(--font-size-sm); cursor: pointer; transition: all var(--motion-duration-normal) var(--motion-easing-standard); }
.btn:hover:not(:disabled) { border-color: var(--color-brand-strong); color: var(--color-brand); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-gold { border-color: var(--color-brand-strong); color: var(--color-brand); background: rgba(216, 177, 106, 0.12); }
.btn-ghost { border-style: dashed; border-color: var(--color-border-strong); color: var(--color-text-secondary); }
.btn-sm { padding: 3px 10px; font-size: var(--font-size-2xs); }
.btn-del { border-color: var(--color-border-default); color: var(--color-text-secondary); }
.btn-del:hover { border-color: var(--color-danger); color: var(--color-danger); }

.acc-row { display: flex; align-items: center; gap: 10px; padding: 6px 0; border-bottom: 1px dashed var(--color-border-default); }
.acc-row:last-of-type { border-bottom: none; }
.acc-name {
  flex: 1; min-width: 160px;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 7px 11px; font-size: var(--font-size-md); outline: none;
}
.acc-name:focus { border-color: var(--color-brand); }
.acc-row .ds { min-width: 130px; }
.acc-tag {
  font-size: var(--font-size-2xs); color: var(--color-brand);
  border: 1px solid var(--color-brand-strong);
  padding: 1px 7px; letter-spacing: 0.5px; flex-shrink: 0;
  background: var(--color-bg-active);
}
.empty-hint { border: 1px dashed var(--color-border-default); padding: 14px; }
</style>
