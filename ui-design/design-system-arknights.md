# Maa-Web · 明日方舟主题设计规范

> 版本：v1.0 ｜ 更新日期：2026-08-10 ｜ 状态：待评审
> 本规范从设计稿 `03-arknights.html`（同目录）提炼，作为 Maa-Web 前端（Vue3 + TypeScript）的实现契约。所有取值以设计稿为准，标注 `[Data-backed]`；未在设计稿中出现、由惯例补齐的取值标注 `[Expert judgment]`。

---

## 1. 设计理念与风格定位

**一句话定位**：把 Maa-Web 做成「罗德岛指挥室」——灰蓝金属底、金色点缀、锐利几何，向明日方舟的 UI 语言致敬，同时保留操控台的工程感。

### 1.1 三个关键词

| 关键词 | 含义 | 落地方式 |
|--------|------|---------|
| 锐利（Sharp） | 拒绝圆角，用直角与斜切建立硬朗轮廓 | 全站 `radius: 0`；关键元素用 `clip-path` 斜切一角 |
| 金属（Steel） | 灰蓝冷调底色，模拟舰桥金属面板 | 4 层深色背景梯度 + 低对比边框 |
| 金色（Gold） | 少量暖金高亮，作为操作与状态的主强调 | 仅用于：激活态、主按钮、状态标签、数值强调 |

### 1.2 设计原则

1. **金色是稀缺资源**：金色只服务于「当前操作」「关键状态」「主行动」三类语义，页面任何一屏金色元素不超过 5 处 `[Expert judgment]`。
2. **硬朗胜于圆润**：不用 `border-radius` 表达层级，改用边框、斜切、菱形角标。方形是默认，斜切是强调。
3. **对角斜切是品牌记忆点**：主行动按钮（Link Start）、激活导航指示、面板标题菱形角标统一使用 45° 斜切/旋转几何，形成一眼可识别的形制。
4. **数值用衬线**：KPI 大数字使用衬线字体（Georgia），与界面无衬线形成对比，营造「仪表读数」质感。

### 1.3 禁止项

- 禁止大范围使用紫色渐变（与方舟灰金调性冲突）。
- 禁止玻璃拟态/大面积模糊（破坏金属面板质感）。
- 禁止圆角胶囊按钮与圆角卡片（与锐利原则冲突）。
- 禁止在次要元素上使用金色（稀释强调语义）。

---

## 2. Token 基础（Design Token Foundation）

### 2.1 命名规范

统一 `kebab-case`，与 CSS 自定义属性、TypeScript 对象、Figma 变量名一一对应，无需转换。

| 类别 | 模式 | 示例 |
|------|------|------|
| 颜色（视觉层） | `color-{role}-{shade}` | `color-gold-500`、`color-neutral-800` |
| 颜色（语义层） | `color-{semantic-role}` | `color-brand`、`color-text-primary`、`color-bg-surface` |
| 间距 | `spacing-{size}` | `spacing-sm`、`spacing-md`、`spacing-lg` |
| 字体族 | `font-family-{role}` | `font-family-sans`、`font-family-serif`、`font-family-mono` |
| 字号 | `font-size-{scale}` | `font-size-sm`、`font-size-md`、`font-size-lg` |
| 字重 | `font-weight-{name}` | `font-weight-regular`、`font-weight-bold` |
| 行高 | `font-lineheight-{scale}` | `font-lineheight-tight`、`font-lineheight-normal` |
| 字距 | `font-tracking-{name}` | `font-tracking-wide`、`font-tracking-widest` |
| 圆角 | `radius-{size}` | `radius-none`、`radius-xs` |
| 阴影 | `shadow-{level}` | `shadow-glow-sm`、`shadow-glow-lg` |
| 动效时长 | `motion-duration-{speed}` | `motion-duration-fast`、`motion-duration-normal` |
| 动效缓动 | `motion-easing-{name}` | `motion-easing-standard` |
| z 层级 | `z-index-{layer}` | `z-index-sticky`、`z-index-overlay` |
| 组件前缀 | `{component}-{property}` | `task-bg-selected`、`chip-border` |

