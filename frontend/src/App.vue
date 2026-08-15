<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useDevicesStore } from '@/stores/devices'
import { useTasksStore } from '@/stores/tasks'
import { settingsApi } from '@/api/settings'
import { applyUiTheme } from '@/composables/useTheme'

const app = useAppStore()
const devices = useDevicesStore()
const tasks = useTasksStore()
const route = useRoute()

onMounted(() => {
  app.probeBackend()
  devices.fetchList()
  devices.detectDevices()
  // 应用已保存的界面主题（设置页可切换；自动模式下由 useTheme 定时重算，刷新后保持）
  settingsApi
    .getAll()
    .then((s) => applyUiTheme(s.ui ?? {}))
    .catch(() => undefined)
  setInterval(() => app.probeBackend(), 30_000)
  // 侧栏设备卡/任务芯片周期性刷新（设备列表变化时也会立即刷新）
  setInterval(() => {
    devices.fetchList()
    refreshTaskStatus()
  }, 15_000)
})

/** 对首台设备刷新任务运行状态（任务芯片用） */
async function refreshTaskStatus() {
  const d = devices.list[0]
  if (d) await tasks.fetchStatus(d.id)
}

// 设备列表首次加载完成后拉一次任务状态
watch(
  () => devices.list.length,
  () => {
    if (devices.list.length && tasks.status === null) refreshTaskStatus()
  },
)

// ── 导航分组（对应设计稿侧栏） ─────────────────
const navGroups = [
  {
    label: '指挥',
    items: [
      { to: '/', label: '作战总览', ico: '◆' },
      { to: '/tasks', label: '任务编排', ico: '▤' },
      { to: '/auto-tasks', label: '自动任务', ico: '◷' },
      { to: '/devices', label: '设备管理', ico: '◇' },
    ],
  },
  {
    label: '作战',
    items: [
      { to: '/toolbox', label: '工具箱', ico: '✚' },
      { to: '/logs', label: '作战日志', ico: '≡' },
    ],
  },
  {
    label: '后勤',
    items: [
      { to: '/settings', label: '设置', ico: '⚙' },
      { to: '/notifications', label: '通知', ico: '✉' },
    ],
  },
]

// ── 面包屑标题映射 ─────────────────────────────
const crumbMap: Record<string, { group: string; name: string }> = {
  '/': { group: '作战总览', name: '罗德岛指挥室' },
  '/tasks': { group: '任务编排', name: '任务队列' },
  '/auto-tasks': { group: '自动任务', name: '定时调度 · 账号轮换' },
  '/devices': { group: '设备管理', name: 'ADB 连接' },
  '/toolbox': { group: '工具箱', name: '识别与辅助' },
  '/logs': { group: '作战日志', name: '执行记录' },
  '/settings': { group: '设置', name: '系统配置' },
  '/notifications': { group: '通知', name: '事件推送' },
}

const crumb = computed(() => crumbMap[route.path] ?? { group: '页面', name: route.path })

// ── 顶部状态芯片（引擎 / 设备 / 任务） ───────────
const apiChip = computed(() => {
  switch (app.api.status) {
    case 'ok': return { cls: 'on', text: '引擎在线' }
    case 'degraded': return { cls: 'idle', text: '状态降级' }
    case 'starting': return { cls: 'idle', text: '启动中…' }
    case 'error': return { cls: 'off', text: '后端离线' }
    default: return { cls: 'idle', text: '待连接' }
  }
})

const devChip = computed(() => {
  const n = devices.onlineCount
  if (n > 0) return { cls: 'on', text: `设备在线 ${n}` }
  return devices.list.length ? { cls: 'idle', text: '设备离线' } : { cls: 'off', text: '无设备' }
})

const taskChip = computed(() => {
  if (tasks.running) return { cls: 'on', text: '任务运行中' }
  if (tasks.status && tasks.status.status !== 'idle') {
    return { cls: 'idle', text: `任务${tasks.status.status}` }
  }
  return { cls: 'idle', text: '任务待命' }
})

// ── 侧栏设备卡（真实设备，在线优先） ──────────────
const primaryDevice = computed(() => {
  const online = devices.list.find((d) => d.status === 'online')
  return online ?? devices.list[0] ?? null
})
const primaryAddr = computed(() => {
  if (!primaryDevice.value) return ''
  const d = primaryDevice.value
  return d.adb_port > 0 ? `adb ${d.adb_host}:${d.adb_port}` : `adb ${d.adb_host}（USB）`
})
const deviceStatusText = computed(() => {
  const map: Record<string, string> = {
    online: '已连接', offline: '离线', connecting: '连接中', error: '异常',
  }
  return map[primaryDevice.value?.status ?? ''] ?? primaryDevice.value?.status ?? ''
})
</script>

