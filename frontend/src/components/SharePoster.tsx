import { useEffect, useRef } from 'react'
import { t, useLocale } from '../i18n'
import QRCode from 'qrcode'
import { primitive } from '../tokens'

const BRAND = primitive.coral[500]
const WARM_700 = primitive.warm[700]
const WARM_500 = primitive.warm[500]
const WARM_800 = primitive.warm[800]
const WARM_300 = primitive.warm[300]
const WHITE = primitive.white

export interface PosterData {
  kind: 'invite' | 'highlight'
  title: string
  note?: string
  budget?: number
  participantCount?: number
  shortCode?: string
  coverImage?: string
  totalPosted?: number
  totalStars?: number
}

const W = 750
const H = 1000

/** 生成分享海报（Canvas 2D 绘制，3:4 社交比例，可下载 PNG） */
export default function SharePoster({ data }: { data: PosterData }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const locale = useLocale()

  useEffect(() => {
    const tagline = data.kind === 'invite' ? t('朋友间的心意交换') : t('一次温暖的心意交换')
    const cta = data.kind === 'invite' ? t('等你加入，一起交换心意') : t('期待下一次心意交换')
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    // 背景：暖色渐变
    const grad = ctx.createLinearGradient(0, 0, 0, H)
    grad.addColorStop(0, BRAND)
    grad.addColorStop(1, primitive.coral[100])
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, W, H)

    // 装饰圆
    ctx.fillStyle = `${WHITE}1F`
    ctx.beginPath(); ctx.arc(660, 120, 90, 0, Math.PI * 2); ctx.fill()
    ctx.beginPath(); ctx.arc(80, 880, 70, 0, Math.PI * 2); ctx.fill()
    ctx.beginPath(); ctx.arc(700, 800, 40, 0, Math.PI * 2); ctx.fill()

    // 品牌
    ctx.fillStyle = WHITE
    ctx.font = 'bold 34px "PingFang SC", sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText(t('🎁 互送礼物'), W / 2, 90)
    ctx.font = '20px "PingFang SC", sans-serif'
    ctx.fillStyle = `${WHITE}D9`
    ctx.fillText(tagline, W / 2, 130)

    // 白色卡片
    ctx.fillStyle = WHITE
    roundRect(ctx, 60, 180, W - 120, H - 380, 28)
    ctx.fill()

    // 标题
    ctx.fillStyle = WARM_700
    ctx.font = 'bold 44px "PingFang SC", sans-serif'
    wrapText(ctx, data.title, W / 2, 260, W - 180, 56)

    // 封面图（如有）——加载后重绘，先画占位
    if (data.coverImage) {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      img.onload = () => {
        // 重新绘制封面区域
        ctx.save()
        ctx.fillStyle = WHITE
        roundRect(ctx, 60, 180, W - 120, H - 380, 28)
        ctx.fill()
        ctx.restore()
        redrawCard()
        const ih = 240
        const iw = (W - 200) * (img.width / img.height) / (240 / (W - 200)) * 0.6
        ctx.save()
        roundRect(ctx, 100, 300, W - 200, ih, 16)
        ctx.clip()
        ctx.drawImage(img, 100, 300, W - 200, ih)
        ctx.restore()
        redrawTexts()
      }
      img.src = data.coverImage
    } else {
      redrawTexts()
    }

    function redrawCard() {
      ctx.fillStyle = WHITE
      roundRect(ctx, 60, 180, W - 120, H - 380, 28)
      ctx.fill()
    }

    function redrawTexts() {
      // 标题
      ctx.fillStyle = WARM_700
      ctx.font = 'bold 44px "PingFang SC", sans-serif'
      wrapText(ctx, data.title, W / 2, 260, W - 180, 56)

      // 说明（截断）
      if (data.note) {
        ctx.fillStyle = WARM_500
        ctx.font = '26px "PingFang SC", sans-serif'
        const note = data.note.length > 60 ? data.note.slice(0, 60) + '…' : data.note
        ctx.fillText(note, W / 2, 360)
      }

      // 信息行
      ctx.fillStyle = WARM_700
      ctx.font = 'bold 32px "PingFang SC", sans-serif'
      const infoParts = []
      if (data.budget) infoParts.push(t('预算 ¥{budget}', { budget: data.budget }))
      if (data.participantCount !== undefined) infoParts.push(t('{participantCount} 人参与', { participantCount: data.participantCount }))
      if (data.kind === 'highlight' && data.totalPosted !== undefined) infoParts.push(t('{totalPosted} 份心意', { totalPosted: data.totalPosted }))
      if (data.kind === 'highlight' && data.totalStars !== undefined) infoParts.push(`⭐ ${data.totalStars}`)
      ctx.fillText(infoParts.join('  ·  '), W / 2, 440)

      if (data.kind === 'invite') {
        // 邀请码
        ctx.fillStyle = BRAND
        ctx.font = 'bold 40px "PingFang SC", sans-serif'
        ctx.fillText(t('邀请码 {shortCode}', { shortCode: data.shortCode || '' }), W / 2, 540)

        // 真实二维码：指向邀请落地页（游客可访问 /events/<shortCode>）
        const qx = W / 2 - 70, qy = 590, qs = 140
        try {          const inviteUrl =
            typeof window !== 'undefined'
              ? `${window.location.origin}/events/${data.shortCode || ''}`
              : `https://gift.local/events/${data.shortCode || ''}`
          const qr = QRCode.create(inviteUrl, { errorCorrectionLevel: 'M' })
          const n = qr.modules.size
          const cell = qs / n
          ctx.fillStyle = WHITE
          ctx.fillRect(qx, qy, qs, qs)
          ctx.fillStyle = WARM_800
          for (let r = 0; r < n; r++) {
            for (let c = 0; c < n; c++) {
              if (qr.modules.data[r * n + c]) {
                ctx.fillRect(qx + c * cell, qy + r * cell, Math.ceil(cell) + 0.5, Math.ceil(cell) + 0.5)
              }
            }
          }
        } catch {
          // 二维码生成失败兜底：画灰色占位框（不阻断海报）
          ctx.fillStyle = WARM_300
          ctx.fillRect(qx, qy, qs, qs)
          ctx.fillStyle = WARM_500
          ctx.font = '20px "PingFang SC", sans-serif'
          ctx.fillText(t('二维码生成失败'), W / 2, qy + qs / 2 + 7)
        }

        ctx.fillStyle = WARM_500
        ctx.font = '22px "PingFang SC", sans-serif'
        ctx.fillText(t('扫码或输入邀请码加入'), W / 2, 800)
      } else {
        ctx.fillStyle = BRAND
        ctx.font = 'bold 40px "PingFang SC", sans-serif'
        ctx.fillText(t('我们完成了一次礼物交换 🎉'), W / 2, 560)
        ctx.fillStyle = WARM_500
        ctx.font = '24px "PingFang SC", sans-serif'
        ctx.fillText(t('感谢每一位参与者'), W / 2, 640)
      }

      // 底部 CTA
      ctx.fillStyle = BRAND
      ctx.font = 'bold 28px "PingFang SC", sans-serif'
      ctx.fillText(cta, W / 2, H - 130)
    }
  }, [data, locale])

  return <canvas ref={canvasRef} width={W} height={H} style={{ width: '100%', maxWidth: 420, borderRadius: 16 }} />
}

/** 圆角矩形路径 */
function roundRect(ctx: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

/** 中文换行绘制 */
function wrapText(ctx: CanvasRenderingContext2D, text: string, cx: number, y: number, maxW: number, lineH: number) {
  const chars = text.split('')
  let line = ''
  let lineY = y
  for (const ch of chars) {
    const test = line + ch
    if (ctx.measureText(test).width > maxW && line) {
      ctx.fillText(line, cx, lineY)
      line = ch
      lineY += lineH
    } else {
      line = test
    }
  }
  if (line) ctx.fillText(line, cx, lineY)
}

/** 导出海报为 PNG 下载 */
export function downloadPoster(canvas: HTMLCanvasElement, filename: string) {
  const url = canvas.toDataURL('image/png')
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
}