### 2.2 色彩系统

#### 视觉层 — 色板（全部取自设计稿 `[Data-backed]`）

| Token | 值 | 用途 |
|-------|-----|------|
| `color-bg-base` | `#1a1d22` | 页面主背景（顶部） |
| `color-bg-deep` | `#14161b` | 页面背景（底部渐变收尾） |
| `color-surface-700` | `#23272e` | 面板/卡片背景 |
| `color-surface-800` | `#1c2026` | 次级面板、输入区、侧栏 |
| `color-border-default` | `#3a3f49` | 常规边框、分隔线 |
| `color-border-strong` | `#4a5060` | 强调边框、输入框描边 |
| `color-text-primary` | `#e8e6df` | 主文字 |
| `color-text-secondary` | `#9b9688` | 次级文字、说明 |
| `color-text-tertiary` | `#6b6759` | 弱化文字、占位 |
| `color-gold-400` | `#d8b16a` | 品牌主金（基础） |
| `color-gold-600` | `#a8853f` | 品牌深金（边框、次级强调） |
| `color-steel` | `#8b93a3` | 中性钢蓝（中性点缀） |
| `color-accent` | `#5d7a8a` | 蓝灰强调（备用语义） |
| `color-success` | `#9fb56f` | 成功/在线 |
| `color-warning` | `#c98f4e` | 警告/排队 |
| `color-danger` | `#b05b53` | 错误/离线/停止 |

#### 语义层 — 角色 Token

| Token | 引用 | 用途 |
|-------|------|------|
| `color-brand` | `color-gold-400` | 品牌元素：logo、激活导航、主按钮文字 |
| `color-brand-strong` | `color-gold-600` | 品牌边框、次级强调 |
| `color-bg-page` | `color-bg-base` | 页面背景 |
| `color-bg-panel` | `color-surface-700` | 面板、卡片 |
| `color-bg-subtle` | `color-surface-800` | 输入框、代码区、嵌套区 |
| `color-bg-active` | `rgba(216,177,106,.08)` | 激活项背景（金色 8% 透明） |
| `color-bg-hover` | `rgba(216,177,106,.05)` | 悬停项背景（金色 5% 透明） |
| `color-border-default` | `color-border-default` | 常规边框 |
| `color-border-focus` | `color-gold-600` | 聚焦描边 |
| `color-text-primary` | `color-text-primary` | 主文字 |
| `color-text-secondary` | `color-text-secondary` | 次级文字 |
| `color-text-tertiary` | `color-text-tertiary` | 弱化文字 |
| `color-text-inverse` | `#14161b` | 金色/亮底上的深色文字 |
| `color-status-success` | `color-success` | 成功、在线、已完成 |
| `color-status-warning` | `color-warning` | 警告、排队、待命 |
| `color-status-danger` | `color-danger` | 错误、离线、停止 |

> 语义层全部引用视觉层，不写死十六进制——后续换主题只改视觉层。

### 2.3 间距系统

基数 4px `[Expert judgment]`（从设计稿实际取值归纳）：

| Token | 值 | 用途 |
|-------|-----|------|
| `spacing-2xs` | `4px` | 极小间隙、图标与文字 |
| `spacing-xs` | `6px` | 紧凑间隙 |
| `spacing-sm` | `8px` | 列表项内部、输入内部 |
| `spacing-md` | `12px` | 导航项内边距、参数行距 |
| `spacing-lg` | `16px` | KPI 内边距、面板标题内边距 |
| `spacing-xl` | `20px` | 内容区左右边距 |
| `spacing-2xl` | `24px` | 内容区顶部、卡片间距 |
| `spacing-3xl` | `26px` | 内容区主边距（设计稿 `24px 26px`） |

### 2.4 字体排印

| Token | 值 | 用途 |
|-------|-----|------|
| `font-family-sans` | `"Microsoft YaHei", "PingFang SC", sans-serif` | 正文、界面文字 `[Data-backed]` |
| `font-family-serif` | `"Georgia", "STSong", serif` | KPI 大数字、数值强调 `[Data-backed]` |
| `font-family-mono` | `Consolas, "Courier New", monospace` | ADB 地址、日志、代码 `[Data-backed]` |

