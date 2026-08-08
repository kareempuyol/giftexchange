// 复现：公网邀请链接 BVSF9E 从点击到进入的完整流程
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/debug_invite'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })
const shot = (name) => page.screenshot({ path: `${OUT}/${name}.png` })

try {
  // 1. 未登录点开邀请链接
  await page.goto(`${PUBLIC}/events/BVSF9E`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  await shot('01-invite-link')
  console.log('01 点开邀请链接 →', page.url())

  // 2. 注册新用户（走完整注册）
  await page.goto(`${PUBLIC}/register`, { waitUntil: 'networkidle2' })
  const uname = 'invtest' + Date.now().toString().slice(-6)
  const inputs = await page.$$('input.form-input, input')
  await inputs[0].type(uname)
  await inputs[1].type(`${uname}@example.com`)
  await inputs[2].type('Test1234')
  await inputs[3].type('Test1234')
  await new Promise(r => setTimeout(r, 300))
  await shot('02-register')
  // 点注册
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(n => n.textContent.includes('注册'))
    b?.click()
  })
  await new Promise(r => setTimeout(r, 3000))
  await shot('03-after-register')
  console.log('03 注册后 →', page.url())

  // 3. 手动去邀请链接
  await page.goto(`${PUBLIC}/events/BVSF9E`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  await shot('04-invite-after-login')
  console.log('04 登录后访问邀请 →', page.url())
  const body = await page.evaluate(() => document.body.innerText.slice(0, 300))
  console.log('页面内容:', body.replace(/\n+/g, ' | '))

  // 4. 尝试加入
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(n => n.textContent.includes('加入'))
    b?.click()
  })
  await new Promise(r => setTimeout(r, 1000))
  await shot('05-join-modal')
  console.log('05 加入弹窗')

  console.log('完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
