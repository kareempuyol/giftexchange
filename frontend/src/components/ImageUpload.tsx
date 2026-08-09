import { useRef, useState } from 'react'
import { t, useLocale } from '../i18n'
import { api, ApiError, UploadResult } from '../api/client'
import { compressImage } from '../utils/imageCompress'
import SafeImage from './SafeImage'

interface ImageUploadProps {
  /** 当前已上传的图片 URL（相对路径，如 /uploads/xxx.png） */
  value: string
  /** 上传成功回调，返回相对 URL */
  onChange: (url: string) => void
  label?: string
  hint?: string
}

/**
 * 图片上传组件（阶段二G：先传后引用）
 * 选择文件 → FormData POST /api/upload → 预览 → 回调返回相对 URL
 * 未来小程序迁移：本组件替换为 wx.chooseImage + wx.uploadFile 即可，业务字段不变
 */
export default function ImageUpload({ value, onChange, label = t('上传图片'), hint }: ImageUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  useLocale()

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!/^image\/(png|jpe?g|gif|webp)$/i.test(file.type)) {
      setError(t('仅支持 png / jpg / jpeg / gif / webp 图片'))
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      setError(t('图片不能超过 5MB'))
      return
    }
    setUploading(true)
    setError('')
    try {
      // 上传前压缩（长边 >1600 降采样、JPEG/WebP 0.8）：传输 + 存储双收益。
      // GIF 与 ≤256KB 小图原样直传；JPEG 内容会把文件名改成 .jpg（后端三重校验）。
      const toUpload = await compressImage(file)
      const result = await api.upload<UploadResult>('/upload', toUpload)
      onChange(result.url)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('上传失败，请稍后重试'))
    } finally {
      setUploading(false)
      // 允许再次选择同一文件
      e.target.value = ''
    }
  }

  return (
    <div className="iu-wrap">
      <input
        ref={inputRef}
        type="file"
        accept="image/png,image/jpeg,image/gif,image/webp"
        onChange={handleFile}
        className="iu-input"
      />
      {value && <SafeImage className="iu-preview" src={value} alt={t('图片预览')} />}
      <button
        type="button"
        className="btn btn-secondary btn-sm"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
      >
        {uploading ? t('上传中…') : value ? t('更换图片') : label}
      </button>
      {error && <div className="form-error iu-error">{error}</div>}
      {hint && <div className="form-hint">{hint}</div>}
    </div>
  )
}