| Token | 值 | 用途 |
|-------|-----|------|
| `font-size-2xs` | `9px` | logo 副标题 |
| `font-size-xs` | `10px` | 状态标签、徽标 |
| `font-size-sm` | `11px` | 弱化信息、面板副标题 |
| `font-size-md` | `12.5px` | 次级文字、参数标签 |
| `font-size-lg` | `13.5px` | 导航项、任务名 |
| `font-size-xl` | `14px` | 面板标题、主要操作 |
| `font-size-2xl` | `16px` | logo 主标题 |
| `font-size-hero` | `26px` | KPI 数值 |
| `font-weight-regular` | `400` | 正文 |
| `font-weight-bold` | `700` | 标题、数值、主按钮 |
| `font-lineheight-tight` | `1.25` | 标题、KPI |
| `font-lineheight-normal` | `1.6` | 日志行、正文 |
| `font-tracking-wide` | `1px` | 面板标题 |
| `font-tracking-widest` | `2px` | KPI 标签、导航分组标签 |
| `font-tracking-logo` | `3px` | logo 主标题 |
| `font-tracking-label` | `4px` | logo 副标题 |

### 2.5 圆角与形制

方舟主题几乎不使用圆角——直角是默认，斜切与菱形是品牌形制 `[Data-backed]`：

| Token | 值 | 用途 |
|-------|-----|------|
| `radius-none` | `0` | 全站默认：面板、按钮、输入、卡片 |
| `radius-xs` | `2px` | 导航项 hover 背景（设计稿 `border-radius:2px`） |

| 形制 | 规格 | 用途 |
|------|------|------|
| 直角 | 所有面板/卡片/输入 `radius:0` | 基础形制 |
| 45° 斜切 | `clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px)` | Link Start 主按钮 |
| 菱形 | `transform: rotate(45deg)` 的方形 | logo 标记、面板标题角标、复选框、状态指示灯 |

### 2.6 阴影

设计稿为扁平金属面板，常规状态无投影，仅金色元素 hover 发光 `[Data-backed]`：

| Token | 值 | 用途 |
|-------|-----|------|
| `shadow-none` | `none` | 面板默认 |
| `shadow-glow-sm` | `0 0 16px rgba(216,177,106,.15)` | 主按钮 hover |
| `shadow-glow-lg` | `0 0 24px rgba(216,177,106,.15)` | 主按钮 hover（设计稿原值） |

### 2.7 动效

| Token | 值 | 用途 |
|-------|-----|------|
| `motion-duration-fast` | `150ms` | 列表项、复选框等微观反馈 |
| `motion-duration-normal` | `200ms` | 导航、面板边框、按钮状态过渡 |
| `motion-easing-standard` | `ease` | 统一缓动 |

动效原则：金属面板状态下过渡应克制（边框/背景色变化即可），不引入位移弹跳 `[Expert judgment]`。

### 2.8 z 层级

| Token | 值 | 用途 |
|-------|-----|------|
| `z-index-base` | `0` | 背景装饰层 |
| `z-index-content` | `1` | 侧栏、主区 |
| `z-index-sticky` | `100` | 吸顶、弹出层 |

### 2.9 Token 输出格式

**CSS 自定义属性**（供 Vue 组件直接引用）：

```css
:root {
  /* 视觉层 */
  --color-gold-400: #d8b16a;
  --color-gold-600: #a8853f;
  --color-bg-base: #1a1d22;
  --color-bg-deep: #14161b;
  --color-surface-700: #23272e;
  --color-surface-800: #1c2026;
  --color-border-default: #3a3f49;
  --color-border-strong: #4a5060;
  --color-text-primary: #e8e6df;
  --color-text-secondary: #9b9688;
  --color-text-tertiary: #6b6759;
  --color-success: #9fb56f;
  --color-warning: #c98f4e;
  --color-danger: #b05b53;

  /* 语义层 */
  --color-brand: var(--color-gold-400);
  --color-brand-strong: var(--color-gold-600);
  --color-bg-page: var(--color-bg-base);
  --color-bg-panel: var(--color-surface-700);
  --color-bg-subtle: var(--color-surface-800);

  /* 间距 */
  --spacing-md: 12px;
  --spacing-lg: 16px;
  --spacing-2xl: 24px;

  /* 字体 */
  --font-family-sans: "Microsoft YaHei", "PingFang SC", sans-serif;
  --font-family-serif: "Georgia", "STSong", serif;
  --font-family-mono: Consolas, "Courier New", monospace;
}
```

