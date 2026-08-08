#!/usr/bin/env node
// R9 送礼状态机 — 进度条 UI 截图
// 1) API 造数：新 3 人活动 → 抽签(purchase) → 发货(shipped)
// 2) puppeteer 截图：purchase / shipped(桌面+375px) / posted(复用 EM3NNG)
import http from 'node:http'
import { mkdirSync } from 'node:fs'
import puppeteer from 'puppeteer-core'

const BASE = { host: '127.0.0.1', port: 8080 }
const OUT = process.env.HOME + '/giftexchange/ui-shots/r9'
mkdirSync(OUT, { recursive: true })
const TS = String(Date.now()).slice(-6)

function req(method, path, body, token) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : null
    const r = http.request(
      { ...BASE, method, path, headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: 'Bearer ' + token } : {}) } },
      (res) => {
        let raw = ''
        res.on('data', (c) => (raw += c))
        res.on('end', () => resolve({ status: res.statusCode, json: JSON.parse(raw || '{}') }))
      }
    )
    r.on('error', reject)
    if (data) r.write(data)
    r.end()
  })
}

async function main() {
  // ---- API 造数 ----
  const login = await req('POST', '/api/auth/login', { username: 'verify_user', password: 'Verify123' })
  const orgToken = login.json.data.token
  const mkUser = async (n) => {
    const u = `r9shot_${n}_${TS}`
    await req('POST', '/api/auth/register', { username: u, email: `${u}@t.com`, password: 'Pass123!' })
    const l = await req('POST', '/api/auth/login', { username: u, password: 'Pass123!' })
    return { name: u, token: l.json.data.token }
  }
  const p2 = await mkUser('a')
  const p3 = await mkUser('b')
  const ev = await req('POST', '/api/events', { title: `状态机截图${TS}`, note: 'r9', budgetMin: 50, budgetMax: 200, drawDate: '2026-12-25T20:00:00.000Z', signUpDeadline: '2026-12-24T20:00:00.000Z' }, orgToken)
  const code = ev.json.data.shortCode
  for (const t of [orgToken, p2.token, p3.token]) await req('POST', `/api/events/${code}/join`, {}, t)
  await req('POST', `/api/events/${code}/draw`, {}, orgToken)
  const mm1 = await req('GET', `/api/events/${code}/my-match`, {}, orgToken)
  console.log('state#1(purchase):', mm1.json.data.shipmentState, '| event', code)
  const matchId = mm1.json.data.matchId
  await req('PUT', `/api/events/${code}/shipment`, { matchId, carrier: '顺丰', trackingNumber: `SF${TS}`, status: 'shipped' }, orgToken)
  const mm2 = await req('GET', `/api/events/${code}/my-match`, {}, orgToken)
  console.log('state#2(shipped):', mm2.json.data.shipmentState)

  // ---- 截图 ----
  const browser = await puppeteer.launch({
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    headless: 'new',
    args: ['--no-sandbox'],
  })
  const shoot = async (file, url, token, viewport, label) => {
    const page = await browser.newPage()
    await page.setViewport(viewport)
    await page.evaluateOnNewDocument((t) => localStorage.setItem('gift_token', t), token)
    await page.goto(url, { waitUntil: 'networkidle0', timeout: 30000 })
    await page.waitForSelector('.ship-progress', { timeout: 15000 })
    await page.evaluate(() => document.querySelector('.ship-progress').scrollIntoView({ block: 'center' }))
    await new Promise((r) => setTimeout(r, 400))
    await page.screenshot({ path: `${OUT}/${file}` })
    await page.close()
    console.log('shot:', file, `(${label})`)
  }
  const origin = 'http://127.0.0.1:8080'
  await shoot('01-purchase-desktop.png', `${origin}/events/${code}`, orgToken, { width: 1280, height: 900 }, 'purchase')
  await shoot('02-shipped-desktop.png', `${origin}/events/${code}`, orgToken, { width: 1280, height: 900 }, 'shipped')
  await shoot('03-shipped-mobile-375.png', `${origin}/events/${code}`, orgToken, { width: 375, height: 812, isMobile: true }, 'shipped@375px')
  await shoot('04-posted-desktop.png', `${origin}/events/EM3NNG`, orgToken, { width: 1280, height: 900 }, 'posted(EM3NNG)')
  await browser.close()
  console.log('DONE →', OUT)
}

main().catch((e) => { console.error(e); process.exit(1) })
