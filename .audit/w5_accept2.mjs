// 波次5 复验：用 I 实测过的数据（empty_flow_user + L7KQTR 解锁活动）
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const PUBLIC = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 390, height: 844 })

try {
  // 1. empty_flow_user 登录 → 切"参与的" tab
  await page.goto(`${PUBLIC}/login`, { waitUntil: 'networkidle2' })
  await page.evaluate(async () => {
    const r = await fetch('/api/auth/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: 'empty_flow_user', password: 'Test1234' }) })
    const d = await r.json()
    if (d.data?.token) localStorage.setItem('gift_token', d.data.token)
  })
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  // 切到"参与的" tab
  await page.evaluate(() => {
    const tabs = [...document.querySelectorAll('button, [role=tab], .tab')]
    const t = tabs.find(b => b.textContent.includes('参与'))
    if (t) t.click()
  })
  await new Promise(r => setTimeout(r, 800))
  const body1 = await page.evaluate(() => document.body.innerText)
  console.log('1. 参与空态「用邀请码加入」:', body1.includes('用邀请码加入'))

  // 2. verify_user 找解锁活动（gift-wall unlocked=true）
  const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  const wallCode = await page.evaluate(async () => {
    const r = await fetch('/api/events/joined', { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
    const d = await r.json()
    for (const ev of (d.data || [])) {
      if (ev.status !== 'drawn') continue
      const w = await fetch(`/api/events/${ev.code}/gift-wall`, { headers: { Authorization: 'Bearer ' + localStorage.getItem('gift_token') } })
      const wd = await w.json()
      if (wd.data?.unlocked) return ev.code
    }
    return ''
  })
  if (wallCode) {
    await page.goto(`${PUBLIC}/events/${wallCode}/gift-wall`, { waitUntil: 'networkidle2' })
    await new Promise(r => setTimeout(r, 2000))
    const hasReplay = await page.evaluate(() => [...document.querySelectorAll('button')].some(b => b.textContent.includes('再开一局')))
    console.log('2. 解锁活动再开一局按钮:', hasReplay, `(活动 ${wallCode.slice(0,8)})`)
    if (hasReplay) {
      await page.evaluate(() => {
        const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.includes('再开一局'))
        btns[0].click()
      })
      await new Promise(r => setTimeout(r, 600))
      const draft = await page.evaluate(() => JSON.parse(localStorage.getItem('gift_draft') || '{}'))
      console.log('   draft.members:', Array.isArray(draft.members) ? draft.members.length + ' 人' : '无')
    }
  } else {
    console.log('2. verify_user 无已解锁活动（需造数据）')
  }
  console.log('复验完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