**TypeScript Token 对象**：

```typescript
export const tokens = {
  color: {
    gold: { 400: '#d8b16a', 600: '#a8853f' },
    bgBase: '#1a1d22',
    bgDeep: '#14161b',
    surface: { 700: '#23272e', 800: '#1c2026' },
    borderDefault: '#3a3f49',
    borderStrong: '#4a5060',
    textPrimary: '#e8e6df',
    textSecondary: '#9b9688',
    textTertiary: '#6b6759',
    success: '#9fb56f',
    warning: '#c98f4e',
    danger: '#b05b53',
  },
  spacing: { md: '12px', lg: '16px', '2xl': '24px' },
  fontFamily: {
    sans: '"Microsoft YaHei", "PingFang SC", sans-serif',
    serif: '"Georgia", "STSong", serif',
    mono: 'Consolas, "Courier New", monospace',
  },
} as const;
```

---

## 3. 组件规范（Component Library）

### 3.1 导航项 NavItem

**描述**：侧栏主导航项，激活时左侧金色斜切指示条 + 渐变背景。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `active` | `boolean` | `false` | 否 | 是否为当前页 |
| `label` | `string` | — | 是 | 导航文字 |
| `icon` | `string` | `''` | 否 | 图标字符 |
| `badge` | `string \| null` | `null` | 否 | 右上角徽标数字 |

#### States

| 状态 | 视觉描述 | 触发 |
|------|---------|------|
| 默认 | 次级文字色，透明背景 | 无交互 |
| Hover | 主文字色，`color-bg-hover` 背景 | 鼠标进入 |
| 激活 | 金色文字，`linear-gradient(90deg, color-bg-active, transparent)` 背景，左侧 3px 金色斜切条（`clip-path`） | 当前路由命中 |

#### 代码示例

```html
<div class="nav-item" :class="{ active }">
  <span class="nav-item__icon">{{ icon }}</span>
  <span class="nav-item__label">{{ label }}</span>
  <span v-if="badge" class="nav-item__badge">{{ badge }}</span>
</div>
```

```css
.nav-item {
  display: flex; align-items: center; gap: var(--spacing-md);
  padding: 11px var(--spacing-md); margin: 3px 0;
  border-radius: var(--radius-xs); color: var(--color-text-secondary);
  font-size: var(--font-size-lg); position: relative;
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.nav-item:hover { color: var(--color-text-primary); background: var(--color-bg-hover); }
.nav-item.active {
  color: var(--color-brand);
  background: linear-gradient(90deg, var(--color-bg-active), transparent);
}
.nav-item.active::before {
  content: ""; position: absolute; left: -14px; top: 0; bottom: 0; width: 3px;
  background: var(--color-brand);
  clip-path: polygon(0 0, 100% 15%, 100% 85%, 0 100%);
}
.nav-item__badge {
  margin-left: auto; font-size: var(--font-size-xs); color: var(--color-brand);
  border: 1px solid var(--color-brand-strong); padding: 1px 8px; letter-spacing: 1px;
}
```

#### Do / Don't

- Do 用斜切指示条表达「当前页」。
- Don't 让多个导航项同时处于激活态。
- Don't 在徽标上使用金色以外的强调色。

### 3.2 主行动按钮 LinkStart

**描述**：页面主操作按钮（开始任务队列），45° 斜切 + 金色描边 + 深色金属底。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `playing` | `boolean` | `false` | 否 | 运行中状态（切换为红色描边） |
| `label` | `string` | `'LINK START'` | 否 | 按钮文字 |

#### States

