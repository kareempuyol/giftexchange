// ============================================================
// E2E 用户全旅程测试（首次使用用户视角，390px 移动视口）
// 覆盖：注册→建活动→邀请游客加入×2→抽签→我的任务→发货→
//       晒图(隐私)→礼物墙解锁→高光海报→个人中心(昵称/头像/地址)
//       →改密码→旧密码失效→通知铃铛→归档/恢复
// 每步截图到 .audit/e2e-shots/，异常记录为缺陷不中断。
// ============================================================
import puppeteer from 'puppeteer-core'
import fs from 'node:fs'
import path from 'node:path'
import zlib from 'node:zlib'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const BASE = 'http://127.0.0.1:8080'
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
const OUT = path.join(__dirname, 'e2e-shots')
const TEST_IMG = path.join(__dirname, 'test_avatar.png')
fs.mkdirSync(OUT, { recursive: true })

// ---------------- 测试图片生成（200x200 纯色 PNG） ----------------
const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()
const crc32 = (buf) => {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}
function makePng(size, [r, g, b]) {
  const raw = Buffer.alloc(size * (1 + size * 3))
  for (let y = 0; y < size; y++) {
    raw[y * (1 + size * 3)] = 0
    for (let x = 0; x < size; x++) {
      const o = y * (1 + size * 3) + 1 + x * 3
      raw[o] = r; raw[o + 1] = g; raw[o + 2] = b
    }
  }
  const chunk = (type, data) => {
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const td = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(td))
    return Buffer.concat([len, td, crc])
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8   // bit depth
  ihdr[9] = 2   // color type RGB
  const sig = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10])
  return Buffer.concat([sig, chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))])
}
fs.writeFileSync(TEST_IMG, makePng(200, [232, 85, 61]))

