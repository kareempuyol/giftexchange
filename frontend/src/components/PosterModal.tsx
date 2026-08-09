import { useRef, useState } from 'react'
import { t, useLocale } from '../i18n'
import SharePoster, { PosterData, downloadPoster } from './SharePoster'
import Modal from './Modal'

/** 海报预览弹窗：内联预览 + 下载 */
export default function PosterModal({ data, onClose }: { data: PosterData | null; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [downloaded, setDownloaded] = useState(false)
  useLocale()

  if (!data) return null

  const title = data.kind === 'invite' ? t('📣 邀请海报') : t('🏆 高光海报')

  return (
    <Modal
      title={title}
      onClose={onClose}
      maxWidth={460}
    >
      <div style={{ textAlign: 'center' }}>
        <div ref={(el) => { if (el) canvasRef.current = el.querySelector('canvas') as HTMLCanvasElement }}>
          <SharePoster data={data} />
        </div>
        <div style={{ display: 'flex', gap: 12, marginTop: 16 }}>
          <button
            className="btn btn-secondary"
            style={{ width: 'auto', flex: 1 }}
            onClick={() => {
              const c = canvasRef.current
              if (c) {
                downloadPoster(c, t('{label}-{title}.png', { label: data.kind === 'invite' ? t('邀请海报') : t('高光海报'), title: data.title }))
                setDownloaded(true)
                setTimeout(() => setDownloaded(false), 2000)
              }
            }}
          >
            {downloaded ? t('✅ 已下载') : t('⬇️ 下载海报')}
          </button>
          <button className="btn btn-primary" style={{ width: 'auto', flex: 1 }} onClick={onClose}>
            {t('关闭')}
          </button>
        </div>
      </div>
    </Modal>
  )
}
