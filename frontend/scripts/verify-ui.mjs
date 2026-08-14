// Maa-Web · L3 浏览器回归脚本（docs/testing.md 第 3 层）
// 用法：npm run verify   （需后端 http://127.0.0.1:8000 与前端 dev server 均在运行）
// 职责：无头浏览器逐页检查渲染 + 控制台无错 + 关键交互冒烟。
// 退出码：0=通过；1=失败（输出原因）。

import { chromium } from 'playwright'

const BASE = process.env.VERIFY_BASE ?? 'http://localhost:5173'
const SHOTS = process.env.VERIFY_SHOTS ?? 'D:/Maa-Web/captures'
const ok = (msg) => console.log(`  ✔ ${msg}`)
const fail = (msg) => { console.error(`  ✘ ${msg}`); process.exitCode = 1 }

const results = { passed: 0, failed: 0 }
function check(cond, msg) { cond ? (results.passed++, ok(msg)) : (results.failed++, fail(msg)) }

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

// ── 控制台错误收集 ─────────────────────────
// 已知设计内噪声（不算失败）：
//   · /healthz/* 返回 503 —— 无 MaaFw 时后端降级态，前端 validateStatus 已按设计处理。
const consoleErrors = []
const badResponses = []
page.on('console', (m) => {
  // 503 资源加载日志由 /healthz/* 降级探针产生（response 监听器已独立校验无其他 ≥500）。
  if (m.type() === 'error' && !/503 \(Service Unavailable\)/.test(m.text())) consoleErrors.push(m.text())
})
page.on('pageerror', (e) => consoleErrors.push(`pageerror: ${e.message}`))
page.on('response', (r) => {
  if (r.status() >= 500 && !r.url().includes('/healthz/')) badResponses.push(`${r.status()} ${r.url()}`)
})

