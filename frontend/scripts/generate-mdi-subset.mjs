import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptPath = fileURLToPath(import.meta.url)
const root = resolve(dirname(scriptPath), '..')
const src = join(root, 'src')
const sourceCss = readFileSync(join(root, 'node_modules', '@mdi', 'font', 'css', 'materialdesignicons.css'), 'utf8')
const vuetifyAliases = readFileSync(join(root, 'node_modules', 'vuetify', 'lib', 'iconsets', 'mdi.js'), 'utf8')
const files = []

function walk(folder) {
  for (const name of readdirSync(folder)) {
    const path = join(folder, name)
    if (statSync(path).isDirectory()) walk(path)
    else if (/\.(vue|js|ts)$/.test(name) && !name.endsWith('.test.js')) files.push(path)
  }
}

walk(src)
const icons = new Set()
for (const file of files) {
  const content = readFileSync(file, 'utf8')
  for (const match of content.matchAll(/mdi-[a-z0-9-]+/g)) icons.add(match[0])
}
// Vuetify uses these icons internally (menu button, selects, checkboxes,
// pagination, validation, etc.), so they do not necessarily appear in templates.
for (const match of vuetifyAliases.matchAll(/mdi-[a-z0-9-]+/g)) icons.add(match[0])
icons.delete('mdi-subset')

const rules = []
for (const icon of [...icons].sort()) {
  const escaped = icon.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = sourceCss.match(new RegExp(`\\.${escaped}::before\\s*\\{[^}]+\\}`))
  if (!match) throw new Error(`Regra MDI não encontrada: ${icon}`)
  rules.push(match[0])
}

const sourceLabel = relative(root, scriptPath).replaceAll('\\', '/')
const css = `/* Gerado automaticamente por ${sourceLabel}. */
@font-face{font-family:"Material Design Icons";src:url("../node_modules/@mdi/font/fonts/materialdesignicons-webfont.woff2?v=7.4.47") format("woff2");font-weight:normal;font-style:normal;font-display:swap}
.mdi:before,.mdi-set{display:inline-block;font:normal normal normal 24px/1 "Material Design Icons";font-size:inherit;text-rendering:auto;line-height:inherit;-webkit-font-smoothing:antialiased;-moz-osx-font-smoothing:grayscale}
${rules.join('\n')}
`
writeFileSync(join(src, 'mdi-subset.css'), css)
console.log(`Ícones MDI incluídos: ${icons.size}`)
