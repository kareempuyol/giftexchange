// 验证：移动端 Header 头像入口 + Profile 头像上传
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

  // 1. Header 移动端：头像入口是否可见
  const header = await page.evaluate(() => {
    const h = document.querySelector('header')
    if (!h) return null
    const avatar = h.querySelector('.app-avatar')
    const userLink = h.querySelector('.app-username')
    const display = avatar ? getComputedStyle(avatar).display : 'none'
    return { hasAvatar: !!avatar, display, userLinkHref: userLink?.getAttribute('href') }
  })
  console.log('1. Header 头像入口:', JSON.stringify(header))
  await page.screenshot({ path: `${OUT}/03-header-mobile.png` })

  // 2. 点头像 → 跳 /profile
  await page.evaluate(() => {
    const link = document.querySelector('header .app-username')
    if (link) link.click()
  })
  await new Promise(r => setTimeout(r, 1500))
  console.log('2. 点击后 URL:', await page.evaluate(() => location.pathname))

  // 3. Profile 页头像上传区
  const profileInfo = await page.evaluate(() => {
    const btn = document.querySelector('button[title="点击更换头像"]')
    return { hasUploadBtn: !!btn, hint: document.body.innerText.includes('点击头像更换') }
  })
  console.log('3. 头像上传按钮:', JSON.stringify(profileInfo))
  await page.screenshot({ path: `${OUT}/04-profile-avatar.png` })
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
