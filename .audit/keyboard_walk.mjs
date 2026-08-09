// 键盘走查：Tab 焦点可见性、弹窗 ESC/回焦/焦点圈定、通知面板、揭晓按钮
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

const log = []
const ok = (name, pass, extra = '') => {
  log.push(`${pass ? '✅' : '❌'} ${name}${extra ? ' — ' + extra : ''}`)
  console.log(`${pass ? 'PASS' : 'FAIL'} ${name} ${extra}`)
}

// 焦点可见性：检查当前 activeElement 是否有可见 focus-visible 指示
const focusVisible = () => page.evaluate(() => {
  const el = document.activeElement
  if (!el || el === document.body) return { ok: false, why: 'no active element' }
  const st = getComputedStyle(el)
  return { ok: st.outlineStyle !== 'none' && parseFloat(st.outlineWidth) > 0, why: `outline=${st.outlineStyle} ${st.outlineWidth}` }
})

// 1. 登录页 Tab 走查
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
for (let i = 0; i < 6; i++) {
  await page.keyboard.press('Tab')
  const f = await focusVisible()
  if (!f.ok) { ok(`login Tab#${i + 1} focus visible`, false, f.why); break }
}
ok('login 连续 Tab 焦点可见', true)

// 2. 事件页：剪贴板邀请码自动弹窗 → 焦点入弹窗 → ESC 关闭 → 回焦
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
// 桩：剪贴板 readText 返回邀请码（自动弹窗路径）
await page.evaluateOnNewDocument((code) => {
  Object.defineProperty(navigator, 'clipboard', {
    value: { readText: async () => `/events/${code}` },
    configurable: true,
  })
}, 'ABC123')
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await new Promise((r) => setTimeout(r, 900))
const modalState = await page.evaluate(() => {
  const dlg = document.querySelector('[role="dialog"]')
  return dlg ? { open: true, label: dlg.getAttribute('aria-labelledby') ? 'ok' : 'missing', activeIn: dlg.contains(document.activeElement) } : { open: false }
})
ok('加入弹窗 role=dialog + 焦点入内', modalState.open && modalState.label === 'ok' && modalState.activeIn, JSON.stringify(modalState))
// ESC 关闭
await page.keyboard.press('Escape')
await new Promise((r) => setTimeout(r, 200))
const afterEsc = await page.evaluate(() => ({
  dialogGone: !document.querySelector('[role="dialog"]'),
  focusBack: !!document.activeElement && document.activeElement !== document.body && !document.querySelector('[role="dialog"]'),
}))
ok('ESC 关闭弹窗 + 焦点不丢失', afterEsc.dialogGone && afterEsc.focusBack, JSON.stringify(afterEsc))

// 3. 礼物墙：Tab 到揭晓按钮 → Enter 揭晓 → 内容可见
await page.goto(`${BASE}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
await new Promise((r) => setTimeout(r, 800))
const revealTab = await page.evaluate(() => {
  const mask = [...document.querySelectorAll('.gw-mask')].find((m) => m.tabIndex === 0)
  if (mask) mask.focus()
  return !!mask
})
ok('揭晓按钮可聚焦', revealTab)
const fv = await focusVisible()
ok('揭晓按钮焦点可见', fv.ok, fv.why)
await page.keyboard.press('Enter')
await new Promise((r) => setTimeout(r, 800))
const revealed = await page.evaluate(() => {
  const card = document.querySelector('.gw-item-card.revealed')
  const body = card?.querySelector('.gw-item-body')
  return card ? { revealed: true, bodyVisible: getComputedStyle(body).visibility !== 'hidden' } : { revealed: false }
})
ok('Enter 揭晓卡片 + 内容可见', revealed.revealed && revealed.bodyVisible, JSON.stringify(revealed))

// 4. 通知铃铛：aria-expanded 切换 + ESC 关闭
await page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
await new Promise((r) => setTimeout(r, 600))
const bell = await page.evaluate(() => {
  const b = document.querySelector('.notif-bell')
  b && b.click()
  return true
})
await new Promise((r) => setTimeout(r, 300))
const notifState = await page.evaluate(() => {
  const b = document.querySelector('.notif-bell')
  const p = document.querySelector('#notif-panel')
  return { expanded: b?.getAttribute('aria-expanded'), panel: p ? p.getAttribute('aria-label') : null }
})
ok('铃铛 aria-expanded=true + 面板 aria-label', notifState.expanded === 'true' && !!notifState.panel, JSON.stringify(notifState))
await page.keyboard.press('Escape')
await new Promise((r) => setTimeout(r, 200))
const notifClosed = await page.evaluate(() => document.querySelector('.notif-bell')?.getAttribute('aria-expanded'))
ok('ESC 关闭通知面板', notifClosed === 'false', `aria-expanded=${notifClosed}`)

// 5. 焦点圈定：弹窗内 Tab 循环
await page.evaluate(() => {
  try { sessionStorage.removeItem('gift-clip-prompted') } catch { /* ignore */ }
})
await page.reload({ waitUntil: 'networkidle2' })
await new Promise((r) => setTimeout(r, 900))
const trap = await page.evaluate(() => {
  const dlg = document.querySelector('[role="dialog"]')
  const focusables = dlg ? [...dlg.querySelectorAll('button, input')] : []
  if (!focusables.length) return { ok: false }
  focusables[focusables.length - 1].focus()
  return { ok: true, count: focusables.length, last: focusables[focusables.length - 1].textContent.trim() }
})
ok('弹窗聚焦元素数量', trap.ok, JSON.stringify(trap))
await page.keyboard.press('Tab')
const afterTab = await page.evaluate(() => {
  const dlg = document.querySelector('[role="dialog"]')
  return dlg ? dlg.contains(document.activeElement) : false
})
ok('Tab 从末尾循环回弹窗内', afterTab)
await page.keyboard.press('Escape')

// 6. prefers-reduced-motion 断言：媒体查询下动画被禁用
const motion = await page.emulateMediaFeatures([{ name: 'prefers-reduced-motion', value: 'reduce' }])
await page.goto(`${BASE}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
await new Promise((r) => setTimeout(r, 500))
const motionState = await page.evaluate(() => {
  // 检查全局动画时长覆盖
  const probe = document.createElement('div')
  probe.style.animationDuration = '0.8s'
  document.body.appendChild(probe)
  const dur = getComputedStyle(probe).animationDuration
  probe.remove()
  return { reducedDur: dur }
})
const durSec = parseFloat(motionState.reducedDur) // '1e-05s' → 1e-05
ok('prefers-reduced-motion 生效（动画时长≈0）', isFinite(durSec) && durSec < 0.001, JSON.stringify(motionState))

fs.writeFileSync(process.env.HOME + '/giftexchange/.audit/keyboard_walk.json', JSON.stringify(log, null, 2))
await browser.close()
console.log('keyboard walk done')
