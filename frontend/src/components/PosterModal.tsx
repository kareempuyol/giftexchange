import { useRef, useState } from 'react'
import SharePoster, { PosterData, downloadPoster } from './SharePoster'

/** 海报预览弹窗：内联预览 + 下载 */
export default function PosterModal({ data, onClose }: { data: PosterData | null; onClose: () => void }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [downloaded, setDownloaded] = useState(false)

  if (!data) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" style={{ maxWidth: 460, textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
        <h3 style={{ marginBottom: 12 }}>
          {data.kind === 'invite' ? '📣 邀请海报' : '🏆 高光海报'}
        </h3>
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
                downloadPoster(c, `${data.kind === 'invite' ? '邀请海报' : '高光海报'}-${data.title}.png`)
                setDownloaded(true)
                setTimeout(() => setDownloaded(false), 2000)
              }
            }}
          >
            {downloaded ? '✅ 已下载' : '⬇️ 下载海报'}
          </button>
          <button className="btn btn-primary" style={{ width: 'auto', flex: 1 }} onClick={onClose}>
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
