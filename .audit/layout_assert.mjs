// 布局/触控目标程序化断言：三视口关键页面
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })

async function check(name, url, viewport) {
  const page = await browser.newPage()
  await page.setViewport(viewport)
  await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
  await new Promise((r) => setTimeout(r, 900))
  const res = await page.evaluate(() => {
    const out = {}
    // 礼物墙列对齐
    const cards = [...document.querySelectorAll('.gw-item-card')].map((el) => {
      const r = el.getBoundingClientRect()
      return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
    })
    out.gwCards = cards.slice(0, 4)
    // 详情两栏
    const l = document.querySelector('.detail-col-left')?.getBoundingClientRect()
    const rcol = document.querySelector('.detail-col-right')?.getBoundingClientRect()
    out.twoCol = l && rcol ? { left: { x: Math.round(l.x), w: Math.round(l.width) }, right: { x: Math.round(rcol.x), w: Math.round(rcol.width) }, sideBySide: rcol.x >= l.x + l.width - 4 } : null
    // 触控目标：所有可见交互元素尺寸
    const small = []
    document.querySelectorAll('button, a, input, select, textarea, [role="button"], [role="link"]').forEach((el) => {
      const st = getComputedStyle(el)
      if (st.visibility === 'hidden' || st.display === 'none') return
      const r = el.getBoundingClientRect()
      if (r.width === 0 && r.height === 0) return
      const isBtnLike = el.tagName === 'BUTTON' || el.getAttribute('role') === 'button'
      if (isBtnLike && (r.height < 40 || r.width < 40)) {
        small.push({ tag: el.tagName, cls: (el.className || '').toString().slice(0, 40), text: (el.textContent || '').trim().slice(0, 20), w: Math.round(r.width), h: Math.round(r.height) })
      }
    })
    out.smallTargets = small.slice(0, 10)
    // 页头布局
    const header = document.querySelector('.app-header-inner')?.getBoundingClientRect()
    out.header = header ? { w: Math.round(header.width), x: Math.round(header.x) } : null
    return out
  })
  console.log(`\n== ${name} @${viewport.width}x${viewport.height}`)
  console.log('gw cards:', JSON.stringify(res.gwCards))
  console.log('two-col:', JSON.stringify(res.twoCol))
  console.log('small targets (<40px):', res.smallTargets.length ? JSON.stringify(res.smallTargets) : 'none')
  await page.close()
}

await check('giftwall', `/events/${creds.events.unlocked}/gift-wall`, { width: 1440, height: 900 })
await check('detail', `/events/${creds.events.drawn}`, { width: 1280, height: 800 })
await check('events', '/events', { width: 1280, height: 800 })
await check('giftwall-768', `/events/${creds.events.unlocked}/gift-wall`, { width: 768, height: 1024 })
await check('detail-768', `/events/${creds.events.drawn}`, { width: 768, height: 1024 })
await check('dashboard-768', `/events/${creds.events.drawn}/dashboard`, { width: 768, height: 1024 })
await browser.close()
console.log('\nlayout checks done')