<template>
  <div class="app-shell">
    <!-- ══ 侧栏 ══ -->
    <aside class="sidebar">
      <!-- Logo -->
      <div class="logo">
        <span class="logo-mark"></span>
        <div class="logo-text">
          <b>Maa-Web</b>
          <small>ARKNIGHTS AUTOMATION</small>
        </div>
      </div>

      <!-- 导航 -->
      <nav class="nav">
        <template v-for="g in navGroups" :key="g.label">
          <div class="nav-label">{{ g.label }}</div>
          <RouterLink
            v-for="item in g.items"
            :key="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ active: item.to === '/' ? route.path === '/' : route.path.startsWith(item.to) }"
          >
            <span class="ico">{{ item.ico }}</span>
            <span class="label">{{ item.label }}</span>
          </RouterLink>
        </template>
      </nav>

      <!-- 侧栏底部：设备卡 -->
      <div class="sidebar-foot">
        <div class="dev-card">
          <template v-if="primaryDevice">
            <div class="row">
              <span class="dev-diamond"></span>
              <b>{{ primaryDevice.name }}</b>
              <span class="st" :class="'s-' + primaryDevice.status">
                <span class="dot"></span>{{ deviceStatusText }}
              </span>
            </div>
            <div class="addr">{{ primaryAddr }}</div>
            <div v-if="primaryDevice.last_error" class="dev-err" :title="primaryDevice.last_error">
              ⚠ {{ primaryDevice.last_error }}
            </div>
          </template>
          <template v-else>
            <div class="row">
              <span class="dev-diamond"></span>
              <b>未登记设备</b>
            </div>
            <div class="addr">请在设备管理中添加</div>
          </template>
        </div>
      </div>
    </aside>

    <!-- ══ 主区 ══ -->
    <div class="main">
      <header class="topbar">
        <div class="crumb">
          <b>{{ crumb.group }}</b>
          <span class="sep">/</span>
          <span>{{ crumb.name }}</span>
        </div>
        <div class="top-right">
          <span class="chip" :class="apiChip.cls"><span class="d"></span>{{ apiChip.text }}</span>
          <span class="chip" :class="devChip.cls"><span class="d"></span>{{ devChip.text }}</span>
          <span class="chip" :class="taskChip.cls"><span class="d"></span>{{ taskChip.text }}</span>
        </div>
      </header>

      <main class="content">
        <RouterView />
      </main>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  display: flex;
  height: 100%;
  position: relative;
  z-index: var(--z-index-content);
}

/* ── 侧栏 ─────────────────────────────── */
.sidebar {
  width: var(--sidebar-w);
  min-width: var(--sidebar-w);
  background: var(--color-bg-subtle);
  border-right: 1px solid var(--color-border-default);
  display: flex;
  flex-direction: column;
  position: relative;
}
.sidebar::before {
  content: "";
  position: absolute;
  top: 0; bottom: 0; left: 0; width: 2px;
  background: linear-gradient(180deg, transparent, var(--color-brand), transparent);
  opacity: 0.5;
}

/* Logo（双层菱形标记） */
.logo {
  padding: 24px 20px 18px;
  border-bottom: 1px solid var(--color-border-default);
  display: flex;
  align-items: center;
  gap: 10px;
}
.logo-mark {
  width: 36px; height: 36px; position: relative; flex-shrink: 0;
}
.logo-mark::before {
  content: ""; position: absolute; inset: 2px;
  border: 1.5px solid var(--color-brand);
  transform: rotate(45deg);
}
.logo-mark::after {
  content: ""; position: absolute; inset: 7px;
  border: 1px solid var(--color-brand-strong);
  transform: rotate(45deg); opacity: 0.6;
}
.logo-text b {
  font-size: var(--font-size-2xl);
  letter-spacing: var(--font-tracking-logo);
  color: var(--color-brand);
}
.logo-text small {
  display: block; margin-top: 4px;
  color: var(--color-text-tertiary);
  font-size: var(--font-size-2xs);
  letter-spacing: var(--font-tracking-label);
  font-family: var(--font-family-mono);
}