| 状态 | 视觉描述 | 触发 |
|------|---------|------|
| 默认 | 深色渐变底 `linear-gradient(180deg, #2a2f38, #1c2026)`，金色文字，金色描边，右下角 12px 斜切 | 无交互 |
| Hover | 底变亮 `#343a45 → #232830`，`shadow-glow-lg` | 鼠标进入 |
| 运行中 | 红色描边 + 红色文字 `#d48f87` | `playing = true` |

#### 代码示例

```css
.linkstart {
  display: flex; align-items: center; gap: 11px; padding: 13px 32px;
  background: linear-gradient(180deg, #2a2f38, #1c2026);
  color: var(--color-brand); font-size: var(--font-size-xl); font-weight: var(--font-weight-bold);
  letter-spacing: 3px; border: 1px solid var(--color-brand-strong); cursor: pointer;
  clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.linkstart:hover { box-shadow: var(--shadow-glow-lg); }
.linkstart.playing { border-color: var(--color-danger); color: #d48f87; }
```

#### Do / Don't

- Do 每屏仅保留一个 LinkStart 主按钮。
- Don't 在 LinkStart 上使用圆角或胶囊形。
- Don't 为次要操作复制此斜切形制（斜切 = 最高行动优先级）。

### 3.3 KPI 指标卡

**描述**：仪表盘顶部四格数据卡，右上角金色角标装饰，数值用衬线字体。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `label` | `string` | — | 是 | 指标名（大写+字距 2px） |
| `value` | `string` | — | 是 | 主数值 |
| `unit` | `string \| null` | `null` | 否 | 数值后缀小字 |
| `delta` | `string` | `''` | 否 | 底部趋势行 |
| `deltaTone` | `'up' \| 'down' \| 'flat'` | `'flat'` | 否 | 趋势颜色 |

#### States

| 状态 | 视觉描述 | 触发 |
|------|---------|------|
| 默认 | 面板背景 + 常规边框，右上角金色 12px 角标（2px 边框） | 无交互 |
| Hover | 边框过渡（设计稿保留 `transition: border-color`，可选加金色弱化） | 鼠标进入 |

#### 代码示例

```css
.kpi {
  background: var(--color-bg-panel); border: 1px solid var(--color-border-default);
  padding: var(--spacing-lg) 18px; position: relative;
}
.kpi::after {
  content: ""; position: absolute; top: -1px; right: -1px; width: 12px; height: 12px;
  border-top: 2px solid var(--color-brand-strong); border-right: 2px solid var(--color-brand-strong);
  opacity: .7;
}
.kpi__label { color: var(--color-text-tertiary); font-size: var(--font-size-sm); letter-spacing: var(--font-tracking-widest); }
.kpi__value { font-family: var(--font-family-serif); font-size: var(--font-size-hero); font-weight: var(--font-weight-bold); color: var(--color-text-primary); }
.kpi__value small { font-size: var(--font-size-md); color: var(--color-text-secondary); font-weight: normal; }
.kpi__delta { font-size: var(--font-size-sm); letter-spacing: .5px; }
```

#### Do / Don't

- Do 数值使用衬线字体，与界面形成对比。
- Don't 在 KPI 内放置多于 1 个金色元素（角标已占用金色语义）。
- Don't 让 KPI 超过 4 格一行（设计稿网格 `repeat(4, 1fr)`）。

### 3.4 状态标签 StatusChip

**描述**：顶部栏引擎/设备/任务状态，菱形指示灯 + 描边文字。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `tone` | `'on' \| 'off' \| 'idle' \| 'run' \| 'wait'` | `'idle'` | 否 | 状态色调 |
| `label` | `string` | — | 是 | 状态文字 |

#### 色调映射

| tone | 指示灯 | 边框 | 文字 |
|------|--------|------|------|
| `on` | `color-success`（+40% 透明填充） | `color-success` | 次级文字色 |
| `off` | `color-danger` | `color-danger` | 次级文字色 |
| `idle` | `color-text-tertiary` | `color-text-tertiary` | 次级文字色 |

#### 代码示例

