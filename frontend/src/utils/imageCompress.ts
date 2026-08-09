/**
 * 上传前图片压缩（性能轮）：长边 >1600 降采样；JPEG/WebP 再编码 quality 0.8。
 *
 * - GIF 跳过（canvas 会丢动画）；≤256KB 的小图跳过（重编码无收益）。
 * - PNG 仅在实际降采样时重编码（保持 alpha；同尺寸重编码常变大）。
 * - JPEG/WebP 重编码后文件名扩展名同步改写（.jpg）：后端 /api/upload
 *   按「扩展名 + content-type + 魔数」三重校验，JPEG 内容必须配 .jpg。
 * - 压缩结果不小于原文件时回退原文件；解码失败也回退（由后端报错兜底）。
 *
 * 解码主路径 createImageBitmap（线程外解码 + EXIF from-image），Safari 12–14
 * 无该 API 时回退 Image + objectURL（同样应用 EXIF 方向）。
 */

const MAX_EDGE = 1600
const JPEG_QUALITY = 0.8
const MIN_BYTES = 256 * 1024

/** 回退路径：Image + objectURL（旧浏览器 createImageBitmap 不可用时） */
function loadImage(file: File): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const img = new Image()
    img.onload = () => {
      // onload 即解码完成，此时可安全 revoke（drawImage 用已解码位图）
      URL.revokeObjectURL(url)
      resolve(img)
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image decode failed'))
    }
    img.src = url
  })
}

async function decodeImage(file: File): Promise<HTMLImageElement | ImageBitmap | null> {
  if (typeof createImageBitmap === 'function') {
    try {
      return await createImageBitmap(file, { imageOrientation: 'from-image' })
    } catch {
      /* 旧实现不支持 options / 解码失败 → Image 回退 */
    }
  }
  return loadImage(file).catch(() => null)
}

export async function compressImage(file: File): Promise<File> {
  if (file.type === 'image/gif' || file.size < MIN_BYTES) return file

  const source = await decodeImage(file)
  if (!source) return file

  const sw = source instanceof ImageBitmap ? source.width : source.naturalWidth
  const sh = source instanceof ImageBitmap ? source.height : source.naturalHeight
  const scale = Math.min(1, MAX_EDGE / Math.max(sw, sh))
  const w = Math.max(1, Math.round(sw * scale))
  const h = Math.max(1, Math.round(sh * scale))

  // PNG 且未降采样：重编码无收益（可能变大），直接保留原文件
  if (scale >= 1 && file.type === 'image/png') {
    if (source instanceof ImageBitmap) source.close()
    return file
  }

  const canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  const ctx = canvas.getContext('2d')
  if (!ctx) {
    if (source instanceof ImageBitmap) source.close()
    return file
  }

  ctx.drawImage(source, 0, 0, w, h)
  // 注意：必须先 drawImage 再 close——绘制已关闭的 ImageBitmap 会抛
  // InvalidStateError（DOMException，非 ApiError → 被上传 catch 误报为通用失败）
  if (source instanceof ImageBitmap) source.close()

  const mime = file.type === 'image/png' ? 'image/png' : file.type === 'image/webp' ? 'image/webp' : 'image/jpeg'
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, mime, file.type === 'image/png' ? undefined : JPEG_QUALITY)
  )
  if (!blob || blob.size >= file.size) return file

  // 后端按文件名扩展名 + content-type + 魔数三重校验：JPEG 内容必须配 .jpg
  const name = mime === 'image/jpeg' ? file.name.replace(/\.\w+$/, '') + '.jpg' : file.name
  return new File([blob], name, { type: mime })
}
