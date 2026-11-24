import { describe, expect, it } from 'vitest'
import { defaultSiteTheme, normalizeSiteTheme, resolveSiteTheme } from './theme'

describe('site theme', () => {
  it('rejects invalid settings and preserves safe defaults', () => {
    const result = normalizeSiteTheme({ primary: 'red', density: 'microscopic', motionEnabled: false })
    expect(result.primary).toBe(defaultSiteTheme.primary)
    expect(result.density).toBe(defaultSiteTheme.density)
    expect(result.motionEnabled).toBe(false)
  })

  it('uses the client mode only when dark mode is enabled', () => {
    expect(resolveSiteTheme({ ...defaultSiteTheme, userMode: 'dark' }, true).dark).toBe(true)
    expect(resolveSiteTheme({ ...defaultSiteTheme, modeEnabled: false, userMode: 'dark' }, false).dark).toBe(false)
  })

  it('falls back to preset colours when custom colours are disabled', () => {
    const resolved = resolveSiteTheme({ ...defaultSiteTheme, preset: 'ocean', colorsEnabled: false }, false)
    expect(resolved.colors.primary).toBe('#17324d')
    expect(resolved.colors.background).toBe('#f3f7f6')
  })
})