```css
.chip { font-size: var(--font-size-sm); color: var(--color-text-secondary); border: 1px solid var(--color-border-default); padding: 5px 13px; display: flex; align-items: center; gap: 7px; letter-spacing: .5px; }
.chip__diamond { width: 8px; height: 8px; border: 1px solid currentColor; transform: rotate(45deg); }
```

### 3.5 面板 Panel

**描述**：内容容器，直角 + 常规边框；标题行带 14px 菱形角标。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `title` | `string` | — | 是 | 面板标题 |
| `subtitle` | `string \| null` | `null` | 否 | 右上角说明文字 |

#### 结构

```
┌──────────────────────────────────┐
│ ◆ 标题                   说明  │  ← 菱形角标 + 标题 + 右对齐说明
├──────────────────────────────────┤
│ 内容区                           │
└──────────────────────────────────┘
```

#### 代码示例

```css
.panel { background: var(--color-bg-panel); border: 1px solid var(--color-border-default); position: relative; }
.panel__header { display: flex; align-items: center; gap: var(--spacing-md); padding: 14px 18px; border-bottom: 1px solid var(--color-border-default); }
.panel__diamond { width: 14px; height: 14px; border: 1px solid var(--color-brand); transform: rotate(45deg); flex-shrink: 0; }
.panel__title { font-size: var(--font-size-xl); font-weight: var(--font-weight-bold); letter-spacing: 1px; }
.panel__subtitle { margin-left: auto; font-size: var(--font-size-sm); color: var(--color-text-tertiary); letter-spacing: .5px; }
```

#### Do / Don't

- Do 用菱形角标标记「任务编排」「作战记录」这类功能性面板。
- Don't 在普通容器上也加菱形角标（角标仅面板标题行使用）。

### 3.6 任务项 TaskItem

**描述**：任务队列中的一行，菱形复选框 + 任务名 + 状态标签。

#### Props

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `checked` | `boolean` | `false` | 否 | 是否勾选启用 |
| `selected` | `boolean` | `false` | 否 | 是否选中（右侧显示参数面板） |
| `name` | `string` | — | 是 | 任务名 |
| `status` | `'idle' \| 'run' \| 'ok' \| 'wait'` | `'idle'` | 否 | 执行状态 |

#### 状态映射

| 状态 | 边框 | 文字 |
|------|------|------|
| `idle` | `color-border-default` | `color-text-tertiary` |
| `run` | `color-gold-600`（+10% 背景） | `color-brand` |
| `ok` | `color-success` | `color-success` |
| `wait` | `color-warning` | `color-warning` |

#### 代码示例

```css
.task { display: flex; align-items: center; gap: var(--spacing-md); padding: 10px 14px; cursor: pointer; border-left: 2px solid transparent; transition: background var(--motion-duration-fast) ease; }
.task:hover { background: var(--color-bg-hover); }
.task.selected { border-left-color: var(--color-brand); background: var(--color-bg-active); }
.task__check { width: 15px; height: 15px; border: 1px solid var(--color-border-strong); transform: rotate(45deg); display: flex; align-items: center; justify-content: center; }
.task__check.checked { background: var(--color-brand); border-color: var(--color-brand); }
.task__check.checked::before { content: "✓"; transform: rotate(-45deg); font-size: 10px; color: var(--color-text-inverse); font-weight: bold; }
```

#### Do / Don't

- Do 选中态同时用「左侧金色竖条 + 金色背景」双重表达。
- Don't 让状态标签使用圆角胶囊（保持直角 `radius:0`）。
- Don't 勾选态与选中态混为一谈——勾选 = 是否执行，选中 = 是否查看参数。

### 3.7 表单控件

#### 开关 Switch

| Prop | 类型 | 默认 | 必填 | 描述 |
|------|------|------|------|------|
| `modelValue` | `boolean` | `false` | 否 | 开关状态 |

```css
.switch { width: 38px; height: 18px; border: 1px solid var(--color-border-strong); position: relative; cursor: pointer; clip-path: polygon(6px 0, 100% 0, 100% calc(100% - 6px), calc(100% - 6px) 100%, 0 100%, 0 6px); }
.switch.on { background: rgba(216,177,106,.25); border-color: var(--color-brand-strong); }
.switch__thumb { position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; background: var(--color-border-strong); transition: left var(--motion-duration-fast) ease; }
.switch.on .switch__thumb { left: 22px; background: var(--color-brand); }
```

