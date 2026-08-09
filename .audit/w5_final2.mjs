// 参与空态终验 v2：真实点击 tab
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  const u = 'final2_' + Math.floor(Math.random() * 100000)
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async (u) => {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, email: u + '@e.com', password: 'Test1234' }) })
    const d = await r.json()
    localStorage.setItem('gift_token', d.data.token)
  }, u)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 用 puppeteer 原生点击"我参与的"（React 按钮）
  const clicked = await page.evaluate(() => {
    const els = [...document.querySelectorAll('button')]
    const t = els.find(b => b.textContent.trim().includes('我参与的'))
    if (t) { t.click(); return t.textContent.trim() }
    return ''
  })
  await new Promise(r => setTimeout(r, 1200))
  const body = await page.evaluate(() => document.body.innerText)
  const inviteBtn = await page.evaluate(() => [...document.querySelectorAll('button')].some(b => b.textContent.includes('用邀请码加入')))
  console.log('点击了:', clicked, '| 邀请码按钮:', inviteBtn)
  console.log('空态区域:', body.slice(body.indexOf('我参与的'), body.indexOf('我参与的') + 300))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
