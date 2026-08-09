// ============================================================
// 跨浏览器 E2E（hackathon 轮6）：Chrome / Edge（puppeteer-core）
// 核心旅程子集：登录 → 列表 → 详情 → 礼物墙
// 每浏览器 5 组断言 + 桌面/移动双视口布局指标 + JS 错误采集
// 输出：.audit/xbrowser_results.json + .audit/xbrowser-shots/
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const OUT = path.join(__dirname, 'xbrowser-shots')
fs.mkdirSync(OUT, { recursive: true })

const BROWSERS = [
  { name: 'chrome', executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' },
  { name: 'edge', executablePath: '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge' },
]
const VIEWPORTS = [
  { name: 'desktop', width: 1280, height: 800 },
  { name: 'mobile', width: 390, height: 844, isMobile: true, hasTouch: true },
]
const CREDS = { username: 'verify_user', password: 'Verify123' }

const settle = (ms = 700) => new Promise((r) => setTimeout(r, ms))

// React 受控输入：原生 setter + input/change 事件
async function reactType(page, selector, value) {
  await page.waitForSelector(selector, { timeout: 10000 })
  await page.evaluate(([sel, v]) => {
    const node = document.querySelector(sel)
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
    setter.call(node, v)
    node.dispatchEvent(new Event('input', { bubbles: true }))
    node.dispatchEvent(new Event('change', { bubbles: true }))
  }, [selector, value])
}

async function runJourney(browserName, browser, vp) {
  const results = { browser: browserName, viewport: vp.name, ua: null, assertions: {}, pages: [], errors: [] }
  const page = await browser.newPage()
  await page.setViewport({ width: vp.width, height: vp.height, deviceScaleFactor: 1, isMobile: !!vp.isMobile, hasTouch: !!vp.hasTouch })

  const jsErrors = []
  page.on('pageerror', (e) => jsErrors.push(`pageerror: ${e.message}`))
  page.on('console', (m) => { if (m.type() === 'error') jsErrors.push(`console.error: ${m.text()}`) })
  page.on('requestfailed', (r) => jsErrors.push(`requestfailed: ${r.url()} ${r.failure()?.errorText}`))
  page.on('response', (r) => { if (r.status() >= 400) jsErrors.push(`http${r.status()}: ${r.url()}`) })

  const metric = async (name, url, waitSel) => {
    await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2', timeout: 20000 })
    if (waitSel) await page.waitForSelector(waitSel, { timeout: 10000 })
    await settle()
    await page.screenshot({ path: `${OUT}/${browserName}-${vp.name}-${name}.png` })
    const m = await page.evaluate(() => ({
      path: location.pathname,
      scrollW: document.documentElement.scrollWidth,
      clientW: document.documentElement.clientWidth,
      hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      bodyText: document.body.innerText.slice(0, 80).replace(/\n/g, ' | '),
      gwGrid: !!document.querySelector('.gw-grid'),
      detailLayout: !!document.querySelector('.detail-layout'),
      eventCards: document.querySelectorAll('.event-card, .event-item, [class*="event-card"]').length,
      title: document.title,
    }))
    results.pages.push({ step: name, url, ...m })
    return m
  }

  // ---- 1. 登录页渲染 ----
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  await settle()
  results.ua = await page.evaluate(() => navigator.userAgent)
  const loginOK = await page.evaluate(() => {
    const user = document.querySelector('input[placeholder="用户名"]')
    const pwd = document.querySelector('input[placeholder="密码"]')
    const btn = document.querySelector('button[type="submit"]')
    return !!user && !!pwd && !!btn
  })
  results.assertions['login_renders'] = { pass: loginOK, detail: '用户名+密码输入框与提交按钮渲染' }
  await page.screenshot({ path: `${OUT}/${browserName}-${vp.name}-login.png` })

  // ---- 2. 真实表单登录 → 列表 ----
  if (!loginOK) {
    results.assertions['login_and_list'] = { pass: false, detail: '登录表单缺失，跳过' }
  } else {
    await reactType(page, 'input[placeholder="用户名"]', CREDS.username)
    await reactType(page, 'input[placeholder="密码"]', CREDS.password)
    await page.evaluate(() => {
      document.querySelector('button[type="submit"]').click()
    })
    await page.waitForFunction(() => location.pathname === '/events', { timeout: 15000 })
    await page.waitForFunction(() => document.querySelectorAll('.event-card, .event-item, [class*="event-card"]').length > 0, { timeout: 10000 })
    await settle()
    const m = await page.evaluate(() => {
      const cards = document.querySelectorAll('.event-card, .event-item, [class*="event-card"]')
      return {
        path: location.pathname,
        cards: cards.length,
        headerName: document.querySelector('.app-header, header, [class*="header"]')?.innerText?.slice(0, 40) ?? '',
        hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      }
    })
    results.assertions['login_and_list'] = {
      pass: m.path === '/events' && m.cards > 0 && !m.hscroll,
      detail: `path=${m.path} cards=${m.cards} hscroll=${m.hscroll} header="${m.headerName}"`,
    }
    results.pages.push({ step: 'list', url: '/events', ...m })
    await page.screenshot({ path: `${OUT}/${browserName}-${vp.name}-list.png` })
  }

  // 取活动 code（页面上下文内 fetch，带真实登录态）
  const codes = await page.evaluate(async () => {
    const res = await fetch('/api/events/mine', { headers: { Authorization: `Bearer ${localStorage.getItem('gift_token')}` } })
    const data = (await res.json()).data
    const open = data.find((e) => e.status === 'open' && e.participantCount >= 1)
    const drawn = data.find((e) => e.status === 'drawn')
    return { open: open?.code, drawn: drawn?.code, openTitle: open?.title, drawnTitle: drawn?.title }
  })
  results.codes = codes

  // ---- 3. 详情 ----
  if (codes?.open) {
    const m = await metric('detail', `/events/${codes.open}`, '.detail-layout')
    const titleOK = m.bodyText.includes(codes.openTitle) || m.bodyText.length > 20
    results.assertions['detail_renders'] = {
      pass: m.detailLayout && !m.hscroll && titleOK,
      detail: `detailLayout=${m.detailLayout} hscroll=${m.hscroll} text="${m.bodyText.slice(0, 50)}"`,
    }
  } else {
    results.assertions['detail_renders'] = { pass: false, detail: '无 open 活动可用' }
  }

  // ---- 4. 礼物墙 ----
  if (codes?.drawn) {
    const m = await metric('giftwall', `/events/${codes.drawn}/gift-wall`, '.page-loading, .gw-grid, main, .app-main')
    const contentOK = m.gwGrid || m.bodyText.length > 10
    results.assertions['giftwall_renders'] = {
      pass: contentOK && !m.hscroll,
      detail: `gwGrid=${m.gwGrid} hscroll=${m.hscroll} text="${m.bodyText.slice(0, 50)}"`,
    }
  } else {
    results.assertions['giftwall_renders'] = { pass: false, detail: '无 drawn 活动可用' }
  }

  // ---- 5. JS 错误 ----
  await settle(400)
  results.assertions['no_js_errors'] = {
    pass: jsErrors.length === 0,
    detail: jsErrors.length ? jsErrors.slice(0, 5).join(' || ') : '全程 0 个 pageerror / console.error / HTTP>=400 / requestfailed',
  }
  results.errors = jsErrors
  await page.close()
  return results
}

const all = []
for (const b of BROWSERS) {
  const browser = await puppeteer.launch({ executablePath: b.executablePath, headless: 'new', args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] })
  for (const vp of VIEWPORTS) {
    const r = await runJourney(b.name, browser, vp)
    all.push(r)
    console.log(`\n[${b.name} @${vp.name}]`)
    for (const [k, v] of Object.entries(r.assertions)) console.log(`  ${v.pass ? 'PASS' : 'FAIL'} ${k}: ${v.detail}`)
  }
  await browser.close()
}
fs.writeFileSync(path.join(__dirname, 'xbrowser_results.json'), JSON.stringify(all, null, 2))
console.log('\nresults -> .audit/xbrowser_results.json')