// ---------------- 结果收集 ----------------
const results = []   // {step, name, pass}
const defects = []   // {step, name, severity, message}
let shotN = 0
const shot = async (page, name) => {
  shotN += 1
  const file = `${String(shotN).padStart(2, '0')}-${name}.png`
  await page.screenshot({ path: path.join(OUT, file), fullPage: true })
  console.log(`📸 ${file}`)
  return file
}
const shotDefect = async (page, name) => {
  const file = `D-${name}.png`
  await page.screenshot({ path: path.join(OUT, file), fullPage: true })
  return file
}
function check(step, name, cond, message = '', severity = 'P1') {
  const pass = !!cond
  results.push({ step, name, pass })
  console.log(`  [${pass ? 'PASS' : 'FAIL'}] ${name}${pass ? '' : ' — ' + message}`)
  if (!pass) defects.push({ step, name, severity, message })
  return pass
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function waitFor(page, fn, timeout = 20000, interval = 250) {
  const t0 = Date.now()
  while (Date.now() - t0 < timeout) {
    try {
      if (await page.evaluate(fn)) return true
    } catch { /* ignore */ }
    await sleep(interval)
  }
  return false
}
const waitText = (page, text, timeout = 15000) => {
  const t0 = Date.now()
  return (async () => {
    while (Date.now() - t0 < timeout) {
      try {
        if (await page.evaluate((t) => !!(document.body && document.body.innerText.includes(t)), text)) return true
      } catch { /* ignore */ }
      await sleep(250)
    }
    return false
  })()
}
const waitURL = (page, substr, timeout = 15000) => {
  const t0 = Date.now()
  return (async () => {
    while (Date.now() - t0 < timeout) {
      try {
        if (await page.evaluate((s) => location.href.includes(s), substr)) return true
      } catch { /* ignore */ }
      await sleep(250)
    }
    return false
  })()
}

// React 受控输入：原生 setter + input/change 事件
async function reactType(page, selector, text) {
  const el = await page.$(selector)
  if (!el) return false
  await el.evaluate((node, value) => {
    const proto = node instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
    const setter = Object.getOwnPropertyDescriptor(proto, 'value').set
    setter.call(node, value)
    node.dispatchEvent(new Event('input', { bubbles: true }))
    node.dispatchEvent(new Event('change', { bubbles: true }))
  }, text)
  return true
}

async function clickText(page, text, selector = 'button,a') {
  return page.evaluate(({ sel, txt }) => {
    const nodes = [...document.querySelectorAll(sel)]
    const el = nodes.find((n) => n.textContent.trim().includes(txt) && n.offsetParent !== null)
    if (el) { el.click(); return true }
    return false
  }, { sel: selector, txt: text })
}

// 每个步骤独立 try/catch：异常记录缺陷，不中断旅程
async function step(name, fn) {
  console.log(`\n== ${name} ==`)
  try {
    await fn()
  } catch (e) {
    const f = await shotDefect(ctxA ? ctxA.page : null, name.replace(/\s+/g, '-'))
    defects.push({ step: name, name: '异常', severity: 'P0', message: e.message, shot: f })
    console.log(`  [EXC] ${name}: ${e.message}`)
  }
}

// ---------------- 启动浏览器（三个独立 context = 三个用户） ----------------
const browser = await puppeteer.launch({
  executablePath: CHROME,
  headless: true,
  args: ['--no-sandbox', '--disable-gpu'],
})
const mkCtx = async () => {
  const ctx = await browser.createBrowserContext()
  const page = await ctx.newPage()
  await page.setViewport({ width: 390, height: 844 })
  return { ctx, page }
}
const A = await mkCtx()
const B = await mkCtx()
const C = await mkCtx()
const ctxA = A // step() 里兜底截图用

// 每次运行唯一用户
const ts = Date.now().toString(36)
const U = {
  alice: { username: `e2e_alice_${ts}`, email: `e2e_alice_${ts}@test.com`, pwd: 'Alice123' },
  bob:   { username: `e2e_bob_${ts}`,   email: `e2e_bob_${ts}@test.com`,   pwd: 'Bob12345' },
  carol: { username: `e2e_carol_${ts}`, email: `e2e_carol_${ts}@test.com`, pwd: 'Carol123' },
}
const EVENT_TITLE = `E2E 全旅程测试 ${new Date().toLocaleDateString('zh-CN')}`
let eventShortCode = ''
let eventCode = ''

const register = async (page, u, shotName) => {
  await page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
  await waitText(page, '注册')
  await reactType(page, 'input[placeholder="用户名"]', u.username)
  await reactType(page, 'input[placeholder="邮箱"]', u.email)
  await reactType(page, 'input[placeholder="密码"]', u.pwd)
  await reactType(page, 'input[placeholder="确认密码"]', u.pwd)
  await shot(page, shotName)
  await clickText(page, '注册', 'button')
  await waitURL(page, '/events', 15000)
  return page.url()
}

const joinEvent = async (page, u) => {
  await page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
  await waitText(page, '加入这个活动')
  await clickText(page, '加入这个活动')
  await waitText(page, '收件人姓名')
  // 第一步：收件信息
  await reactType(page, 'input[placeholder="真实姓名"]', u.username)
  await reactType(page, 'input[placeholder="手机号"]', '13800138000')
  await reactType(page, 'textarea[placeholder*="省市区"]', '广东省深圳市南山区科技园路 1 号')
  await clickText(page, '下一步')
  await waitText(page, '我喜欢的礼物')
  // 第二步：心愿单
  await reactType(page, 'input[placeholder*="咖啡"]', '咖啡、手办、书籍')
  await reactType(page, 'input[placeholder*="香水"]', '香水、毛绒玩具')
  await clickText(page, '确认加入')
  await waitText(page, '你已加入', 15000)
}

const postGift = async (page, { stars, review, mode, withPhoto }) => {
  await page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
  await waitText(page, '我收到的礼物')
  await waitText(page, '晒出礼物')
  await page.click(`button[aria-label="${stars} 星"]`)
  const ta = await page.$('textarea[placeholder="收到礼物想说点什么？"]')
  await ta.evaluate((node, v) => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set.call(node, v)
    node.dispatchEvent(new Event('input', { bubbles: true }))
  }, review)
  if (mode === 'text') {
    await clickText(page, '仅文字', 'label')
  } else if (withPhoto) {
    await clickText(page, '公开照片', 'label')
    const input = await page.$('.iu-input')
    await input.uploadFile(TEST_IMG)
    await waitFor(page, () => !!document.querySelector('.iu-preview'))
  }
  await clickText(page, '晒出礼物')
  return waitText(page, '晒图成功', 15000)
}

