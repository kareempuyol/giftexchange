// 验证 UX 改动的截图（tab 激活态 / 复制收件信息 / 选填标注）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = process.env.HOME + '/giftexchange/ui-shots/ux2'
fs.mkdirSync(OUT, { recursive: true })
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  // 1. 活动列表 tab 激活态
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1800))
  await page.screenshot({ path: `${OUT}/01-tabs.png` })
  const tabStyle = await page.evaluate(() => {
    const el = document.querySelector('.tab-active')
    if (!el) return null
    const s = getComputedStyle(el)
    return { text: el.textContent.trim(), bg: s.backgroundColor, color: s.color, weight: s.fontWeight }
  })
  console.log('tab-active:', JSON.stringify(tabStyle))

  // 2. 我的送礼任务：复制收件信息按钮（用 demo 活动，已抽签）
  const code = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    const ev = (d.data || []).find(e => e.status === 'drawn' && e.title.includes('圣诞'))
    return ev ? ev.code : ((d.data || []).find(e => e.status === 'drawn') || {}).code || ''
  })
  console.log('drawn event:', code || 'none')
  if (code) {
    await page.goto(`${PUBLIC}/events/${code}`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2200))
    const hasCopy = await page.evaluate(() => [...document.querySelectorAll('button')].some(b => b.textContent.includes('复制收件信息')))
    console.log('复制收件信息按钮:', hasCopy)
    if (hasCopy) {
      // 滚到该区域截图
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('复制收件信息'))
        if (btn) btn.scrollIntoView({ block: 'center' })
      })
      await new Promise(r => setTimeout(r, 600))
      await page.screenshot({ path: `${OUT}/02-copy-contact.png` })
      // 点击验证 toast + 剪贴板
      await page.evaluate(() => {
        const btn = [...document.querySelectorAll('button')].find(b => b.textContent.includes('复制收件信息'))
        if (btn) btn.click()
      })
      await new Promise(r => setTimeout(r, 900))
      const clip = await page.evaluate(async () => { try { return await navigator.clipboard.readText() } catch { return '(no-perm)' } })
      console.log('剪贴板内容:', JSON.stringify(clip).slice(0, 120))
      await page.screenshot({ path: `${OUT}/03-copy-toast.png` })
    }
  }

  // 3. 创建页选填标注
  await page.goto(`${PUBLIC}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1800))
  const labels = await page.evaluate(() => [...document.querySelectorAll('.form-label')].map(l => l.textContent.trim()))
  console.log('表单标签:', JSON.stringify(labels))
  await page.screenshot({ path: `${OUT}/04-create-labels.png`, fullPage: true })
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
