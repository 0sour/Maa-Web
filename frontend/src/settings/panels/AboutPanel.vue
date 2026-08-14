<script setup lang="ts">
/**
 * 关于我们面板 —— 对齐 MAA 客户端 AboutUserControl（PRD §4.4.15）。
 * 应用版本（/api 元信息）+ 引擎版本（/resources/status）+ 官方链接。
 */
import { onMounted, ref } from 'vue'
import { httpRoot } from '@/api/http'
import { resourcesApi } from '@/api/resources'
import './panel.css'

const appVersion = ref('—')
const engineVersion = ref('—')
const engineSource = ref('')
const loadErr = ref('')
/** 已裁剪清单默认折叠 */
const showTrimmed = ref(false)

onMounted(async () => {
  try {
    const meta = await httpRoot.get<{ version?: string }>('/api')
    appVersion.value = meta.data?.version ?? '—'
  } catch {
    /* 保持默认值 */
  }
  try {
    const r = await resourcesApi.status()
    engineVersion.value = r.local_version ?? '未安装'
    engineSource.value = r.source || ''
  } catch (e: unknown) {
    loadErr.value = (e as { message?: string })?.message ?? '引擎版本读取失败'
  }
})

/** 本项目链接 */
const links = [
  { label: 'Maa-Web 仓库', url: 'https://github.com/0sour/Maa-Web', desc: '本项目 GitHub 仓库' },
  { label: '项目文档', url: 'https://github.com/0sour/Maa-Web/tree/main/docs', desc: 'PRD / 架构 / 部署指南 / 会话记录' },
]

/** 相关项目（MAA 生态） */
const related = [
  { label: 'MAA 官方仓库', url: 'https://github.com/MaaAssistantArknights/MaaAssistantArknights', desc: 'MAA 引擎核心（本项目运行依赖）' },
  { label: 'MAA 官网', url: 'https://maa.plus/', desc: 'MAA 文档与公告' },
  { label: 'B 站账号', url: 'https://space.bilibili.com/161972295', desc: 'MAA 官方 B 站' },
]

/** 已裁剪的 MAA 客户端设置项目及原因（WebUI 不适用 / 决定不做） */
const trimmed = [
  { name: '切换配置', reason: '多用户需求将走数据分离，不做配置切换（2026-08-14 决定）' },
  { name: '远程控制设置', reason: 'NAS 部署通过端口访问本身即远程控制；MAA 客户端远程控制协议（手机端控制 PC）场景不适用' },
  { name: '成就设置', reason: 'MAA 客户端成就多为 UI 交互类（时间管理大师 / 全频道广播等），与 WebUI 交互不一致' },
  { name: '性能设置（GPU 推理加速）', reason: 'DirectML 仅 Windows 桌面支持，NAS 部署无独立 GPU 推理需求' },
  { name: '启动设置', reason: '桌面客户端专属（开机自启 / 模拟器启动），WebUI 运行于 NAS 服务' },
  { name: '背景设置', reason: '桌面壁纸设置，WebUI 无桌面环境' },
  { name: '热键设置', reason: '桌面全局热键，WebUI 无桌面环境' },
  { name: '运行设置 · 阻止睡眠 / 休眠', reason: 'NAS 服务常驻运行，无需阻止系统睡眠' },
]
</script>

<template>
  <div class="panel-card">
    <div class="card-hd">
      <span class="diamond"></span>
      <b>关于我们</b>
      <span class="sub">对齐 MAA 客户端 About · 版本与链接</span>
    </div>

    <div class="f-row">
      <label class="f-label">Maa-Web 版本</label>
      <div class="f-ctrl"><code class="ver">v{{ appVersion }}</code></div>
    </div>
    <div class="f-row">
      <label class="f-label">MAA 引擎版本</label>
      <div class="f-ctrl">
        <code class="ver">{{ engineVersion }}</code>
        <span v-if="engineSource" class="src-tag">{{ engineSource }}</span>
      </div>
    </div>
    <div v-if="loadErr" class="err-bar">⚠ {{ loadErr }}</div>

    <div class="f-sec">本项目</div>
    <div class="link-list">
      <a v-for="l in links" :key="l.url" class="link-item" :href="l.url" target="_blank" rel="noopener">
        <span class="diamond"></span>
        <span class="nm">{{ l.label }}</span>
        <span class="desc">{{ l.desc }}</span>
      </a>
    </div>

    <div class="f-sec">相关项目（MAA 生态）</div>
    <div class="link-list">
      <a v-for="l in related" :key="l.url" class="link-item" :href="l.url" target="_blank" rel="noopener">
        <span class="diamond"></span>
        <span class="nm">{{ l.label }}</span>
        <span class="desc">{{ l.desc }}</span>
      </a>
    </div>

    <!-- 已裁剪清单：默认折叠，放页面最底部 -->
    <div class="f-sec trim-hd" role="button" tabindex="0" @click="showTrimmed = !showTrimmed" @keydown.enter="showTrimmed = !showTrimmed">
      已裁剪 · WebUI 不适用
      <span class="arr">{{ showTrimmed ? '▾' : '▸' }}</span>
    </div>
    <div v-if="showTrimmed" class="trim-list">
      <div v-for="t in trimmed" :key="t.name" class="trim-item">
        <span class="diamond"></span>
        <b>{{ t.name }}</b>
        <span class="reason">{{ t.reason }}</span>
      </div>
    </div>

    <p class="hint">本项目仅供学习交流使用。明日方舟为鹰角网络的注册商标，本项目与鹰角网络无任何关联。</p>
  </div>
</template>

<style scoped>
.ver {
  font-family: var(--font-family-mono); font-size: var(--font-size-md);
  color: var(--color-brand); letter-spacing: 0.5px;
}
.src-tag {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  border: 1px solid var(--color-border-default); padding: 2px 8px;
}
.f-sec {
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
  letter-spacing: 1px; margin-top: 6px; padding-top: 10px;
  border-top: 1px dashed var(--color-border-default);
}
.trim-hd {
  display: flex; align-items: center; gap: 6px;
  cursor: pointer; user-select: none;
  transition: color var(--motion-duration-fast) var(--motion-easing-standard);
}
.trim-hd:hover { color: var(--color-brand); }
.trim-hd .arr { font-size: 10px; }
.trim-list { display: flex; flex-direction: column; gap: 4px; }
.trim-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
}
.trim-item .diamond {
  width: 9px; height: 9px; flex-shrink: 0;
  border: 1px solid var(--color-text-tertiary); transform: rotate(45deg);
}
.trim-item b { color: var(--color-text-primary); font-size: var(--font-size-md); flex-shrink: 0; }
.trim-item .reason { margin-left: auto; font-size: var(--font-size-xs); color: var(--color-text-tertiary); text-align: right; }
.link-list { display: flex; flex-direction: column; gap: 4px; }
.link-item {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px;
  background: var(--color-bg-subtle);
  border: 1px solid var(--color-border-default);
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.link-item:hover { border-color: var(--color-brand-strong); box-shadow: var(--shadow-glow-sm); }
.link-item .diamond {
  width: 9px; height: 9px; flex-shrink: 0;
  border: 1px solid var(--color-brand); transform: rotate(45deg);
}
.link-item .nm { color: var(--color-text-primary); font-size: var(--font-size-md); }
.link-item:hover .nm { color: var(--color-brand); }
.link-item .desc { margin-left: auto; font-size: var(--font-size-xs); color: var(--color-text-tertiary); }
</style>
