// 检查右上角个人菜单 + Profile 页实际内容
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r12'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 1. 右上角区域 DOM 结构
  const headerInfo = await page.evaluate(() => {
    const header = document.querySelector('header')
    if (!header) return 'no header'
    return {
      html: header.innerHTML.slice(0, 1200),
      text: header.innerText.slice(0, 300)
    }
  })
  console.log('=== Header 结构 ===')
  console.log(headerInfo.text)

  // 2. 点击用户名/头像（右上角）
  await page.evaluate(() => {
    const links = [...document.querySelectorAll('header a, header button')]
    const target = links.find(l => l.textContent.includes('verify_user') || l.textContent.includes('⚙️') || l.textContent.includes('我的'))
    if (target) { target.click(); return target.outerHTML }
    return 'not found'
  })
  await new Promise(r => setTimeout(r, 1200))

  // 3. 看是否弹出了菜单或跳转了
  const after = await page.evaluate(() => {
    const body = document.body.innerText.slice(0, 600)
    return { url: location.pathname, body }
  })
  console.log('=== 点击后 ===')
  console.log('URL:', after.url)
  console.log('内容:', after.body.slice(0, 400))

  // 4. 如果有下拉菜单，截图
  await page.screenshot({ path: `${OUT}/01-header-menu.png` })

  // 5. 直接访问 /profile 看有什么
  await page.goto(`${PUBLIC}/profile`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const profileText = await page.evaluate(() => document.body.innerText.slice(0, 800))
  console.log('=== /profile 页面 ===')
  console.log('URL:', await page.evaluate(() => location.pathname))
  console.log('内容:', profileText.slice(0, 500))
  await page.screenshot({ path: `${OUT}/02-profile.png` })
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
