// R3 验收：礼物墙遮罩揭晓 + 悄悄话门控
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r3'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

try {
  // 注入 token → 礼物墙
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await page.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))

  // 1. 遮罩态检查
  const maskCount = await page.evaluate(() => document.querySelectorAll('.gw-mask').length)
  console.log('遮罩卡片数:', maskCount)
  await page.screenshot({ path: `${OUT}/01-masked.png` })

  // 2. 点击第一张揭晓
  const firstMask = await page.$('.gw-mask')
  if (firstMask) {
    await firstMask.click()
    await new Promise(r => setTimeout(r, 1200))
    await page.screenshot({ path: `${OUT}/02-revealed.png` })
    const revealedCount = await page.evaluate(() => document.querySelectorAll('.gw-item-card.revealed').length)
    const stillMasked = await page.evaluate(() => document.querySelectorAll('.gw-mask:not(.gw-mask-hidden)').length)
    console.log('已揭晓卡片:', revealedCount, '| 剩余遮罩:', stillMasked)
    // 内容是否可见
    const bodyVisible = await page.evaluate(() => {
      const b = document.querySelector('.gw-item-card.revealed .gw-item-body')
      return b ? b.getAttribute('aria-hidden') : 'no-body'
    })
    console.log('揭晓后内容 aria-hidden:', bodyVisible)
  }

  // 3. 悄悄话门控：找一个已抽签未晒图的活动
  await page.goto(`${PUBLIC}/events/${creds.events.drawn}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const noteText = await page.evaluate(() => {
    const els = [...document.querySelectorAll('p')]
    const note = els.find(n => n.textContent.includes('悄悄话'))
    return note ? note.textContent.trim() : '未找到'
  })
  console.log('悄悄话显示:', noteText)
  await page.screenshot({ path: `${OUT}/03-note-gate.png` })

  // 4. 移动端 375px 检查破版
  const mpage = await browser.newPage()
  await mpage.setViewport({ width: 375, height: 812, isMobile: true, hasTouch: true })
  await mpage.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await mpage.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)
  await mpage.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const overflow = await mpage.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)
  await mpage.screenshot({ path: `${OUT}/04-mobile.png` })
  console.log('移动端横向溢出:', overflow)

  console.log('\nR3 验收截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
