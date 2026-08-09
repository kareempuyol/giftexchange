import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })
const scan = async (name, url) => {
  await page.goto(`${BASE}${url}`, { waitUntil: 'networkidle2' })
  await new Promise((r) => setTimeout(r, 700))
  const r = await page.evaluate(() => {
    const issues = []
    document.querySelectorAll('img').forEach((img) => {
      if (!img.hasAttribute('alt')) issues.push(`img 缺 alt: ${img.src?.slice(-40)}`)
    })
    document.querySelectorAll('input, textarea, select').forEach((el) => {
      if (el.type === 'hidden' || el.style.display === 'none') return
      const id = el.id
      const hasLabel = (id && document.querySelector(`label[for="${id}"]`)) || el.getAttribute('aria-label') || el.getAttribute('aria-labelledby')
      if (!hasLabel) issues.push(`${el.tagName} 缺可访问名: ${el.className} ${el.placeholder || ''}`)
    })
    const h1s = document.querySelectorAll('h1').length
    const buttons = [...document.querySelectorAll('button')].filter((b) => {
      const r = b.getBoundingClientRect()
      return r.height > 0 && !b.textContent.trim() && !b.getAttribute('aria-label')
    })
    buttons.forEach((b) => issues.push(`button 无文本/aria-label: ${b.className}`))
    return { h1s, issues }
  })
  console.log(`${name}: h1=${r.h1s} issues=${r.issues.length ? JSON.stringify(r.issues) : 'none'}`)
}
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle2' })
await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
await scan('login(未登录)', '/login')
await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
await scan('register', '/register')
await scan('forgot', '/forgot-password')
await scan('events', '/events')
await scan('create', '/events/new')
await scan('detail-drawn', `/events/${creds.events.drawn}`)
await scan('detail-open', `/events/${creds.events.open}`)
await scan('giftwall', `/events/${creds.events.unlocked}/gift-wall`)
await scan('dashboard', `/events/${creds.events.drawn}/dashboard`)
await scan('profile', '/profile')
await browser.close()
