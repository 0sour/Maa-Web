<script setup lang="ts">
/**
 * 设置中心 —— 对齐 MAA 客户端设置窗口（SettingKey 枚举，zh-cn 中文名）。
 * 「切换配置」已裁掉（用户决定：多用户需求走数据分离）；14 组导航。
 * 左侧分组导航（落地分组可点，规划中/不适用分组置灰）；右侧为对应面板。
 */
import { ref } from 'vue'
import GameSettingsPanel from '@/settings/panels/GameSettingsPanel.vue'
import ConnectionSettingsPanel from '@/settings/panels/ConnectionSettingsPanel.vue'
import UiSettingsPanel from '@/settings/panels/UiSettingsPanel.vue'
import UpdateSettingsPanel from '@/settings/panels/UpdateSettingsPanel.vue'
import IssueReportPanel from '@/settings/panels/IssueReportPanel.vue'
import AboutPanel from '@/settings/panels/AboutPanel.vue'
import ExternalNotificationPanel from '@/settings/panels/ExternalNotificationPanel.vue'
import AccountGroupsPanel from '@/settings/panels/AccountGroupsPanel.vue'

interface SettingGroup {
  key: string
  label: string
  ready: boolean
  /** 已落地（独立页面）：指引说明 */
  done?: string
}

// 对齐 MAA 客户端 SettingKey 枚举，已裁剪：切换配置（多用户走数据分离）、
// 性能/启动/背景/热键（桌面专属）、远程控制（NAS 端口访问即远程）、成就（UI 交互不一致）
// ——原因见「关于我们」面板。
const GROUPS: SettingGroup[] = [
  {
    key: 'schedule', label: '自动任务', ready: true,
    done: '功能已落地：请使用侧栏「指挥 → 自动任务」页（时间槽 × 账号 × 方案，定时执行与账号轮换）',
  },
  { key: 'game', label: '运行设置', ready: true },
  { key: 'connection', label: '连接设置', ready: true },
  { key: 'accounts', label: '账号组', ready: true },
  { key: 'ui', label: '界面设置', ready: true },
  { key: 'notification', label: '外部通知', ready: true },
  { key: 'update', label: '更新设置', ready: true },
  { key: 'issue', label: '问题反馈', ready: true },
  { key: 'about', label: '关于我们', ready: true },
]

const active = ref('game')
const current = () => GROUPS.find((g) => g.key === active.value) ?? GROUPS[0]
</script>

<template>
  <div class="st-wrap">
    <div class="st-top">
      <div class="st-title">
        <span class="diamond"></span>
        <div>
          <h2>设置</h2>
          <p class="sub">对齐 MAA 客户端设置窗口 · 9 组（已裁剪桌面专属 / 配置切换 / 远程控制 / 成就）</p>
        </div>
      </div>
    </div>

    <div class="st-body">
      <!-- 左侧分组导航 -->
      <nav class="st-nav">
        <button
          v-for="g in GROUPS"
          :key="g.key"
          type="button"
          class="nav-item"
          :class="{ on: g.key === active, off: !g.ready }"
          :disabled="!g.ready"
          @click="active = g.key"
        >
          <span class="mark"></span>
          <span class="nm">{{ g.label }}</span>
        </button>
      </nav>

      <!-- 右侧面板 -->
      <div class="st-content">
        <GameSettingsPanel v-if="active === 'game'" />
        <ConnectionSettingsPanel v-else-if="active === 'connection'" />
        <AccountGroupsPanel v-else-if="active === 'accounts'" />
        <UiSettingsPanel v-else-if="active === 'ui'" />
        <UpdateSettingsPanel v-else-if="active === 'update'" />
        <IssueReportPanel v-else-if="active === 'issue'" />
        <AboutPanel v-else-if="active === 'about'" />
        <ExternalNotificationPanel v-else-if="active === 'notification'" />
        <div v-else class="ph panel-card">
          <div class="ph-diamond"><span>◇</span></div>
          <h3>{{ current()?.label }}</h3>
          <span v-if="current()?.done" class="badge done">已落地</span>
          <p v-if="current()?.done" class="reason">{{ current()?.done }}</p>
          <p class="hint dim">字段映射见 docs/PRD.md §4.4 设置中心。</p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.st-wrap {
  flex: 1; min-height: 0;
  overflow-y: auto;
  padding: 24px 26px;
  display: flex; flex-direction: column; gap: 14px;
}

.st-top { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.st-title { display: flex; align-items: center; gap: 12px; }
.st-title .diamond {
  width: 14px; height: 14px;
  border: 1px solid var(--color-brand);
  transform: rotate(45deg);
  flex-shrink: 0;
  background: rgba(216, 177, 106, 0.15);
}
.st-title h2 { font-size: var(--font-size-2xl); letter-spacing: var(--font-tracking-wide); }
.st-title .sub { font-size: var(--font-size-sm); color: var(--color-text-tertiary); margin-top: 3px; letter-spacing: 0.5px; }

/* ── 双栏布局 ── */
.st-body { display: grid; grid-template-columns: 210px 1fr; gap: 14px; align-items: start; }
@media (max-width: 900px) { .st-body { grid-template-columns: 1fr; } }

/* ── 左侧导航 ── */
.st-nav {
  display: flex; flex-direction: column; gap: 3px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  padding: 8px;
  position: sticky; top: 0;
}
.nav-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  background: none; border: none; cursor: pointer;
  color: var(--color-text-secondary);
  font-size: var(--font-size-md); letter-spacing: 0.5px;
  text-align: left;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.nav-item .mark {
  width: 8px; height: 8px; flex-shrink: 0;
  border: 1px solid var(--color-border-strong);
  transform: rotate(45deg);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.nav-item:hover:not(:disabled) { color: var(--color-brand); background: var(--color-bg-hover); }
.nav-item.on {
  color: var(--color-brand);
  background: var(--color-bg-active);
  border-left: 2px solid var(--color-brand);
}
.nav-item.on .mark { border-color: var(--color-brand); background: rgba(216, 177, 106, 0.3); }
.nav-item.off { opacity: 0.4; cursor: not-allowed; }
.nav-item .nm { flex: 1; min-width: 0; }
.nav-item .tag {
  font-size: var(--font-size-2xs); color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-default);
  padding: 0 5px; letter-spacing: 1px; flex-shrink: 0;
}

/* ── 右侧内容 ── */
.st-content { min-width: 0; }
.st-content .panel-card {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
}

.ph { align-items: center; text-align: center; padding: 56px 24px; gap: 10px; }
.ph-diamond {
  width: 44px; height: 44px; margin: 0 auto 14px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--color-brand-strong);
  transform: rotate(45deg);
  color: var(--color-brand); font-size: 16px;
}
.ph-diamond span { transform: rotate(-45deg); display: block; }
.ph h3 { font-size: var(--font-size-2xl); letter-spacing: var(--font-tracking-wide); }
.ph .reason { color: var(--color-text-secondary); font-size: var(--font-size-md); max-width: 420px; line-height: 1.8; }
.ph .badge {
  font-size: var(--font-size-2xs); letter-spacing: 1.5px;
  padding: 3px 10px; border: 1px solid var(--color-border-default);
  color: var(--color-text-tertiary);
}
.ph .badge.done { color: var(--color-success); border-color: var(--color-success); }
.ph .hint.dim { opacity: 0.75; }
</style>
