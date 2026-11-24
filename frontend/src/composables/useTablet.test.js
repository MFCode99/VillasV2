import { describe, expect, it } from 'vitest'
import { classifyDevice } from './useTablet'

describe('classifyDevice', () => {
  it('recognizes tablet portrait and landscape when touch is available', () => {
    expect(classifyDevice(768, 1024, true)).toMatchObject({ tablet: true, portrait: true })
    expect(classifyDevice(1180, 820, true)).toMatchObject({ tablet: true, portrait: false })
  })

  it('does not classify desktop or phone as tablet', () => {
    expect(classifyDevice(1180, 820, false).tablet).toBe(false)
    expect(classifyDevice(390, 844, true).tablet).toBe(false)
  })
})
