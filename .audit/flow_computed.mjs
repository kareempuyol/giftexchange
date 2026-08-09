// 查 computed style：wrap 和 steps 的实际 flex 值 + 页面加载的 CSS 文件
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events/8715bec9-c612-4810-b8c4-db670a8b60a2`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2500))

  const info = await page.evaluate(() => {
    // 页面加载的 css 链接
    const cssLinks = [...document.querySelectorAll('link[rel=stylesheet]')].map(l => l.href.split('/').pop())
    const steps = document.querySelector('.flow-steps')
    const wrap = document.querySelector('.flow-step-wrap')
    if (!steps || !wrap) return { cssLinks, err: 'no elements' }
    const sc = getComputedStyle(steps)
    const wc = getComputedStyle(wrap)
    const stepEl = wrap.querySelector('.flow-step')
    const stepC = stepEl ? getComputedStyle(stepEl) : null
    return {
      cssLinks,
      steps: { display: sc.display, flexWrap: sc.flexWrap, width: sc.width },
      wrap: { display: wc.display, flex: wc.flex, flexGrow: wc.flexGrow, flexBasis: wc.flexBasis, minWidth: wc.minWidth, width: wc.width },
      step: stepC ? { flex: stepC.flex, width: stepC.width, display: stepC.display } : null,
      wrapCount: steps.querySelectorAll('.flow-step-wrap').length,
    }
  })
  console.log(JSON.stringify(info, null, 1))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