> 开关沿用品牌形制——直角斜切，不用圆角胶囊 `[Data-backed]`。

#### 下拉选择 Select

```css
select {
  background: var(--color-bg-subtle); color: var(--color-text-primary);
  border: 1px solid var(--color-border-default); padding: 6px 11px;
  font-size: var(--font-size-md); outline: none;
}
select:focus { border-color: var(--color-brand); }
```

#### 数字输入 NumberInput

```css
input[type="number"], .num {
  background: var(--color-bg-subtle); border: 1px solid var(--color-border-default);
  color: var(--color-text-primary); width: 60px; padding: 6px 11px;
  font-size: var(--font-size-md); text-align: right; outline: none;
  font-family: var(--font-family-mono);
}
input[type="number"]:focus, .num:focus { border-color: var(--color-brand); }
```

> 数字输入使用等宽字体，保证数字对齐 `[Data-backed]`。

#### 时间选择 TimeSelect

**描述**：定时触发时间（HH:MM）。触发框同普通下拉（斜切直角 + ▼ 旋转）；面板为**时 00-23 / 分 00-59 双列滚动**，选中项金色高亮，时+分都选中即组合并收起。替代原生 `input[type="time"]`（浏览器控件与方舟主题不搭）。组件 `TimeSelect.vue`，v-model 为 `"HH:MM"`（与 `schedule_jobs.time`、主题自动切换时间同格式）。画廊示例见 `07-component-gallery.html` §下拉选择。

| 状态 | 视觉 |
|------|------|
| 默认 | `bg-subtle` 底 + `border-default` 边框 + 等宽 `HH:MM` |
| 聚焦 / 展开 | `border-brand-strong` + `shadow-glow-sm`，▼ 旋转 180° |
| 面板 | `bg-panel` 底 + `border-strong` 边框，双列各 `max-height:208px` 滚动 |
| 选中 | 金色高亮 + 菱形 ✓（同普通下拉 sel） |
| 占位 | `color-text-tertiary`（如「选择时间」） |
| 禁用 | 整体 0.45 透明度，不可交互 |

**交互**：点击触发框展开；Esc / 外部点击收起；时、分列各选中一次后自动收起并写回。键盘：Tab 聚焦、Enter/Space 展开收起。

### 3.8 日志流 LogStream

**描述**：实时任务日志，等宽字体，时间戳 + 级别 + 内容。

| 级别 | 颜色 |
|------|------|
| INFO | `color-brand` |
| OK | `color-success` |
| WARN | `color-warning` |
| ERROR | `color-danger` |
| 内容正文 | `color-text-secondary` |

```css
.log { font-family: var(--font-family-mono); font-size: var(--font-size-md); padding: var(--spacing-md) 18px; background: var(--color-bg-subtle); line-height: 1.6; overflow-y: auto; }
.log__line { display: flex; gap: 10px; padding: 4px 0; }
.log__time { color: var(--color-text-tertiary); flex-shrink: 0; }
```

---

## 4. 图标与装饰图形

### 4.1 图标原则

- 全部使用**线性（描边）图标**，`1px` 描边，继承 `currentColor`，不内置颜色 `[Expert judgment]`。
- 激活/选中态可切换为金色填充。
- 图标字符（emoji/几何符号）仅在设计稿阶段使用，正式实现替换为同一风格的 SVG 集。

### 4.2 品牌几何元素

| 元素 | 规格 | 用途 |
|------|------|------|
| 菱形 | 方形 `rotate(45deg)` | logo 标记（双层菱形）、面板标题角标、复选框、状态指示灯 |
| 斜切条 | 3px 宽，`clip-path: polygon(0 0, 100% 15%, 100% 85%, 0 100%)` | 导航激活指示 |
| 背景斜切光带 | 115° 方向两条极淡金线（透明 62%/82% 处） | 页面背景装饰（`color-gold-400` 3~4% 透明度） |
| 角标 | 12px，2px 边框金色 | KPI 卡右上角 |