/* 导航 */
.nav { flex: 1; padding: 18px 14px; overflow-y: auto; }
.nav-label {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  letter-spacing: var(--font-tracking-widest);
  padding: 10px 12px 6px;
}
.nav-item {
  display: flex; align-items: center; gap: 11px;
  padding: 11px 12px; margin: 3px 0;
  border-radius: var(--radius-xs);
  color: var(--color-text-secondary);
  font-size: var(--font-size-lg);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
  position: relative;
}
.nav-item:hover { color: var(--color-text-primary); background: var(--color-bg-hover); }
.nav-item.active {
  color: var(--color-brand);
  background: linear-gradient(90deg, var(--color-bg-active), transparent);
}
.nav-item.active::before {
  content: "";
  position: absolute; left: -14px; top: 0; bottom: 0; width: 3px;
  background: var(--color-brand);
  clip-path: polygon(0 0, 100% 15%, 100% 85%, 0 100%);
}
.nav-item .ico { width: 18px; text-align: center; font-size: 15px; }
.nav-item .label { flex: 1; }

/* 侧栏底部设备卡 */
.sidebar-foot { padding: 14px; border-top: 1px solid var(--color-border-default); }
.dev-card {
  border: 1px solid var(--color-border-default);
  padding: 13px; background: var(--color-bg-panel);
  position: relative;
}
.dev-card::before {
  content: "";
  position: absolute; top: -1px; left: -1px;
  width: 8px; height: 8px;
  border-top: 2px solid var(--color-brand);
  border-left: 2px solid var(--color-brand);
}
.dev-card .row { display: flex; align-items: center; gap: 9px; }
.dev-diamond {
  width: 9px; height: 9px; flex-shrink: 0;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg);
  background: rgba(216, 177, 106, 0.3);
}
.dev-card b { font-size: var(--font-size-md); color: var(--color-text-primary); }
.dev-card .addr {
  color: var(--color-text-tertiary);
  font-size: var(--font-size-xs);
  font-family: var(--font-family-mono);
  margin-top: 4px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dev-card .st {
  display: inline-flex; align-items: center; gap: 5px;
  margin-left: auto; flex-shrink: 0;
  font-size: var(--font-size-2xs);
  border: 1px solid var(--color-border-default);
  padding: 2px 7px; letter-spacing: 1px;
}
.dev-card .st .dot { width: 6px; height: 6px; border: 1px solid; transform: rotate(45deg); }
.dev-card .s-online { color: var(--color-success); border-color: var(--color-success); }
.dev-card .s-online .dot { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.dev-card .s-offline { color: var(--color-text-tertiary); }
.dev-card .s-offline .dot { border-color: var(--color-text-tertiary); }
.dev-card .s-connecting { color: var(--color-warning); border-color: var(--color-warning); }
.dev-card .s-connecting .dot { border-color: var(--color-warning); background: rgba(201, 143, 78, 0.4); }
.dev-card .s-error { color: #d48f87; border-color: var(--color-danger); }
.dev-card .s-error .dot { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
.dev-card .dev-err {
  margin-top: 6px;
  font-size: var(--font-size-2xs); color: #d48f87;
  border: 1px solid var(--color-danger);
  background: rgba(176, 91, 83, 0.1);
  padding: 4px 8px; letter-spacing: 0.3px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}

/* ── 主区 ─────────────────────────────── */
.main { flex: 1; display: flex; flex-direction: column; min-width: 0; }

.topbar {
  height: var(--topbar-h);
  flex-shrink: 0;
  display: flex; align-items: center; gap: 16px;
  padding: 0 26px;
  border-bottom: 1px solid var(--color-border-default);
  background: var(--color-topbar-bg);
}
.crumb { font-size: var(--font-size-lg); color: var(--color-text-secondary); letter-spacing: 0.5px; }
.crumb b { color: var(--color-brand); }
.crumb .sep { margin: 0 6px; opacity: 0.6; }
.top-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }

/* 状态芯片 */
.chip {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border-default);
  padding: 5px 13px;
  display: flex; align-items: center; gap: 7px;
  letter-spacing: 0.5px;
}
.chip .d { width: 8px; height: 8px; border: 1px solid; transform: rotate(45deg); }
.chip.on  { border-color: var(--color-success); color: var(--color-success); }
.chip.on .d  { border-color: var(--color-success); background: rgba(159, 181, 111, 0.4); }
.chip.off { border-color: var(--color-danger); color: var(--color-danger); }
.chip.off .d { border-color: var(--color-danger); background: rgba(176, 91, 83, 0.4); }
.chip.idle .d { border-color: var(--color-text-tertiary); background: rgba(107, 105, 89, 0.4); }

/* 内容区：不滚动，由各视图自行管理滚动（LINK START 常驻底部） */
.content {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
</style>
