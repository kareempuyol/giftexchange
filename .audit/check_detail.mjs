// 检查活动详情页标题 + Header 各元素宽度
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
  await page.goto(`${PUBLIC}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))

  const info = await page.evaluate(() => {
    const t = document.querySelector('.page-title')
    const headerEls = [...document.querySelectorAll('.app-header-inner > *')].map(el => ({
      cls: el.className || el.tagName,
      text: (el.textContent || '').trim().slice(0, 12),
      w: Math.round(el.getBoundingClientRect().width),
    }))
    return {
      title: t ? {
        text: t.textContent.trim(),
        w: Math.round(t.getBoundingClientRect().width),
        h: Math.round(t.getBoundingClientRect().height),
        lineHeight: getComputedStyle(t).lineHeight,
      } : null,
      headerEls,
      inviteBox: document.querySelector('.invite-box') ? {
        w: Math.round(document.querySelector('.invite-box').getBoundingClientRect().width),
        h: Math.round(document.querySelector('.invite-box').getBoundingClientRect().height),
      } : null,
    }
  })
  console.log(JSON.stringify(info, null, 2))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
