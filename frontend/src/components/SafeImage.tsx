import { useRef, useState } from 'react'

interface SafeImageProps extends React.ImgHTMLAttributes<HTMLImageElement> {
  /** 加载失败时占位块内显示的文字（可选；缺省为纯色块） */
  fallbackText?: string
}

/**
 * 图片加载失败兜底（稳定性）：裂图 → 占位色块，不再显示破图图标。
 * - 背景/文字色走 --gift-* token（.safe-img-fallback），不硬编码色值
 * - 失败瞬间测量原 <img> 渲染尺寸（offsetWidth/Height + borderRadius），
 *   占位块保持一致，避免布局跳动；自动高度图片测不到高度时由 CSS min-height 兜底
 * - 用法与 <img> 一致；自定义 onError 先兜底后透传
 */
export default function SafeImage({ fallbackText, onError, style, alt, ...rest }: SafeImageProps) {
  const imgRef = useRef<HTMLImageElement>(null)
  const [failed, setFailed] = useState(false)
  const [box, setBox] = useState<{ width?: number; height?: number; radius?: string }>({})

  if (failed) {
    const cssStyle = style as React.CSSProperties | undefined
    return (
      <span
        className="safe-img-fallback"
        role={alt ? undefined : 'presentation'}
        aria-label={alt}
        style={{
          ...cssStyle,
          width: box.width || cssStyle?.width,
          height: box.height || cssStyle?.height,
          borderRadius: box.radius,
        }}
      >
        {fallbackText ?? ''}
      </span>
    )
  }

  return (
    <img
      ref={imgRef}
      alt={alt}
      {...rest}
      style={style}
      onError={(e) => {
        const el = imgRef.current
        if (el && el.offsetWidth > 0) {
          setBox({
            width: el.offsetWidth,
            height: el.offsetHeight,
            radius: getComputedStyle(el).borderRadius,
          })
        }
        setFailed(true)
        onError?.(e)
      }}
    />
  )
}
