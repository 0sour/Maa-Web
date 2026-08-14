/**
 * 界面主题应用 —— 深色 / 浅色 / 自动（自动 = 按当地日出日落 或 手动设定切换时间）。
 * 自动模式下每分钟重算一次当前应显示的主题；切回固定主题时清理定时器。
 * 主题持久化在设置页（ui 组），本模块只负责计算 + 应用到 html[data-theme]。
 */

export interface UiThemeSettings {
  theme?: unknown
  auto_theme_mode?: unknown
  auto_theme_lat?: unknown
  auto_theme_lon?: unknown
  auto_theme_light_start?: unknown
  auto_theme_dark_start?: unknown
}

let timer: number | null = null

function setTheme(theme: 'dark' | 'light') {
  document.documentElement.dataset.theme = theme
}

export interface SunTimes {
  sunrise: Date
  sunset: Date
  /** 极昼（全天白天）/ 极夜（全天黑夜）；null = 正常日出日落 */
  polar: 'day' | 'night' | null
}

/** 简化日出日落计算（NOAA 近似，精度约 ±2 分钟；返回本地时区 Date） */
export function sunTimes(date: Date, lat: number, lon: number): SunTimes {
  const rad = Math.PI / 180
  const jd = date.getTime() / 86400000 + 2440587.5
  const jstar = jd - 2451545.0 + 0.0008 - lon / 360
  const M = (357.5291 + 0.98560028 * jstar) % 360
  const C = 1.9148 * Math.sin(M * rad) + 0.02 * Math.sin(2 * M * rad) + 0.0003 * Math.sin(3 * M * rad)
  const lambda = (M + C + 180 + 102.9372) % 360
  const jtransit = 2451545.0 + jstar + 0.0053 * Math.sin(M * rad) - 0.0069 * Math.sin(2 * lambda * rad)
  const decl = Math.asin(Math.sin(lambda * rad) * Math.sin(23.4397 * rad)) / rad
  const h =
    (Math.sin(-0.833 * rad) - Math.sin(lat * rad) * Math.sin(decl * rad)) /
    (Math.cos(lat * rad) * Math.cos(decl * rad))
  if (h > 1) return { sunrise: date, sunset: date, polar: 'night' } // 极夜：全天无日出
  if (h < -1) return { sunrise: date, sunset: date, polar: 'day' } // 极昼：全天不日落
  const H = Math.acos(h) / rad
  const at = (j: number) => new Date((j - 2440587.5) * 86400000)
  return { sunrise: at(jtransit - H / 360), sunset: at(jtransit + H / 360), polar: null }
}

function toMin(s: unknown, fallback: number): number {
  const m = /^(\d{1,2}):(\d{2})$/.exec(String(s ?? ''))
  if (!m) return fallback
  return Number(m[1]) * 60 + Number(m[2])
}

/** 当前应显示的主题：自动模式 → 白天浅色 / 夜晚深色 */
export function effectiveTheme(ui: UiThemeSettings): 'dark' | 'light' {
  if (ui.theme !== 'auto') return ui.theme === 'light' ? 'light' : 'dark'
  const now = new Date()
  if (ui.auto_theme_mode === 'sun') {
    const lat = Number(ui.auto_theme_lat)
    const lon = Number(ui.auto_theme_lon)
    if (Number.isFinite(lat) && Number.isFinite(lon) && Math.abs(lat) <= 90 && Math.abs(lon) <= 180) {
      const { sunrise, sunset, polar } = sunTimes(now, lat, lon)
      if (polar === 'day') return 'light'
      if (polar === 'night') return 'dark'
      return now >= sunrise && now < sunset ? 'light' : 'dark'
    }
  }
  // 手动设定切换时间（或「日出日落」缺位置时回退）：浅色区间 [浅色开始, 深色开始)，支持跨午夜
  const lightStart = toMin(ui.auto_theme_light_start, 6 * 60)
  const darkStart = toMin(ui.auto_theme_dark_start, 18 * 60)
  const hm = now.getHours() * 60 + now.getMinutes()
  if (lightStart <= darkStart) return hm >= lightStart && hm < darkStart ? 'light' : 'dark'
  return hm >= lightStart || hm < darkStart ? 'light' : 'dark'
}

/** 应用主题（自动模式下挂每分钟重算定时器；固定主题只应用一次） */
export function applyUiTheme(ui: UiThemeSettings): void {
  if (timer !== null) {
    window.clearInterval(timer)
    timer = null
  }
  setTheme(effectiveTheme(ui))
  if (ui.theme === 'auto') {
    timer = window.setInterval(() => setTheme(effectiveTheme(ui)), 60_000)
  }
}
