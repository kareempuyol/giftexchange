// 调试：empty_flow_user 参与空态
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async () => {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'empty_flow_user', password: 'Test1234' }) })
    const d = await r.json()
    console.log('login:', d.code, d.message)
    if (d.data?.token) localStorage.setItem('gift_token', d.data.token)
  })
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  // 打印所有按钮和 tab
  const info = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')].map(b => b.textContent.trim().slice(0, 20))
    const tabs = [...document.querySelectorAll('[role=tab], .tab, .tabs button')].map(b => b.textContent.trim().slice(0, 20))
    const body = document.body.innerText.slice(0, 500)
    return { btns, tabs, body }
  })
  console.log('按钮:', JSON.stringify(info.btns))
  console.log('tab:', JSON.stringify(info.tabs))
  console.log('页面文本前 300:', info.body.slice(0, 300))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
