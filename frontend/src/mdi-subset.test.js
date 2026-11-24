import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

describe('MDI subset', () => {
  const css = readFileSync(resolve(process.cwd(), 'src', 'mdi-subset.css'), 'utf8')

  it('contains Vuetify internal navigation and form icons', () => {
    for (const icon of ['mdi-menu', 'mdi-menu-down', 'mdi-checkbox-marked', 'mdi-chevron-left', 'mdi-close']) {
      expect(css).toContain(`.${icon}::before`)
    }
  })
})