try {
  // ── 1. 作战总览 ─────────────────────────
  console.log('[1/5] 作战总览 /')
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle' })
  // 作战总览/任务编排有本地即时保存，回归前清空以保证队列从空态开始
  await page.evaluate(() => localStorage.clear())
  await page.waitForSelector('.linkstart', { timeout: 8000 })
  check((await page.textContent('title'))?.includes('作战总览') ?? false, '页面标题正确')
  check((await page.locator('.kpi').count()) === 4, 'KPI 指标卡 ×4')
  check(await page.isVisible('.linkstart'), 'LINK START 底栏可见')
  check(await page.isVisible('.log'), '作战记录日志面板可见')
  check(await page.isVisible('.target-row'), '目标设备选择行可见')
  check(await page.isVisible('.res-row'), '识别资源包状态条可见（S-07 主动更新）')

  // 编排一个「刷理智」任务 → 真实参数面板（D-03）出现
  await page.getByRole('button', { name: /添加任务/ }).click()
  await page.getByRole('button', { name: /刷理智/ }).click()
  check(await page.isVisible('.params'), '刷理智参数面板可见（关卡/理智药/源石/次数/倍率）')
  const paramLabels = await page.locator('.f-row .f-label').allTextContents()
  check(
    ['目标关卡', '理智药', '源石', '战斗次数', '代理倍率'].every((l) => paramLabels.some((x) => x.includes(l))),
    '参数面板字段齐备（目标关卡/理智药/源石/次数/倍率）',
  )
  // 数字字段渲染为数字微调（▲▼ 步进按钮），与组件示例一致（NumericUpDown）
  const nfCount = await page.locator('.nf').count()
  const nfBtnCount = await page.locator('.nf-btn').count()
  check(nfCount >= 4 && nfBtnCount >= 8, `数字微调控件渲染（.nf=${nfCount}, ▲▼按钮=${nfBtnCount}）`)
  // 任务项支持勾选/排序/移除交互
  check(await page.locator('.task .chk').count() >= 1, '任务队列项已渲染（菱形勾选）')
  await page.locator('.task').first().hover()
  await page.locator('.task .del').first().click()
  await page.waitForFunction(() => document.querySelectorAll('.task').length === 0, undefined, { timeout: 5000 })
  check(true, '任务移除交互正常')

  // ── 2. 设备管理 ─────────────────────────
  console.log('[2/5] 设备管理 /devices')
  await page.goto(`${BASE}/devices`, { waitUntil: 'networkidle' })
  await page.waitForSelector('.dv-top, .dv-empty', { timeout: 8000 })

  const hasCards = await page.locator('.dev').count()
  const hasEmpty = await page.isVisible('.dv-empty')
  check(hasCards > 0 || hasEmpty, `设备列表渲染（卡片=${hasCards}, 空态=${hasEmpty}）`)

  // 打开「添加设备」Modal
  await page.getByRole('button', { name: /添加设备/ }).first().click()
  await page.waitForSelector('.modal', { timeout: 5000 })
  check(await page.isVisible('.modal'), '添加设备 Modal 打开')
  check(await page.locator('.modal input').count() >= 3, '表单字段齐备（名称/ADB/端口…）')

  // 填写并提交
  const t = `verify-${Date.now()}`
  await page.locator('.f-row input[type=text]').nth(0).fill(t)
  await page.locator('.f-row input[type=text]').nth(1).fill('127.0.0.1')
  await page.getByRole('button', { name: '保存' }).click()
  await page.waitForSelector('.modal', { state: 'detached', timeout: 5000 })
  await page.waitForSelector(`text="${t}"`, { timeout: 8000 })
  check(true, `新增设备「${t}」出现在列表`)

  // 连接：真实引擎下两种合法终态
  //   · adb 可用且连接成功 → status=online（出现「断开」按钮）
  //   · adb 缺失 / 连接失败 → status=error（卡片展示 last_error 原因）
  const card = page.locator('.dev', { hasText: t })
  await card.getByRole('button', { name: '连接' }).click()
  await page.waitForFunction(
    (name) => {
      const node = [...document.querySelectorAll('.dev')].find((el) => el.textContent.includes(name))
      return !!node && !!node.querySelector('.s-online, .s-error')
    },
    t,
    { timeout: 8000 },
  )
  const wentOnline = (await card.locator('.s-online').count()) > 0
  const wentError = (await card.locator('.s-error').count()) > 0
  check(wentOnline || wentError, `连接后到达终态（在线=${wentOnline}, 异常=${wentError}）`)
  if (wentOnline) {
    check(await card.getByRole('button', { name: '断开' }).isVisible(), '在线态出现「断开」按钮')
  } else {
    const errText = await card.locator('.dev-err').textContent()
    check(!!errText && errText.length > 0, `异常态卡片展示连接原因（${errText?.trim()}）`)
  }

  // 环境检测面板
  await page.getByRole('button', { name: /检测设备/ }).first().click()
  await page.waitForSelector('.detect', { timeout: 8000 })
  check(await page.isVisible('.detect'), '检测面板出现（环境芯片 + 扫描结果）')
  const envChips = await page.locator('.env-chip').count()
  check(envChips === 2, `环境芯片 ×2（ADB/MAA，实际=${envChips}）`)

  // 编辑弹窗
  await card.getByRole('button', { name: '编辑' }).click()
  await page.waitForSelector('.modal', { timeout: 5000 })
  check((await page.locator('.modal input[type=text]').first().inputValue()) === t, '编辑 Modal 回填正确')
  await page.getByRole('button', { name: '取消' }).click()

  // 删除（两步确认）
  await card.getByRole('button', { name: '删除' }).click()
  await card.getByRole('button', { name: '确认删除?' }).click()
  await page.waitForSelector(`text="${t}"`, { state: 'detached', timeout: 8000 })
  check(true, `删除设备「${t}」成功`)

  // ── 3. 任务编排页 + 其余占位页可渲染 ─────────────────
  console.log('[3/5] 任务编排 /tasks + 占位页')
  await page.goto(`${BASE}/tasks`, { waitUntil: 'networkidle' })
  check(await page.isVisible('.scheme-bar'), '任务编排页 方案栏可见')
  check(await page.isVisible('.panel-col .panel'), '任务编排页 任务队列面板可见')
  check(await page.isVisible('.linkstart'), '任务编排页 LINK START 可见')
  for (const path of ['/toolbox', '/logs', '/settings', '/notifications']) {
    await page.goto(`${BASE}${path}`, { waitUntil: 'networkidle' })
    check(await page.isVisible('.ph'), `占位页 ${path} 渲染`)
  }

  // ── 4. 控制台错误检查 ────────────────────
  console.log('[4/5] 控制台错误')
  check(consoleErrors.length === 0, `无 JS 错误（捕获 ${consoleErrors.length} 条）`)
  if (consoleErrors.length) consoleErrors.forEach((e) => console.error(`      ↳ ${e}`))
  check(badResponses.length === 0, `无异常 HTTP 响应 ≥500（捕获 ${badResponses.length} 条，healthz 除外）`)
  if (badResponses.length) badResponses.forEach((e) => console.error(`      ↳ ${e}`))
} catch (e) {
  fail(`脚本异常: ${e?.message ?? e}`)
  try { await page.screenshot({ path: `${SHOTS}/verify-failure.png`, fullPage: true }) } catch { /* ignore */ }
} finally {
  await browser.close()
}

console.log(`\n结果: ${results.passed} 通过, ${results.failed} 失败`)
process.exit(results.failed > 0 ? 1 : 0)
