// 第二批前端验收：海报 + 再开一局 + 模板
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'

const creds = JSON.parse(fs.readFileSync('/tmp/audit_creds.json', 'utf8'))
const PUBLIC = 'https://select-categories-upgrades-ellis.trycloudflare.com'
const OUT = process.env.HOME + '/giftexchange/ui-shots/r7'
fs.mkdirSync(OUT, { recursive: true })

const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'] })
const page = await browser.newPage()
await page.setViewport({ width: 1280, height: 800 })

const clickText = async (sel, txt) => {
  const el = await page.evaluateHandle(({ s, t }) => {
    const nodes = [...document.querySelectorAll(s)]
    return nodes.find(n => n.textContent.includes(t)) || null
  }, { s: sel, t: txt })
  if (el && (await el.asElement())) { await el.asElement().click(); return true }
  return false
}

try {
  await page.goto(`${PUBLIC}/events`, { waitUntil: 'networkidle2' })
  await page.evaluate((t) => localStorage.setItem('gift_token', t), creds.orgToken)

  // 1. 活动详情：邀请海报按钮
  await page.goto(`${PUBLIC}/events/${creds.events.open}`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1500))
  const hasPosterBtn = await clickText('button', '邀请海报')
  console.log('1. 邀请海报按钮:', hasPosterBtn)
  await new Promise(r => setTimeout(r, 1500))
  await page.screenshot({ path: `${OUT}/01-invite-poster.png` })
  // 关闭弹窗
  await clickText('button', '关闭')
  await new Promise(r => setTimeout(r, 500))

  // 2. 礼物墙：高光海报 + 再开一局
  await page.goto(`${PUBLIC}/events/${creds.events.unlocked}/gift-wall`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 2000))
  const hasHighlight = await clickText('button', '生成高光海报')
  console.log('2. 高光海报按钮:', hasHighlight)
  await new Promise(r => setTimeout(r, 1500))
  await page.screenshot({ path: `${OUT}/02-highlight-poster.png` })
  await clickText('button', '关闭')
  await new Promise(r => setTimeout(r, 500))

  // 3. 再开一局 → 跳转 + 预填
  await clickText('button', '再开一局')
  await new Promise(r => setTimeout(r, 1500))
  console.log('3. 再开一局后 URL:', page.url())
  const titleVal = await page.evaluate(() => {
    const i = document.querySelector('input[placeholder*="活动名称"], input[placeholder*="圣诞"]')
    return i ? i.value : '未找到'
  })
  console.log('   预填标题:', titleVal)
  await page.screenshot({ path: `${OUT}/03-replay-draft.png` })

  // 4. 模板
  await page.goto(`${PUBLIC}/events/new`, { waitUntil: 'networkidle2' })
  await new Promise(r => setTimeout(r, 1000))
  await clickText('button', '🎂 生日惊喜')
  await new Promise(r => setTimeout(r, 800))
  const tTitle = await page.evaluate(() => {
    const i = document.querySelector('input[placeholder*="活动名称"], input[placeholder*="圣诞"]')
    return i ? i.value : '未找到'
  })
  console.log('4. 模板预填标题:', tTitle)
  await page.screenshot({ path: `${OUT}/04-template.png` })

  console.log('\n第二批前端验收截图完成')
} catch (e) {
  console.error('ERR:', e.message)
} finally {
  await browser.close()
}