// ================= 旅程开始 =================
try {
  // ---------- 1. Alice 注册 → 自动登录 ----------
  await step('1. 注册 Alice', async () => {
    const url = await register(A.page, U.alice, '01-register-alice')
    check('1', '注册后自动登录进入活动列表', url.includes('/events'), `url=${url}`)
    const nameOk = await waitText(A.page, U.alice.username)
    check('1', '列表页显示用户名', nameOk)
    await shot(A.page, '02-events-home-after-register')
  })

  // ---------- 2. Alice 创建活动 ----------
  await step('2. 创建活动', async () => {
    await A.page.goto(`${BASE}/events/new`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '创建活动')
    await reactType(A.page, 'input[placeholder*="圣诞礼物互赠"]', EVENT_TITLE)
    await reactType(A.page, 'input[placeholder="写点规则或想说的话（选填）"]', '这是 E2E 全旅程测试活动，大家互相送惊喜 🎁')
    await reactType(A.page, 'input[type="number"]', '100')
    await reactType(A.page, 'input[type="datetime-local"]', '2026-08-20T20:00')
    await shot(A.page, '03-create-event-form-filled')
    await clickText(A.page, '创建活动', 'button')
    const ok = await waitFor(A.page, () => /\/events\/[^/]+$/.test(location.pathname) && !!document.querySelector('.invite-code-btn'), 15000)
    check('2', '创建后跳转活动详情页', ok, `url=${await A.page.evaluate(() => location.href)}`)
    eventCode = await A.page.evaluate(() => location.pathname.split('/').pop())
    eventShortCode = await A.page.evaluate(() => {
      const el = document.querySelector('.invite-code-btn')
      return el ? el.textContent.trim().replace(/[📋\s]/g, '') : ''
    })
    check('2', '邀请短码可见', !!eventShortCode, `shortCode=${eventShortCode}`)
    check('2', '详情页显示活动标题', await waitText(A.page, EVENT_TITLE))
    await shot(A.page, '04-event-detail-created')

    // 创建者需主动加入才能参与抽签（后端不自动加入）
    await clickText(A.page, '加入这个活动')
    await waitText(A.page, '收件人姓名')
    await reactType(A.page, 'input[placeholder="真实姓名"]', U.alice.username)
    await reactType(A.page, 'input[placeholder="手机号"]', '13800138000')
    await reactType(A.page, 'textarea[placeholder*="省市区"]', '北京市朝阳区建国路 88 号')
    await clickText(A.page, '下一步')
    await waitText(A.page, '我喜欢的礼物')
    await reactType(A.page, 'input[placeholder*="咖啡"]', '咖啡、相机、旅行')
    await clickText(A.page, '确认加入')
    const joined = await waitText(A.page, '参与者（1）', 15000)
    check('2', '组织者加入活动（创建者需主动加入）', joined)
    await shot(A.page, '05-alice-joined')
  })

  // ---------- 3. 复制邀请链接 ----------
  await step('3. 复制邀请链接', async () => {
    await clickText(A.page, '复制邀请链接')
    const copied = await waitFor(
      A.page,
      () => {
        const ts = [...document.querySelectorAll('.toast')]
        return ts.some((t) => t.textContent.includes('已复制') || t.textContent.includes('邀请链接'))
      },
      5000
    )
    const toast = await A.page.evaluate(() => document.querySelector('.toast')?.textContent || '')
    check('3', '复制邀请链接反馈', copied, `toast="${toast}"`)
    await shot(A.page, '05-invite-copy-toast')
  })

  // ---------- 4. 游客 B 打开邀请链接 → 注册 → 回跳加入 ----------
  await step('4. 游客 B 经邀请链接加入', async () => {
    await B.page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
    const landing = await waitText(B.page, '登录后加入')
    check('4', '游客落地页展示', landing, `url=${await B.page.evaluate(() => location.href)}`)
    check('4', '游客落地页标题正确', await waitText(B.page, EVENT_TITLE))
    await shot(B.page, '06-guest-landing')

    await clickText(B.page, '登录后加入')
    const loginPage = await waitURL(B.page, 'from=events', 10000)
    check('4', '落地页跳登录且带 from 回跳', loginPage)
    await shot(B.page, '07-guest-login-with-from')

    await clickText(B.page, '立即注册')
    await waitText(B.page, '注册')
    await reactType(B.page, 'input[placeholder="用户名"]', U.bob.username)
    await reactType(B.page, 'input[placeholder="邮箱"]', U.bob.email)
    await reactType(B.page, 'input[placeholder="密码"]', U.bob.pwd)
    await reactType(B.page, 'input[placeholder="确认密码"]', U.bob.pwd)
    await clickText(B.page, '注册', 'button')
    const backToEvent = await waitURL(B.page, `/events/${eventShortCode}`, 15000)
    check('4', '注册后回跳活动页', backToEvent, `url=${await B.page.evaluate(() => location.href)}`)

    await joinEvent(B.page, U.bob)
    check('4', 'B 加入成功（你已加入）', await waitText(B.page, '你已加入'))
    await shot(B.page, '08-b-joined')
  })

  // ---------- 5. 邀请第 3 人 C 加入 ----------
  await step('5. 游客 C 加入', async () => {
    await C.page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
    await waitText(C.page, '登录后加入')
    await clickText(C.page, '登录后加入')
    await clickText(C.page, '立即注册')
    await waitText(C.page, '注册')
    await reactType(C.page, 'input[placeholder="用户名"]', U.carol.username)
    await reactType(C.page, 'input[placeholder="邮箱"]', U.carol.email)
    await reactType(C.page, 'input[placeholder="密码"]', U.carol.pwd)
    await reactType(C.page, 'input[placeholder="确认密码"]', U.carol.pwd)
    await clickText(C.page, '注册', 'button')
    await waitURL(C.page, `/events/${eventShortCode}`, 15000)
    await joinEvent(C.page, U.carol)
    check('5', 'C 加入成功', await waitText(C.page, '你已加入'))
    await shot(C.page, '09-c-joined')

    // Alice 刷新确认 3 人
    await A.page.goto(`${BASE}/events/${eventCode}`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '参与者（3）')
    check('5', '组织者看到 3 名参与者', await waitText(A.page, '参与者（3）'))
    await shot(A.page, '10-alice-3-participants')
  })

  // ---------- 6. 抽签 ----------
  await step('6. 抽签', async () => {
    await A.page.goto(`${BASE}/events/${eventCode}`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '开始抽签')
    await shot(A.page, '11-draw-confirm-modal')
    await clickText(A.page, '开始抽签')
    await waitText(A.page, '确认抽签？')
    await clickText(A.page, '确认抽签')
    const drawn = await waitText(A.page, '抽签完成', 15000)
    check('6', '抽签完成提示', drawn)
    check('6', '状态变为已抽签', await waitText(A.page, '已抽签'))
    await shot(A.page, '12-alice-after-draw')
  })

  // ---------- 7. 各自看到我的送礼任务 ----------
  await step('7. 我的送礼任务', async () => {
    for (const [who, page] of [['A', A.page], ['B', B.page], ['C', C.page]]) {
      await page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
      const t = await waitText(page, '我的送礼任务')
      check('7', `${who} 看到我的送礼任务`, t)
      const receiver = await page.evaluate(() => {
        const m = document.body.innerText.match(/我要送给\s*([^\n]+)/)
        return m ? m[1].trim() : ''
      })
      check('7', `${who} 有明确送礼对象`, !!receiver, `receiver="${receiver}"`)
      await shot(page, `13-${who}-my-task`)
    }
  })

  // ---------- 8. B 发货（快递单号 + 悄悄话） ----------
  await step('8. B 发货', async () => {
    await B.page.goto(`${BASE}/events/${eventShortCode}`, { waitUntil: 'networkidle2' })
    await waitText(B.page, '填写快递单号')
    await clickText(B.page, '填写快递单号')
    await waitText(B.page, '快递单号')
    await reactType(B.page, 'input[placeholder="快递公司（选填）"]', '顺丰速运')
    await reactType(B.page, 'input[placeholder="快递单号 *"]', 'SF1234567890')
    await reactType(B.page, 'input[placeholder*="悄悄话"]', '祝你天天开心！')
    await shot(B.page, '14-b-shipment-form')
    await clickText(B.page, '确认发货')
    const saved = await waitText(B.page, '发货信息已保存', 15000)
    check('8', '发货保存成功', saved)
    await shot(B.page, '15-b-shipped')
  })

  // ---------- 9. 三人晒图（评分 + 评价 + 隐私模式） ----------
  await step('9a. Alice 晒图（仅文字）', async () => {
    const ok = await postGift(A.page, { stars: 5, review: '超用心的礼物，谢谢！', mode: 'text' })
    check('9', 'Alice 晒图成功（仅文字模式）', ok)
    await shot(A.page, '16-alice-posted-text')
  })
  await step('9b. B 晒图（仅文字）', async () => {
    const ok = await postGift(B.page, { stars: 4, review: '礼物很喜欢，感谢！', mode: 'text' })
    check('9', 'B 晒图成功（仅文字模式）', ok)
    await shot(B.page, '17-b-posted-text')
  })
  await step('9c. C 晒图（公开照片）', async () => {
    const ok = await postGift(C.page, { stars: 5, review: '照片晒出来！这个礼物绝了 🎉', mode: 'photo', withPhoto: true })
    check('9', 'C 晒图成功（公开照片）', ok)
    await shot(C.page, '18-c-posted-photo')
  })

  // ---------- 10. 礼物墙解锁 + 高光海报 ----------
  await step('10. 礼物墙解锁与海报', async () => {
    await A.page.goto(`${BASE}/events/${eventCode}/gift-wall`, { waitUntil: 'networkidle2' })
    const unlocked = await waitText(A.page, '生成高光海报', 15000)
    check('10', '礼物墙已解锁（3/3 晒图）', unlocked)
    await shot(A.page, '19-gift-wall-unlocked')
    await waitFor(A.page, () => !!document.querySelector('.gw-mask'))
    await A.page.click('.gw-mask')
    await sleep(800)
    check('10', '点击揭晓礼物卡片', await A.page.evaluate(() => !!document.querySelector('.gw-item-card.revealed')))
    await shot(A.page, '20-gift-wall-revealed')
    await clickText(A.page, '生成高光海报')
    const poster = await waitText(A.page, '下载海报')
    check('10', '高光海报弹窗', poster)
    await shot(A.page, '21-highlight-poster')
    await clickText(A.page, '关闭')
    await sleep(400)
  })

  // ---------- 11. 个人中心：昵称/头像/地址 ----------
  await step('11a. 改昵称 → Header 立即更新', async () => {
    await A.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '常用信息')
    await shot(A.page, '22-profile-before-edit')
    await A.page.evaluate(() => {
      const inputs = [...document.querySelectorAll('.form-input')]
      const nick = inputs.find((i) => i.closest('.form-group')?.querySelector('.form-label')?.textContent.includes('昵称'))
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set
      setter.call(nick, '爱丽丝')
      nick.dispatchEvent(new Event('input', { bubbles: true }))
    })
    await clickText(A.page, '保存资料')
    const saved = await waitText(A.page, '个人资料已保存', 10000)
    check('11', '资料保存成功', saved)
    await sleep(500)
    const headerName = await A.page.evaluate(() => document.querySelector('.app-username-text')?.textContent || '')
    check('11', 'Header 立即显示新昵称', headerName === '爱丽丝', `header="${headerName}"`)
    await shot(A.page, '23-profile-nickname-saved')
  })

  await step('11b. 上传头像 → Header 头像更新', async () => {
    await A.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '点击头像更换')
    const input = await A.page.$('input[type="file"]')
    await input.uploadFile(TEST_IMG)
    const ok = await waitText(A.page, '头像已更新', 15000)
    check('11', '头像上传保存成功', ok)
    await sleep(800)
    const headerAvatar = await A.page.evaluate(() => {
      const img = document.querySelector('header .app-avatar')
      return img ? { tag: img.tagName, src: img.getAttribute('src') || '' } : null
    })
    check('11', 'Header 头像立即更新为图片', !!headerAvatar && headerAvatar.tag === 'IMG' && !!headerAvatar.src,
      JSON.stringify(headerAvatar))
    await shot(A.page, '24-profile-avatar-saved')
  })

  await step('11c. 保存地址/收件人/偏好', async () => {
    await A.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '常用信息')
    await reactType(A.page, 'input[placeholder="收礼人电话"]', '13900139000')
    await reactType(A.page, 'input[placeholder="收礼人姓名"]', '爱丽丝')
    await reactType(A.page, 'textarea[placeholder="收礼地址"]', '上海市浦东新区世纪大道 100 号')
    await reactType(A.page, 'textarea[placeholder*="尺码颜色"]', '喜欢简约风，M 码')
    await clickText(A.page, '保存资料')
    const saved = await waitText(A.page, '个人资料已保存', 10000)
    check('11', '地址/收件人/偏好保存成功', saved)
    await shot(A.page, '25-profile-contact-saved')
  })

  // ---------- 12. 修改密码 → 退出 → 旧密码失败 → 新密码成功 ----------
  await step('12a. 修改密码', async () => {
    await A.page.goto(`${BASE}/profile`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '修改密码')
    await reactType(A.page, 'input[placeholder="输入当前密码"]', U.alice.pwd)
    await reactType(A.page, 'input[placeholder*="至少 6 位"]', 'Alice1234')
    await reactType(A.page, 'input[placeholder="再次输入新密码"]', 'Alice1234')
    await shot(A.page, '26-password-change-form')
    await clickText(A.page, '修改密码', 'button')
    const ok = await waitText(A.page, '密码已修改', 10000)
    check('12', '修改密码成功', ok)
  })

  await step('12b. 退出 → 旧密码登录失败', async () => {
    await clickText(A.page, '退出', 'button')
    const atLogin = await waitURL(A.page, '/login', 10000)
    check('12', '退出回到登录页', atLogin)
    await shot(A.page, '27-logout-login-page')
    await reactType(A.page, 'input[placeholder="用户名"]', U.alice.username)
    await reactType(A.page, 'input[placeholder="密码"]', U.alice.pwd)
    await clickText(A.page, '登录', 'button')
    const fail = await waitFor(A.page, () => !!document.querySelector('.form-error'), 10000)
    const errMsg = fail ? await A.page.evaluate(() => document.querySelector('.form-error')?.textContent || '') : ''
    check('12', '旧密码登录被拒绝', fail, `error="${errMsg}"`)
    await shot(A.page, '28-login-old-password-fail')
  })

  await step('12c. 新密码登录成功', async () => {
    await reactType(A.page, 'input[placeholder="密码"]', 'Alice1234')
    await clickText(A.page, '登录', 'button')
    const ok = await waitURL(A.page, '/events', 15000)
    check('12', '新密码登录成功', ok, `url=${await A.page.evaluate(() => location.href)}`)
    await shot(A.page, '29-login-new-password-ok')
  })

  // ---------- 13. 通知铃铛 ----------
  await step('13. 通知铃铛：有通知→全部已读→清空已读', async () => {
    await A.page.goto(`${BASE}/events`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '互送礼物')
    await sleep(1200) // 等通知加载
    const badge = await A.page.evaluate(() => {
      const b = document.querySelector('.notif-badge')
      return b ? b.textContent : ''
    })
    check('13', '铃铛有未读角标', badge !== '', `badge="${badge}"`)
    await A.page.click('.notif-bell')
    await waitText(A.page, '通知')
    const items = await A.page.evaluate(() => document.querySelectorAll('.notif-item').length)
    check('13', '通知面板有通知条目', items > 0, `items=${items}`)
    await shot(A.page, '30-notification-bell')

    await clickText(A.page, '全部已读')
    const badgeGone = await waitFor(A.page, () => !document.querySelector('.notif-badge'), 10000)
    check('13', '全部已读后角标消失', badgeGone)
    await shot(A.page, '31-notification-all-read')

    await clickText(A.page, '清空已读')
    const empty = await waitText(A.page, '暂无通知', 10000)
    check('13', '清空已读后暂无通知', empty)
    await shot(A.page, '32-notification-cleared')
  })

  // ---------- 14. 归档 → 列表消失 → 归档 tab 恢复 ----------
  await step('14a. 归档活动', async () => {
    await A.page.goto(`${BASE}/events/${eventCode}`, { waitUntil: 'networkidle2' })
    await waitText(A.page, '归档活动')
    await clickText(A.page, '归档活动')
    await waitText(A.page, '归档活动？')
    await shot(A.page, '33-archive-confirm')
    await clickText(A.page, '确认归档')
    const atEvents = await waitURL(A.page, '/events', 10000)
    check('14', '归档后回到活动列表', atEvents)
    await waitText(A.page, '互送礼物')
    await sleep(800)
    const gone = await A.page.evaluate((t) => !document.body.innerText.includes(t), EVENT_TITLE)
    check('14', '归档后从「我创建的」消失', gone)
    await shot(A.page, '34-events-mine-after-archive')
  })

  await step('14b. 归档 tab 恢复', async () => {
    await clickText(A.page, '已归档')
    const found = await waitText(A.page, EVENT_TITLE, 10000)
    check('14', '归档 tab 中可见活动', found)
    check('14', '归档 tab 标记已归档', await waitText(A.page, '已归档'))
    await shot(A.page, '35-events-archived-tab')
    await clickText(A.page, '恢复')
    const restored = await waitText(A.page, '活动已恢复', 10000)
    check('14', '恢复活动成功', restored)
    await clickText(A.page, '我创建的')
    const back = await waitText(A.page, EVENT_TITLE, 10000)
    check('14', '恢复后回到「我创建的」', back)
    await shot(A.page, '36-events-mine-restored')
  })
} finally {
  await browser.close()
}

// ---------------- 输出结果 ----------------
const summary = {
  runAt: new Date().toISOString(),
  eventCode,
  eventShortCode,
  users: U,
  totalSteps: results.length,
  passed: results.filter((r) => r.pass).length,
  failed: results.filter((r) => !r.pass).length,
  defects,
  results,
}
fs.writeFileSync(path.join(__dirname, 'e2e-results.json'), JSON.stringify(summary, null, 2))
console.log('\n=============== E2E 结果 ===============')
console.log(`通过 ${summary.passed}/${summary.totalSteps}，缺陷 ${defects.length} 个`)
for (const d of defects) {
  console.log(`  [${d.severity}] ${d.step} / ${d.name}: ${d.message}`)
}
process.exit(summary.failed > 0 ? 1 : 0)
