// 最小验证：创建活动是否正常跳转详情页
import puppeteer from 'puppeteer-core'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  const u = 'mk_' + Math.floor(Math.random() * 100000)
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async (u) => {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, email: u + '@e.com', password: 'Test1234' }) })
    const d = await r.json()
    localStorage.setItem('gift_token', d.data.token)
    window.__tok = d.data.token
  }, u)
  console.log('注册 ok:', u)

  await page.goto(`${PUBLIC}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))

  // 模拟 E2E 的填表方式
  await page.evaluate(() => {
    const setVal = (el, v) => {
      const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
      setter.call(el, v)
      el.dispatchEvent(new Event('input', { bubbles: true }))
    }
    const title = document.querySelector('input[placeholder*="圣诞礼物互赠"]')
    const note = document.querySelector('input[placeholder="写点规则或想说的话（选填）"]')
    const num = document.querySelector('input[type="number"]')
    const dt = document.querySelector('input[type="datetime-local"]')
    if (title) setVal(title, 'E2E-验证创建跳转')
    if (note) setVal(note, '验证用')
    if (num) setVal(num, '100')
    if (dt) setVal(dt, '2026-12-25T20:00')
    return { title: !!title, note: !!note, num: !!num, dt: !!dt }
  }).then(r => console.log('字段定位:', JSON.stringify(r)))

  // 点创建按钮（按钮文字含「创建活动」）
  const clicked = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')]
    const b = btns.find(x => x.textContent.trim() === '创建活动' || x.textContent.includes('创建活动'))
    if (b) { b.click(); return b.textContent.trim() }
    return ''
  })
  console.log('点击按钮:', clicked)

  await new Promise(r => setTimeout(r, 3500))
  const url = await page.evaluate(() => location.pathname)
  const hasCode = await page.evaluate(() => !!document.querySelector('.invite-code-btn'))
  const body = await page.evaluate(() => document.body.innerText.slice(0, 200))
  console.log('跳转后 URL:', url)
  console.log('邀请码按钮:', hasCode)
  console.log('页面片段:', body.replace(/\n+/g, ' | ').slice(0, 150))
  console.log(url.match(/\/events\/[^/]+$/) && hasCode ? '✅ 创建→详情跳转正常' : '❌ 创建跳转异常')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
