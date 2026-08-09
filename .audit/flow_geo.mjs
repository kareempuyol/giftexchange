// 精确坐标：步骤条所有元素的位置
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

  const geo = await page.evaluate(() => {
    const steps = document.querySelector('.flow-steps')
    if (!steps) return 'no flow-steps'
    const srect = steps.getBoundingClientRect()
    const result = {
      steps: { left: Math.round(srect.left), right: Math.round(srect.right), width: Math.round(srect.width), top: Math.round(srect.top) },
      wraps: []
    }
    for (const w of steps.querySelectorAll('.flow-step-wrap')) {
      const r = w.getBoundingClientRect()
      result.wraps.push({
        left: Math.round(r.left), width: Math.round(r.width), top: Math.round(r.top), height: Math.round(r.height),
        children: [...w.children].map(c => {
          const cr = c.getBoundingClientRect()
          return { cls: c.className, left: Math.round(cr.left), width: Math.round(cr.width), text: c.textContent.trim().slice(0, 10) }
        })
      })
    }
    return result
  })
  console.log(JSON.stringify(geo, null, 1))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
