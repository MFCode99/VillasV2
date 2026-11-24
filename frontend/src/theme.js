const lightColors = {
  primary: '#17243d', secondary: '#b58c42', accent: '#5271a5', background: '#f7f5ef', surface: '#fffdf8'
}

const darkColors = {
  darkPrimary: '#29466f', darkSecondary: '#d2ad62', darkAccent: '#7394c1', darkBackground: '#0f1726', darkSurface: '#172236'
}

export const defaultSiteTheme = Object.freeze({
  preset: 'classic', adminCanView: false,
  modeEnabled: true, mode: 'light',
  colorsEnabled: true,
  densityEnabled: true, density: 'comfortable',
  cornersEnabled: true, corners: 'soft',
  shadowsEnabled: true, shadows: 'subtle',
  textSizeEnabled: true, textSize: 'normal',
  contentWidthEnabled: true, contentWidth: 'standard',
  motionEnabled: true, motion: 'normal',
  contrastEnabled: true, contrast: 'standard',
  tableStyleEnabled: true, tableStyle: 'clean',
  ...lightColors, ...darkColors
})

export const siteThemePresets = Object.freeze([
  { key: 'classic', name: 'Clássico', description: 'Azul-marinho, dourado e branco-pastel.', colors: { ...lightColors, ...darkColors } },
  {
    key: 'ocean', name: 'Oceano', description: 'Azul profundo com apontamentos verde-água.',
    colors: { primary: '#17324d', secondary: '#4f9b91', accent: '#4c78a8', background: '#f3f7f6', surface: '#fcfefd', darkPrimary: '#28557a', darkSecondary: '#65b7ad', darkAccent: '#79a4d0', darkBackground: '#0d1923', darkSurface: '#152735' }
  },
  {
    key: 'olive', name: 'Oliveira', description: 'Verde elegante com tons quentes e naturais.',
    colors: { primary: '#30453a', secondary: '#a78745', accent: '#6b806f', background: '#f5f4ed', surface: '#fffdf7', darkPrimary: '#3d604e', darkSecondary: '#c6a45e', darkAccent: '#8ca493', darkBackground: '#111a16', darkSurface: '#1b2921' }
  },
  {
    key: 'terracotta', name: 'Terracota', description: 'Quente, sóbrio e distinto sem perder contraste.',
    colors: { primary: '#4a2d2a', secondary: '#c47755', accent: '#8a6256', background: '#f8f2ed', surface: '#fffaf6', darkPrimary: '#684039', darkSecondary: '#df916e', darkAccent: '#b48170', darkBackground: '#1b1211', darkSurface: '#2b1d1a' }
  }
])

const colorPattern = /^#[0-9a-f]{6}$/i
const colorKeys = ['primary', 'secondary', 'accent', 'background', 'surface', 'darkPrimary', 'darkSecondary', 'darkAccent', 'darkBackground', 'darkSurface']
const booleanKeys = ['adminCanView', 'modeEnabled', 'colorsEnabled', 'densityEnabled', 'cornersEnabled', 'shadowsEnabled', 'textSizeEnabled', 'contentWidthEnabled', 'motionEnabled', 'contrastEnabled', 'tableStyleEnabled']
const allowedValues = {
  mode: ['light', 'dark', 'system'], density: ['compact', 'comfortable', 'spacious'],
  corners: ['square', 'soft', 'rounded'], shadows: ['none', 'subtle', 'normal'], textSize: ['small', 'normal', 'large'],
  contentWidth: ['focused', 'standard', 'wide'], motion: ['none', 'subtle', 'normal'], contrast: ['standard', 'high'], tableStyle: ['clean', 'lines', 'striped']
}

