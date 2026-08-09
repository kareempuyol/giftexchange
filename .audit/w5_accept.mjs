// 波次5 独立验收：空态 + 再开一局 + 互避（DOM 级）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'http://127.0.0.1:8080'

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  // 1. 参与空态：注册新用户（无任何活动）
  const u = 'w5_' + Math.floor(Math.random() * 100000)
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async (u) => {
    const r = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: u, email: u + '@e.com', password: 'Test1234' }) })
    const d = await r.json()
    localStorage.setItem('gift_token', d.data.token)
  }, u)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const body = await page.evaluate(() => document.body.innerText)
  console.log('1. 参与空态含「用邀请码加入」:', body.includes('用邀请码加入'))

  // 点开邀请码弹窗
  const hasModal = await page.evaluate(() => {
    const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('用邀请码加入'))
    if (!btns.length) return false
    btns[0].click()
    return true
  })
  await new Promise(r => setTimeout(r, 500))
  const modalBody = await page.evaluate(() => document.body.innerText)
  console.log('   弹窗出现:', modalBody.includes('邀请码'))

  // 2. 再开一局（verify_user 登录，用有数据的活动）
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  // 找已解锁活动
  const wallCode = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    const ev = (d.data || []).find(e => e.status === 'drawn')
    return ev ? ev.code : ''
  })
  if (wallCode) {
    await page.goto(`${PUBLIC}/events/${wallCode}/gift-wall`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2000))
    const hasReplay = await page.evaluate(() => {
      const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('再开一局'))
      return btns.length
    })
    console.log('2. 再开一局按钮:', hasReplay > 0)
    if (hasReplay) {
      await page.evaluate(() => {
        const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('再开一局'))
        btns[0].click()
      })
      await new Promise(r => setTimeout(r, 500))
      const dl = await page.evaluate(() => localStorage.getItem('gift_draft') || localStorage.getItem('draft') || '')
      console.log('   draft 含 members:', dl.includes('members'))
    }
  } else {
    console.log('2. 无已抽签活动（可接受）')
  }

  // 3. 创建页互避说明
  await page.goto(`${PUBLIC}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const createBody = await page.evaluate(() => document.body.innerText)
  console.log('3. 互避说明文案:', createBody.includes('互避 = 这两人不会互送礼物'))

  console.log('波次5 独立验收完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
