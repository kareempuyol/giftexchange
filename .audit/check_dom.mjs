// 检查 DOM：Header 渲染次数 + 移动端布局数据
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))

  const info = await page.evaluate(() => {
    const headers = [...document.querySelectorAll('header.app-header')]
    const navLinks = [...document.querySelectorAll('.app-nav-link')].map(a => ({
      text: a.textContent.trim(), w: Math.round(a.getBoundingClientRect().width), h: Math.round(a.getBoundingClientRect().height)
    }))
    const headerBox = headers[0]?.getBoundingClientRect()
    const inner = document.querySelector('.app-header-inner')?.getBoundingClientRect()
    const overflowX = document.documentElement.scrollWidth > document.documentElement.clientWidth
    return {
      headerCount: headers.length,
      headerWidth: headerBox ? Math.round(headerBox.width) : null,
      innerWidth: inner ? Math.round(inner.width) : null,
      viewportWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
      overflowX,
      navLinks,
      titleBox: document.querySelector('.page-title')?.getBoundingClientRect() ? {
        w: Math.round(document.querySelector('.page-title').getBoundingClientRect().width),
        h: Math.round(document.querySelector('.page-title').getBoundingClientRect().height)
      } : null,
    }
  })
  console.log(JSON.stringify(info, null, 2))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