export function normalizeSiteTheme(value = {}) {
  const normalized = { ...defaultSiteTheme }
  if (typeof value.preset === 'string' && value.preset.trim()) normalized.preset = value.preset.trim().toLowerCase()
  for (const key of booleanKeys) if (typeof value[key] === 'boolean') normalized[key] = value[key]
  for (const [key, allowed] of Object.entries(allowedValues)) if (allowed.includes(value[key])) normalized[key] = value[key]
  for (const key of colorKeys) if (colorPattern.test(String(value[key] || ''))) normalized[key] = String(value[key]).toLowerCase()
  return normalized
}

function contrastText(hex) {
  const channels = [1, 3, 5].map(index => parseInt(hex.slice(index, index + 2), 16) / 255)
  const luminance = channels.map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
    .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0)
  return luminance > .46 ? '#17243d' : '#ffffff'
}

function prefersDark() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
}

export function resolveSiteTheme(value, forcedDark = null) {
  const config = normalizeSiteTheme(value)
  const requestedMode = ['light', 'dark', 'system'].includes(value?.userMode) ? value.userMode : 'light'
  const selectedMode = config.modeEnabled ? requestedMode : 'light'
  const dark = forcedDark ?? (selectedMode === 'dark' || (selectedMode === 'system' && prefersDark()))
  const preset = siteThemePresets.find(item => item.key === config.preset) || siteThemePresets[0]
  const source = config.colorsEnabled ? config : { ...config, ...preset.colors }
  const colors = dark
    ? { primary: source.darkPrimary, secondary: source.darkSecondary, accent: source.darkAccent, background: source.darkBackground, surface: source.darkSurface }
    : { primary: source.primary, secondary: source.secondary, accent: source.accent, background: source.background, surface: source.surface }
  return {
    config, dark, colors,
    density: config.densityEnabled ? config.density : 'comfortable',
    corners: config.cornersEnabled ? config.corners : 'soft',
    shadows: config.shadowsEnabled ? config.shadows : 'subtle',
    textSize: config.textSizeEnabled ? config.textSize : 'normal',
    contentWidth: config.contentWidthEnabled ? config.contentWidth : 'standard',
    motion: config.motionEnabled ? config.motion : 'normal',
    contrast: config.contrastEnabled ? config.contrast : 'standard',
    tableStyle: config.tableStyleEnabled ? config.tableStyle : 'clean'
  }
}

let activeTheme = null
let activeValue = null
let mediaListenerReady = false

function bindSystemThemeListener() {
  if (mediaListenerReady || typeof window === 'undefined' || !window.matchMedia) return
  mediaListenerReady = true
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', () => {
    if (activeTheme && activeValue?.modeEnabled && activeValue.userMode === 'system') applySiteTheme(activeTheme, activeValue)
  })
}

export function applySiteTheme(theme, value) {
  const resolved = resolveSiteTheme(value)
  const { config, colors, dark, density, corners, shadows, textSize, contentWidth, motion, contrast, tableStyle } = resolved
  activeTheme = theme
  activeValue = { ...config, userMode: value?.userMode || 'light' }
  bindSystemThemeListener()
  const current = theme.themes.value.villasLight || { dark: false, colors: {} }
  theme.themes.value.villasLight = {
    ...current,
    dark,
    colors: {
      ...current.colors, ...colors,
      'on-primary': contrastText(colors.primary), 'on-secondary': contrastText(colors.secondary),
      'on-background': contrastText(colors.background), 'on-surface': contrastText(colors.surface)
    }
  }
  const root = document.documentElement
  root.dataset.siteMode = dark ? 'dark' : 'light'
  root.dataset.siteDensity = density
  root.dataset.siteCorners = corners
  root.dataset.siteShadows = shadows
  root.dataset.siteText = textSize
  root.dataset.siteWidth = contentWidth
  root.dataset.siteMotion = motion
  root.dataset.siteContrast = contrast
  root.dataset.siteTable = tableStyle
  root.style.backgroundColor = colors.background
  document.body.style.backgroundColor = colors.background
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', colors.primary)
  return config
}
