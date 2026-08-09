/**
 * giftexchange Design Tokens
 * ===========================
 * 分层结构：原始值 (primitive) → 语义 (semantic) → 组件 (component)
 *
 * 修改原则：
 * - 调整品牌色/圆角等基础值 → 只改 primitive 层
 * - 业务语义（如"危险操作"用哪个色）→ 只改 semantic 层
 * - 组件样式引用 semantic 层，绝不直接引用 primitive
 *
 * 使用方式：
 * - CSS：var(--gift-*)，见 tokens.css
 * - TS：import { colors, radii, spacing } from './tokens'
 * - 两处来源唯一：本文件生成 CSS 变量 + TS 常量
 */

// ============================================================
// 1. 原始值层 (Primitive) — 来自现有 UI 设计语言，保持延续
// ============================================================
export const primitive = {
  // 品牌色系（暖橙红，源自现有 --gift-primary）
  coral: {
    50: '#FFF1EE',
    100: '#FFE0D9',
    200: '#FFC4B8',
    300: '#FBA492',
    400: '#F57F68',
    // 500 主品牌色：#E8553D → #C93B24（WCAG AA 4.5:1：白字 5.08、浅底文字 4.61）
    500: '#C93B24',
    600: '#D44028',
    700: '#B5341F',
    800: '#8F2A1A',
    900: '#6B2216',
  },
  // 暖中性色（米白/奶油/深褐）
  warm: {
    50: '#FFFAF5', // 页面背景
    100: '#F7F3ED', // 悬停背景
    200: '#F0EBE4', // 骨架屏
    300: '#E8DFD5', // 边框
    400: '#D5C9BB', // 分割线
    500: '#7A6B5D', // 次级文字
    600: '#5C5046', // 强调文字
    700: '#3D2E2A', // 主文字
    800: '#2C211E', // 深色标题
    900: '#1A1311', // 最深
  },
  // 功能色
  gold: '#A97A00',   // 金色点缀（徽章/高亮）— 调深保证图标 3:1
  success: '#1B7A43', // 成功
  warning: '#8A5E00', // 警告
  error: '#C22F2F',  // 错误/危险
  info: '#2F5F8F',   // 信息（新增，用于提示）
  white: '#FFFFFF',
  black: '#000000',
  // 透明色（用于遮罩等）
  overlay: 'rgba(26, 19, 17, 0.5)',
}

// ============================================================
// 2. 语义层 (Semantic) — 业务含义映射
// ============================================================
export const semantic = {
  color: {
    bg: primitive.warm[50],            // 页面背景
    bgMuted: primitive.warm[100],      // 弱化背景（区块）
    card: primitive.white,             // 卡片背景
    border: primitive.warm[300],       // 常规边框
    borderStrong: primitive.warm[400], // 强调边框
    textPrimary: primitive.warm[700],  // 主文字
    textSecondary: primitive.warm[500],// 次级文字
    textOnPrimary: primitive.white,    // 主色上的文字
    textDisabled: primitive.warm[400], // 禁用文字
    brand: primitive.coral[500],       // 品牌主色
    brandHover: primitive.coral[600],
    brandActive: primitive.coral[700],
    brandLight: primitive.coral[50],   // 品牌浅底
    gold: primitive.gold,
    success: primitive.success,
    successBg: '#E7F5EC',
    warning: primitive.warning,
    warningBg: '#FDF3E3',
    error: primitive.error,
    errorBg: '#FCEBEB',
    info: primitive.info,
    infoBg: '#EAF1F8',
    // 状态色文字变体：浅色主题与主色一致；暗色主题提亮（见 tokens.css）保证 AA
    successText: primitive.success,
    warningText: primitive.warning,
    errorText: primitive.error,
    infoText: primitive.info,
    overlay: primitive.overlay,
  },
  radius: {
    sm: '8px',
    md: '12px',
    card: '16px',   // 卡片
    btn: '26px',    // 按钮（胶囊）
    pill: '999px',  // 标签/徽章
  },
  shadow: {
    card: '0 2px 8px rgba(61, 46, 42, 0.06)',
    raised: '0 4px 16px rgba(61, 46, 42, 0.10)',
    modal: '0 8px 32px rgba(26, 19, 17, 0.18)',
  },
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '12px',
    lg: '16px',
    xl: '24px',
    xxl: '32px',
  },
  font: {
    family: "'Inter', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, sans-serif",
    sizeXs: '12px',
    sizeSm: '14px',
    sizeMd: '16px',
    sizeLg: '20px',
    sizeXl: '24px',
    sizeTitle: '28px',
    weightNormal: '400',
    weightMedium: '500',
    weightBold: '600',
  },
  motion: {
    fast: '0.15s',
    normal: '0.25s',
    slow: '0.4s',
    ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
  },
  control: {
    height: '52px',       // 主按钮高度（延续现有）
    heightSm: '40px',     // 次按钮
    inputHeight: '48px',  // 输入框
  },
  breakpoint: {
    mobile: '640px',
    tablet: '768px',
    desktop: '1024px',
  },
  zIndex: {
    base: 1,
    sticky: 100,
    modal: 1000,
    toast: 1100,
  },
}

// ============================================================
// 3. 导出统一访问入口
// ============================================================
export const tokens = {
  ...semantic,
  primitive,
}

export default tokens
