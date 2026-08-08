// 深度检查标题为何竖排
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
    const header = document.querySelector('.page-header')
    if (!t) return { error: 'no .page-title' }
    const cs = getComputedStyle(t)
    const tr = t.getBoundingClientRect()
    const hr = header?.getBoundingClientRect()
    return {
      titleText: t.textContent.trim(),
      titleW: Math.round(tr.width), titleH: Math.round(tr.height),
      headerW: hr ? Math.round(hr.width) : null,
      display: cs.display,
      flex: cs.flex,
      flexGrow: cs.flexGrow, flexShrink: cs.flexShrink, flexBasis: cs.flexBasis,
      minWidth: cs.minWidth,
      overflowWrap: cs.overflowWrap, wordBreak: cs.wordBreak,
      whiteSpace: cs.whiteSpace,
      fontSize: cs.fontSize, lineHeight: cs.lineHeight,
      parentDisplay: getComputedStyle(t.parentElement).display,
      parentWidth: Math.round(t.parentElement.getBoundingClientRect().width),
      siblings: [...t.parentElement.children].map(c => ({
        cls: c.className, w: Math.round(c.getBoundingClientRect().width)
      })),
      containerWidth: Math.round(document.querySelector('.page-container').getBoundingClientRect().width),
      containerPadding: getComputedStyle(document.querySelector('.page-container')).padding,
    }
  })
  console.log(JSON.stringify(info, null, 2))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
