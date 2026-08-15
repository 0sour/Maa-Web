<script setup lang="ts">
/**
 * 更新设置面板 —— 镜像源（GitHub/Mirror酱 + CDK 有效期）迁移自原设置页，
 * 新增「检查更新」区（引擎包本地/远端版本对比 + 一键更新，对齐 PRD §4.4.9）。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { settingsApi, type MirrorCdkCheckResult, type MirrorSourceSettings } from '@/api/settings'
import { resourcesApi, type ResourceStatus } from '@/api/resources'
import './panel.css'

const loading = ref(true)
const saving = ref(false)
const saved = ref(false)
const error = ref('')

// ── 镜像源（原设置页逻辑迁入） ──
const mirror = reactive({
  update_source: 'github',
  mirror_prefixes: '',
  mirrorchyan_cdk: '',
  http_proxy: '',
})
const cdkMasked = ref('')
const cdkConfigured = ref(false)
const cdkMessage = ref('')
const cdkStatus = ref<'none' | 'valid' | 'expiring' | 'expired' | 'unknown'>('none')
const effectivePrefixes = ref<string[]>([])
const showCdk = ref(false)
const checking = ref(false)
const cdkCheck = ref<MirrorCdkCheckResult | null>(null)

function cdkCls(s: string) {
  const map: Record<string, string> = {
    valid: 's-online', expiring: 's-connecting', expired: 's-error', unknown: 's-offline',
  }
  return map[s] ?? 's-offline'
}

function deriveCdkStatus(s: MirrorSourceSettings) {
  const rem = s.mirrorchyan_cdk_remaining_days
  if (!s.mirrorchyan_cdk_configured) cdkStatus.value = 'none'
  else if (rem == null) cdkStatus.value = 'expired'
  else if (rem <= 7) cdkStatus.value = 'expiring'
  else cdkStatus.value = 'valid'
}

const proxyTesting = ref(false)
const proxyResult = ref<{ ok: boolean; latency_ms: number | null; error: string | null } | null>(null)

async function testProxy() {
  proxyTesting.value = true
  proxyResult.value = null
  try {
    proxyResult.value = await settingsApi.proxyTest(mirror.http_proxy.trim())
  } catch (e: unknown) {
    proxyResult.value = {
      ok: false,
      latency_ms: null,
      error: (e as { message?: string })?.message ?? '测试失败',
    }
  } finally {
    proxyTesting.value = false
  }
}

async function checkCdk() {
  const cdk = mirror.mirrorchyan_cdk.trim()
  if (!cdk) {
    error.value = '请先输入 Mirror酱 CDK'
    return
  }
  checking.value = true
  error.value = ''
  cdkCheck.value = null
  try {
    const r = await settingsApi.checkCdk(cdk)
    cdkCheck.value = r
    cdkMessage.value = r.message
    if (r.ok) {
      cdkConfigured.value = true
      cdkStatus.value = (r.remaining_days != null && r.remaining_days <= 7) ? 'expiring' : 'valid'
      const s = await settingsApi.mirror()
      cdkMasked.value = s.mirrorchyan_cdk_masked
    } else if (r.code === 7001) {
      cdkStatus.value = 'expired'
    } else {
      cdkStatus.value = 'unknown'
    }
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? 'CDK 检查失败'
  } finally {
    checking.value = false
  }
}

// ── 检查更新（引擎包版本对比） ──
const res = ref<ResourceStatus | null>(null)
const resLoading = ref(false)
const resMsg = ref('')

async function checkUpdate() {
  resLoading.value = true
  resMsg.value = ''
  try {
    res.value = await resourcesApi.status()
    const r = res.value
    if (!r.installed) resMsg.value = '未安装引擎包，请点击「下载引擎包」'
    else if (r.update_available) resMsg.value = `有可用更新：本地 ${r.local_version} → 远端 ${r.remote_latest}`
    else resMsg.value = `已是最新（${r.local_version}）`
  } catch (e: unknown) {
    resMsg.value = (e as { message?: string })?.message ?? '检查更新失败'
  } finally {
    resLoading.value = false
  }
}

async function startUpdate() {
  if (res.value?.updating) return
  resMsg.value = ''
  try {
    const r = await resourcesApi.update()
    resMsg.value = r.message
    setTimeout(checkUpdate, 3000)
  } catch (e: unknown) {
    resMsg.value = (e as { message?: string })?.message ?? '更新失败'
  }
}

const cdkStateText = computed(() => {
  const map: Record<string, string> = {
    none: '未配置', valid: '有效', expiring: '即将到期', expired: '已过期', unknown: '未知',
  }
  return map[cdkStatus.value] ?? '未知'
})

// ── 载入 ──
async function load() {
  loading.value = true
  error.value = ''
  try {
    const s = await settingsApi.mirror()
    mirror.update_source = s.update_source
    mirror.mirror_prefixes = s.mirror_prefixes
    mirror.mirrorchyan_cdk = s.mirrorchyan_cdk
    mirror.http_proxy = s.http_proxy
    cdkMasked.value = s.mirrorchyan_cdk_masked
    cdkConfigured.value = s.mirrorchyan_cdk_configured
    cdkMessage.value = s.mirrorchyan_cdk_message
    effectivePrefixes.value = s.effective_prefix_list
    deriveCdkStatus(s)
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '读取设置失败'
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  saved.value = false
  error.value = ''
  try {
    const s = await settingsApi.saveMirror({
      update_source: mirror.update_source,
      mirror_prefixes: mirror.mirror_prefixes,
      http_proxy: mirror.http_proxy,
      ...(mirror.mirrorchyan_cdk !== '' ? { mirrorchyan_cdk: mirror.mirrorchyan_cdk } : {}),
    })
    mirror.mirrorchyan_cdk = s.mirrorchyan_cdk
    cdkMasked.value = s.mirrorchyan_cdk_masked
    cdkConfigured.value = s.mirrorchyan_cdk_configured
    cdkMessage.value = s.mirrorchyan_cdk_message
    effectivePrefixes.value = s.effective_prefix_list
    deriveCdkStatus(s)
    saved.value = true
  } catch (e: unknown) {
    error.value = (e as { message?: string })?.message ?? '保存失败'
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>更新设置</b>
      <span class="sub">镜像源 · 引擎包检查更新（对齐 MAA 客户端 VersionUpdate）</span>
      <div class="right">
        <button class="btn" :disabled="loading" @click="load">⟳ 刷新</button>
        <button class="btn btn-gold" :disabled="saving || loading" @click="save">{{ saving ? '保存中…' : '保存设置' }}</button>
      </div>
    </div>
    <div v-if="error" class="err-bar">⚠ {{ error }}</div>
    <div v-if="saved" class="ok-bar">✔ 设置已保存（立即生效，无需重启）</div>

    <!-- 镜像下载源 -->
    <div class="f-row">
      <label class="f-label">更新源</label>
      <div class="src-options">
        <button
          type="button"
          class="src-opt"
          :class="{ active: mirror.update_source === 'github' }"
          @click="mirror.update_source = 'github'"
        >
          <b>GitHub 官方源</b>
          <span>直连 / 自定义镜像加速 · 免费</span>
        </button>
        <button
          type="button"
          class="src-opt"
          :class="{ active: mirror.update_source === 'mirrorchyan' }"
          @click="mirror.update_source = 'mirrorchyan'"
        >
          <b>Mirror酱（MirrorChyan）</b>
          <span>MAA 高速更新源 · 需 CDK · Linux 部署请用 GitHub 源</span>
        </button>
      </div>
    </div>

    <template v-if="mirror.update_source === 'github'">
      <div class="f-row f-col">
        <label class="f-label">ghproxy 镜像前缀</label>
        <textarea v-model="mirror.mirror_prefixes" rows="2" placeholder="https://ghproxy.net/, https://ghfast.top/"></textarea>
        <p class="hint">多个前缀用逗号或换行分隔，留空 = GitHub 官方直连。客户端并发测速择优、失败自动切换下一源。</p>
      </div>
      <div class="f-row">
        <label class="f-label">当前生效前缀</label>
        <div class="f-ctrl">
          <span v-for="p in effectivePrefixes" :key="p" class="chip">{{ p }}</span>
          <span v-if="!effectivePrefixes.length" class="hint dim">官方直连（未配置镜像）</span>
        </div>
      </div>
      <div class="f-row f-col">
        <label class="f-label">HTTP 代理 <small>可选</small></label>
        <div class="proxy-row">
          <input v-model="mirror.http_proxy" placeholder="http://192.168.10.110:7890" spellcheck="false" />
          <button class="btn btn-sm" :disabled="proxyTesting" @click="testProxy">
            {{ proxyTesting ? '测试中…' : '测试连通性' }}
          </button>
        </div>
        <p v-if="proxyResult" class="proxy-result" :class="proxyResult.ok ? 'ok' : 'bad'">
          {{ proxyResult.ok ? `✔ 代理连通（${proxyResult.latency_ms}ms）` : `✖ 代理不可达：${proxyResult.error}` }}
        </p>
        <p class="hint">GitHub 官方直连不通时可填代理地址（如 NAS 上 clash 的 7890 端口）；留空 = 直连。对版本查询与引擎包下载均生效。</p>
      </div>
    </template>

    <template v-else>
      <div class="f-row f-col">
        <label class="f-label">CDK <small v-if="cdkMasked">已配置：{{ cdkMasked }}</small></label>
        <div class="cdk-row">
          <div class="cdk-input-wrap">
            <input
              v-model="mirror.mirrorchyan_cdk"
              :type="showCdk ? 'text' : 'password'"
              placeholder="粘贴 Mirror酱 CDK"
              autocomplete="off"
              spellcheck="false"
            />
            <button type="button" class="cdk-eye" :class="{ on: showCdk }" :title="showCdk ? '隐藏 CDK' : '显示完整 CDK'" @click="showCdk = !showCdk">
              {{ showCdk ? '◉' : '◌' }}
            </button>
          </div>
          <button class="btn" :disabled="checking" @click="checkCdk">{{ checking ? '检查中…' : '⌁ 检查有效期' }}</button>
        </div>
        <p class="hint">CDK 默认掩码显示；点击右侧眼睛查看完整。修改后需重新「检查有效期」刷新到期时间。</p>
        <p class="hint warn">⚠️ Mirror酱的 MAA 资源仅发布 Windows 应用本体，Linux（NAS）部署无对应引擎包——请改用 GitHub 官方源（可配 ghproxy 镜像加速）。</p>
      </div>
      <div class="cdk-state">
        <span class="st" :class="cdkCls(cdkStatus)"><span class="dot"></span>CDK {{ cdkStateText }}</span>
        <span v-if="cdkMessage" class="cdk-msg">{{ cdkMessage }}</span>
      </div>
    </template>

    <!-- 检查更新 -->
    <div class="f-sec">引擎包更新</div>
    <div class="f-row">
      <label class="f-label">检查更新<small>对比本地与远端引擎包版本（按当前更新源）</small></label>
      <div class="f-ctrl">
        <button class="btn" :disabled="resLoading" @click="checkUpdate">{{ resLoading ? '检查中…' : '⌁ 检查更新' }}</button>
        <button
          class="btn btn-gold"
          :disabled="!res || res.updating || !res.update_available"
          @click="startUpdate"
        >{{ res?.updating ? '更新中…' : '更新引擎包' }}</button>
      </div>
    </div>
    <div v-if="resMsg" class="upd-msg">{{ resMsg }}</div>
    <div v-if="res" class="upd-detail">
      本地 {{ res.local_version ?? '未安装' }} · 远端 {{ res.remote_latest ?? '—' }}
      <template v-if="res.progress > 0">· 进度 {{ Math.round(res.progress * 100) }}%</template>
      <template v-if="res.update_error">· ⚠ {{ res.update_error }}</template>
    </div>
  </div>
</template>

<style scoped>
.proxy-row { display: flex; align-items: center; gap: 8px; }
.proxy-row input {
  flex: 1;
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 9px 12px; font-size: var(--font-size-md); outline: none;
  font-family: inherit; border-radius: 0;
}
.proxy-row input::placeholder { color: var(--color-text-tertiary); }
.proxy-row input:focus { border-color: var(--color-brand-strong); }
.proxy-result { font-size: var(--font-size-sm); margin: 0; }
.proxy-result.ok { color: var(--color-success); }
.proxy-result.bad { color: var(--color-danger); }
.src-options { display: flex; gap: 10px; flex-wrap: wrap; flex: 1; }
.src-opt {
  flex: 1; min-width: 200px;
  display: flex; flex-direction: column; gap: 4px;
  text-align: left; padding: 10px 12px;
  border: 1px solid var(--color-border-default);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  cursor: pointer;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.src-opt b { font-size: var(--font-size-lg); letter-spacing: 0.5px; }
.src-opt span { font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
.src-opt:hover { border-color: var(--color-brand-strong); }
.src-opt.active { border-color: var(--color-brand-strong); background: rgba(216, 177, 106, 0.12); box-shadow: var(--shadow-glow-sm); }
.src-opt.active b { color: var(--color-brand); }

textarea {
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default);
  padding: 8px 11px; font-size: var(--font-size-md);
  font-family: var(--font-family-mono); outline: none; resize: vertical;
}
textarea:focus { border-color: var(--color-brand); }

.chip {
  font-family: var(--font-family-mono); font-size: var(--font-size-xs);
  color: var(--color-brand); border: 1px solid var(--color-border-strong);
  padding: 3px 10px; letter-spacing: 0.3px;
}
.hint.dim { opacity: 0.75; }

.cdk-row { display: flex; gap: 10px; align-items: stretch; }
.cdk-input-wrap {
  flex: 1; display: flex; align-items: center; gap: 4px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
}
.cdk-input-wrap:focus-within { border-color: var(--color-brand); }
.cdk-input-wrap input {
  flex: 1; min-width: 0;
  background: transparent; color: var(--color-text-primary);
  border: none; padding: 8px 6px 8px 11px;
  font-size: var(--font-size-md); font-family: var(--font-family-mono); outline: none;
}
.cdk-eye {
  width: 34px; flex-shrink: 0;
  color: var(--color-text-tertiary);
  border-left: 1px solid var(--color-border-default);
  cursor: pointer;
}
.cdk-eye.on { color: var(--color-brand); }

.cdk-state { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.st {
  display: inline-flex; align-items: center; gap: 6px;
  font-size: var(--font-size-xs); padding: 3px 10px;
  border: 1px solid var(--color-border-default); letter-spacing: 1px;
}
.st .dot { width: 7px; height: 7px; border: 1px solid; transform: rotate(45deg); }
.s-online { color: var(--color-success); border-color: var(--color-success); }
.s-online .dot { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.s-connecting { color: var(--color-warning); border-color: var(--color-warning); }
.s-connecting .dot { border-color: var(--color-warning); background: rgba(201, 143, 78, 0.4); }
.s-error { color: #d48f87; border-color: var(--color-danger); }
.s-error .dot { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
.s-offline { color: var(--color-text-tertiary); }
.s-offline .dot { border-color: var(--color-text-tertiary); }
.cdk-msg { font-size: var(--font-size-md); color: var(--color-text-secondary); }

.f-sec {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  letter-spacing: 1px; margin: 6px 0 0; padding-top: 10px;
  border-top: 1px dashed var(--color-border-default);
}
.upd-msg { font-size: var(--font-size-md); color: var(--color-brand); }
.upd-detail {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  font-family: var(--font-family-mono); letter-spacing: 0.3px;
}
</style>