---

## 5. 模板页面

### 5.1 总览仪表盘（Dashboard）

```
┌────┬──────────────────────────────────────────────────┐
│    │  作战总览 / 罗德岛指挥室      [◆引擎][◆设备][◆待命] │
│    ├──────────────────────────────────────────────────┤
│ 侧 │  ┌KPI┐ ┌KPI┐ ┌KPI┐ ┌KPI┐                       │
│ 栏 │  └───┘ └───┘ └───┘ └───┘                       │
│    │  ┌────────────────────┬─────────────────────┐   │
│    │  │ ◆ 作战部署         │ ◆ 作战记录          │   │
│    │  │ 任务列表 + 参数面板 │ 实时日志流          │   │
│    │  └────────────────────┴─────────────────────┘   │
│    ├──────────────────────────────────────────────────┤
│    │  ▶ LINK START      执行队列 · 刷理智 2/3 ...    │
└────┴──────────────────────────────────────────────────┘
```

| 区域 | 组件 | 关键 Token |
|------|------|-----------|
| 侧栏 | Logo + NavItem + 设备卡 | `color-bg-subtle`、`font-tracking-logo` |
| 顶部栏 | 面包屑 + StatusChip ×3 | `color-border-default` |
| KPI 区 | Kpi ×4 | `font-family-serif` 数值、金色角标 |
| 左面板 | Panel + TaskItem + 表单 | `color-bg-active`、菱形复选框 |
| 右面板 | Panel + LogStream | `color-bg-subtle` |
| 底部 | LinkStart + 提示 | 45° 斜切、`shadow-glow-lg` |

| 断点 | 行为 |
|------|------|
| ≥1080px | 双栏并排，KPI 4 列 |
| <1080px | 双栏变单栏，KPI 2 列 `[Data-backed]` |

### 5.2 状态变体

| 状态 | 表现 |
|------|------|
| 加载中 | 面板骨架以 `color-bg-hover` 底色 + 淡入动画呈现 `[Expert judgment]` |
| 无设备 | 设备卡显示离线菱形指示灯（`color-danger`）+ 引导连接按钮 |
| 运行中 | LinkStart 切换红色描边；日志流持续追加；运行任务状态标签金色 |
| 空任务 | 任务面板展示「暂无部署任务，点击添加」占位（次级文字色）`[Expert judgment]` |

---

## 6. 无障碍（Accessibility）

| 项目 | 要求 |
|------|------|
| 正文对比度 | 主文字 `#e8e6df` 对背景 `#1a1d22` 对比度约 13:1，满足 WCAG AA `[Research-backed]` |
| 次级文字 | `#9b9688` 对 `#23272e` 对比度约 5.4:1，满足 AA 正文要求 `[Research-backed]` |
| 金色文字 | `#d8b16a` 对 `#1c2026` 约 7:1，满足 AA（含大字号 AAA）`[Research-backed]` |
| 聚焦指示 | 交互元素聚焦时边框切换 `color-border-focus`（金色），不依赖颜色外的唯一提示时补充 `outline: 1px solid` `[Expert judgment]` |
| 键盘可达 | 所有交互组件可 Tab 到达、Enter/Space 触发；复选框、开关、下拉需原生语义或 `role`/`aria-checked` |
| 状态传达 | 状态标签（在线/运行/等待）需配文字，不单靠颜色区分 `[Expert judgment]` |

---

## 7. 证据标注索引

| 标注 | 含义 | 本规范中应用位置 |
|------|------|-----------------|
| `[Data-backed]` | 直接取自设计稿 `03-arknights.html` | 全部色值、间距归纳、字体族、形制、断点 |
| `[Research-backed]` | 引用成熟标准 | WCAG 2.1 AA 对比度要求 |
| `[Expert judgment]` | 设计惯例推断 | 间距基数、徽标样式、空态/加载态、图标线性风格 |

> 未经设计稿或标准支撑的取值一律标注 `[Expert judgment]`，评审时可据此复核或修改。
