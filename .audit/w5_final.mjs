// 波次5 参与空态终验：全新注册用户
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  const u = 'final_' + Math.floor(Math.random() * 100000)
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async (u) => {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, email: u + '@e.com', password: 'Test1234' }) })
    const d = await r.json()
    localStorage.setItem('gift_token', d.data.token)
  }, u)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 找 tab 容器，打印 tab 文本
  const tabInfo = await page.evaluate(() => {
    const all = [...document.querySelectorAll('button, [role=tab], a')].map(b => b.textContent.trim()).filter(t => t && t.length < 15)
    return [...new Set(all)]
  })
  console.log('tab/按钮候选:', JSON.stringify(tabInfo))

  // 点"参与的"（遍历含'参与'的元素）
  await page.evaluate(() => {
    const els = [...document.querySelectorAll('button, [role=tab], a, div')]
    const t = els.find(b => b.textContent.trim() === '参与的' || b.textContent.includes('参与的'))
    if (t) t.click()
  })
  await new Promise(r => setTimeout(r, 800))
  const body = await page.evaluate(() => document.body.innerText)
  console.log('参与空态「用邀请码加入」:', body.includes('用邀请码加入'))
  console.log('参与空态副文案:', body.includes('还没有参与活动'))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
