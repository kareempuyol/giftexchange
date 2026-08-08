// 游客落地页实测：未登录访问短码链接
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/roadmap_r2'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })

try {
  // 游客（无 token）访问短码
  await page.goto(`${PUBLIC}/events/KQV2JS`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  await page.screenshot({ path: `${OUT}/01-guest-preview.png` })
  console.log('01 游客预览 URL:', page.url())
  const body = await page.evaluate(() => document.body.innerText.slice(0, 400))
  console.log('内容:', body.replace(/\n+/g, ' | '))

  // 点击"登录后加入" → 应跳登录页带 from
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('a')].find(n => n.textContent.includes('登录后加入'))
    b?.click()
  })
  await new Promise(r => setTimeout(r, 1500))
  console.log('02 点击登录后:', page.url())
  await page.screenshot({ path: `${OUT}/02-after-login-click.png` })
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
