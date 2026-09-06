<script setup lang="ts">
/**
 * 像素画面板 —— 移植 MAA 客户端 ToolboxView 像素画交互（标准版）。
 * 导入：文件选择 / 拖拽 / 剪贴板粘贴（对齐客户端 v6.17）；
 * 参数：Fit 三模式 / 四档抖动（含插画优先）/ 对比度/亮度/饱和度 / 跳过纯白 / 滑动绘制 / 格子延迟；
 * 预览：24×24 色号矩阵实时渲染（参数变化防抖重算，PreparedImage 复用仅重跑量化）。
 * 通过 defineExpose 的 getResult() 产出引擎 params.pixel_paint 结构。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import {
  convert, prepare, renderPreviewData,
  GRID_SIZE, PREVIEW_PIXEL_SIZE,
  type BgraImage, type ConvertResult, type FitMode, type DitherMode, type PixelPaintResult,
} from '@/pixelPaint/PixelPaintHelper'
import '@/tasks/forms/field.css'

const props = defineProps<{ disabled?: boolean }>()

const prepared = ref<BgraImage | null>(null)
const result = ref<ConvertResult | null>(null)
const fileName = ref('')
const statusText = ref('')
const busy = ref(false)

const opts = reactive({
  fit: 'crop' as FitMode,
  dither: 'illustration' as DitherMode,
  contrast: 100,
  brightness: 100,
  saturation: 100,
  skipWhite: true,
  swipe: true,
  gridDelay: 0,
})

const fitOpts: Array<{ value: FitMode; label: string }> = [
  { value: 'crop', label: '裁剪填充（铺满画布）' },
  { value: 'contain', label: '完整包含（两侧留白）' },
  { value: 'stretch', label: '拉伸（忽略宽高比）' },
]
const ditherOpts: Array<{ value: DitherMode; label: string }> = [
  { value: 'illustration', label: '插画优先（干净色块）' },
  { value: 'floyd_steinberg', label: 'Floyd-Steinberg（照片渐变）' },
  { value: 'atkinson', label: 'Atkinson（柔和噪点）' },
  { value: 'none', label: '无抖动' },
]

const totalCells = GRID_SIZE * GRID_SIZE
const paintedCells = computed(() => result.value?.painted ?? 0)
const groupCount = computed(() => result.value?.groups.length ?? 0)
const hasImage = computed(() => prepared.value !== null && result.value !== null)

const fileInput = ref<HTMLInputElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)
const dragOver = ref(false)

// ── 导入 ────────────────────────────────────────────────────

function importImage(src: CanvasImageSource, w: number, h: number, name: string) {
  try {
    prepared.value = prepare(src, w, h)
    fileName.value = name
    statusText.value = ''
    recompute()
  } catch (e: unknown) {
    statusText.value = `图片处理失败：${(e as Error)?.message ?? e}`
  }
}

function importFile(file: File) {
  if (!file.type.startsWith('image/')) {
    statusText.value = '仅支持图片文件'
    return
  }
  const url = URL.createObjectURL(file)
  const img = new Image()
  img.onload = () => {
    importImage(img, img.naturalWidth, img.naturalHeight, file.name)
    URL.revokeObjectURL(url)
  }
  img.onerror = () => {
    statusText.value = '图片解码失败'
    URL.revokeObjectURL(url)
  }
  img.src = url
}

function onFileChange(ev: Event) {
  const f = (ev.target as HTMLInputElement).files?.[0]
  if (f) importFile(f)
  ;(ev.target as HTMLInputElement).value = ''
}

function onDrop(ev: DragEvent) {
  dragOver.value = false
  const f = ev.dataTransfer?.files?.[0]
  if (f) importFile(f)
}

// 文本粘贴（≤4 字）→ 渲染为黑字白底 24×24 位图（对齐客户端 RenderTextToBitmap 简化版）
function importText(text: string) {
  const cv = document.createElement('canvas')
  cv.width = GRID_SIZE
  cv.height = GRID_SIZE
  const ctx = cv.getContext('2d')
  if (!ctx) return
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, GRID_SIZE, GRID_SIZE)
  ctx.fillStyle = '#000'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  const chars = [...text].slice(0, 4)
  const cols = Math.min(chars.length, 2)
  const rows = Math.ceil(chars.length / cols)
  const cellW = GRID_SIZE / cols
  const cellH = GRID_SIZE / rows
  ctx.font = `${Math.floor(Math.min(cellW, cellH))}px "SimSun", serif`
  chars.forEach((c, i) => {
    ctx.fillText(c, (i % cols) * cellW + cellW / 2, Math.floor(i / cols) * cellH + cellH / 2)
  })
  importImage(cv, GRID_SIZE, GRID_SIZE, `文本「${chars.join('')}」`)
}

function onPaste(ev: ClipboardEvent) {
  if (props.disabled) return
  const items = ev.clipboardData?.items
  if (!items) return
  for (const it of items) {
    if (it.type.startsWith('image/')) {
      const f = it.getAsFile()
      if (f) {
        importFile(f)
        ev.preventDefault()
        return
      }
    }
  }
  const text = ev.clipboardData?.getData('text')?.trim()
  if (text && [...text].length <= 4 && [...text].length > 0) {
    importText(text)
    ev.preventDefault()
  }
}

onMounted(() => window.addEventListener('paste', onPaste))
onBeforeUnmount(() => window.removeEventListener('paste', onPaste))

// ── 转换与预览 ──────────────────────────────────────────────

let recomputeTimer: number | undefined
function scheduleRecompute() {
  if (recomputeTimer) clearTimeout(recomputeTimer)
  recomputeTimer = window.setTimeout(recompute, 120)
}

function recompute() {
  const img = prepared.value
  if (!img) return
  busy.value = true
  // setTimeout 让出主线程，参数拖动时 UI 不卡
  window.setTimeout(() => {
    try {
      result.value = convert(img, {
        fit: opts.fit,
        dither: opts.dither,
        contrast: opts.contrast,
        brightness: opts.brightness,
        saturation: opts.saturation,
        skipWhite: opts.skipWhite,
      })
      renderPreview()
    } catch (e: unknown) {
      statusText.value = `转换失败：${(e as Error)?.message ?? e}`
    } finally {
      busy.value = false
    }
  }, 0)
}

function renderPreview() {
  const cv = canvasEl.value
  const r = result.value
  if (!cv || !r) return
  const cellPx = Math.floor(PREVIEW_PIXEL_SIZE / GRID_SIZE) // 9 → 216px
  cv.width = GRID_SIZE * cellPx
  cv.height = GRID_SIZE * cellPx
  const ctx = cv.getContext('2d')
  if (!ctx) return
  ctx.putImageData(renderPreviewData(r.matrix, cellPx), 0, 0)
}

// ── 产出 ────────────────────────────────────────────────────

function getResult(): PixelPaintResult | null {
  const r = result.value
  if (!r || !r.groups.length) return null
  return {
    swipe: opts.swipe,
    grid_delay: Math.min(500, Math.max(0, Math.round(opts.gridDelay))),
    groups: r.groups.map((g) => ({ color: g.color, points: g.points })),
    painted: r.painted,
    group_count: r.groups.length,
  }
}

defineExpose({ getResult, hasImage })
</script>

<template>
  <div class="pp-panel" :class="{ disabled: props.disabled }">
    <!-- 导入区 -->
    <div
      class="pp-drop" :class="{ over: dragOver, filled: hasImage }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop.prevent="onDrop"
      @click="fileInput?.click()"
    >
      <canvas v-show="hasImage" ref="canvasEl" class="pp-canvas"></canvas>
      <div v-if="!hasImage" class="pp-hint">
        点击选择 / 拖入图片<br />
        <small>或直接粘贴图片 / ≤4 字文本（Ctrl+V）</small>
      </div>
    </div>
    <input ref="fileInput" type="file" accept="image/*" hidden @change="onFileChange" />
    <div v-if="fileName" class="pp-file">📷 {{ fileName }}</div>
    <div v-if="statusText" class="pp-status">{{ statusText }}</div>
    <div v-if="hasImage" class="pp-stat">
      {{ paintedCells }}/{{ totalCells }} 格 · {{ groupCount }} 种颜色
      <span v-if="busy"> · 计算中…</span>
    </div>

    <!-- 参数区 -->
    <div class="pp-params">
      <div class="f-row">
        <label class="f-label">构图方式</label>
        <select class="f-text" v-model="opts.fit" @change="scheduleRecompute">
          <option v-for="o in fitOpts" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="f-row">
        <label class="f-label">量化方式</label>
        <select class="f-text" v-model="opts.dither" @change="scheduleRecompute">
          <option v-for="o in ditherOpts" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
      </div>
      <div class="f-row">
        <label class="f-label">对比度 {{ opts.contrast }}%</label>
        <input type="range" min="50" max="200" step="1" v-model.number="opts.contrast" @input="scheduleRecompute" />
      </div>
      <div class="f-row">
        <label class="f-label">亮度 {{ opts.brightness }}%</label>
        <input type="range" min="50" max="200" step="1" v-model.number="opts.brightness" @input="scheduleRecompute" />
      </div>
      <div class="f-row">
        <label class="f-label">饱和度 {{ opts.saturation }}%</label>
        <input type="range" min="0" max="200" step="1" v-model.number="opts.saturation" @input="scheduleRecompute" />
      </div>
      <div class="f-row">
        <label class="f-label">跳过纯白格<small>白底不画</small></label>
        <span class="f-switch" :class="{ on: opts.skipWhite }" @click="opts.skipWhite = !opts.skipWhite; scheduleRecompute()"></span>
      </div>
      <div class="f-row">
        <label class="f-label">滑动绘制<small>同色连续格一次拖画完</small></label>
        <span class="f-switch" :class="{ on: opts.swipe }" @click="opts.swipe = !opts.swipe"></span>
      </div>
      <div class="f-row">
        <label class="f-label">格子延迟<small>每格额外等待（ms），画错调高</small></label>
        <input class="f-text" type="number" min="0" max="500" step="50" v-model.number="opts.gridDelay" />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pp-panel.disabled { opacity: 0.5; pointer-events: none; }
.pp-drop {
  width: 216px; height: 216px; margin: 0 auto;
  display: flex; align-items: center; justify-content: center;
  background: rgba(127, 127, 127, 0.08);
  border: 1px dashed var(--color-border-default, #888);
  border-radius: 4px; cursor: pointer; overflow: hidden;
}
.pp-drop.over { border-color: var(--color-brand, #d8b16a); background: rgba(216, 177, 106, 0.12); }
.pp-canvas { width: 216px; height: 216px; image-rendering: pixelated; }
.pp-hint { text-align: center; color: var(--color-text-tertiary, #999); font-size: var(--font-size-sm); line-height: 1.8; }
.pp-hint small { font-size: var(--font-size-xs); opacity: 0.8; }
.pp-file, .pp-status, .pp-stat {
  margin-top: 6px; text-align: center;
  font-size: var(--font-size-xs); color: var(--color-text-tertiary);
}
.pp-status { color: var(--color-danger, #c33); }
.pp-params { margin-top: 12px; }
.pp-params input[type='range'] { width: 100%; }
</style>
