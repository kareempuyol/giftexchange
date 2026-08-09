// 查活动详情页中部状态区块
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

  // L9UMHF 是用户截图里的活动（KDNiao 实测）
  await page.goto(`${PUBLIC}/events/L9UMHF`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 抓取页面主体结构（gift-card 区块 + 标题）
  const info = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.gift-card')]
    return cards.map((c, i) => {
      const txt = c.innerText.slice(0, 150).replace(/\n+/g, ' | ')
      const cls = c.className
      return { i, cls, txt }
    })
  })
  info.forEach(x => console.log(`[卡片${x.i}] ${x.cls}\n  ${x.txt}\n`))

  // 找"摇号"或"招募中"元素
  const statusEl = await page.evaluate(() => {
    const all = [...document.querySelectorAll('*')]
    const hits = all.filter(el => el.children.length === 0 && /摇号|等待抽签|招募中/.test(el.textContent || ''))
    return hits.map(h => ({ tag: h.tagName, cls: h.className, text: h.textContent.trim().slice(0, 50) }))
  })
  console.log('状态元素:', JSON.stringify(statusEl, null, 1))
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
