<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'
import { defaultSiteTheme, normalizeSiteTheme, resolveSiteTheme, siteThemePresets } from '../theme'

const feedback = useFeedbackStore()
const router = useRouter()
const loading = ref(true)
const saving = ref(false)
const ready = ref(false)
const canEdit = ref(false)
const previewPalette = ref('light')
const savedTheme = ref({ ...defaultSiteTheme })
const form = reactive({ ...defaultSiteTheme })
const colorPattern = /^#[0-9a-f]{6}$/i

const colorFields = [
  { light: 'primary', dark: 'darkPrimary', label: 'Cor principal', hint: 'Menu e ações principais' },
  { light: 'secondary', dark: 'darkSecondary', label: 'Cor de destaque', hint: 'Seleções e pontos de atenção' },
  { light: 'accent', dark: 'darkAccent', label: 'Cor complementar', hint: 'Elementos de apoio e gráficos' },
  { light: 'background', dark: 'darkBackground', label: 'Fundo do site', hint: 'Área geral por trás dos cartões' },
  { light: 'surface', dark: 'darkSurface', label: 'Cartões e painéis', hint: 'Superfícies com conteúdo' }
]
const densities = [
  { value: 'compact', label: 'Compacto' }, { value: 'comfortable', label: 'Normal' }, { value: 'spacious', label: 'Espaçoso' }
]
const corners = [
  { value: 'square', label: 'Retos' }, { value: 'soft', label: 'Suaves' }, { value: 'rounded', label: 'Arredondados' }
]
const shadows = [
  { value: 'none', label: 'Sem sombras' }, { value: 'subtle', label: 'Discretas' }, { value: 'normal', label: 'Normais' }
]
const textSizes = [
  { value: 'small', label: 'Pequeno' }, { value: 'normal', label: 'Normal' }, { value: 'large', label: 'Grande' }
]
const contentWidths = [{ value: 'focused', label: 'Focado' }, { value: 'standard', label: 'Normal' }, { value: 'wide', label: 'Amplo' }]
const motions = [{ value: 'none', label: 'Sem transições' }, { value: 'subtle', label: 'Discretas' }, { value: 'normal', label: 'Normais' }]
const contrasts = [{ value: 'standard', label: 'Normal' }, { value: 'high', label: 'Elevado' }]
const tableStyles = [{ value: 'clean', label: 'Limpa' }, { value: 'lines', label: 'Com linhas' }, { value: 'striped', label: 'Alternada' }]

const dirty = computed(() => JSON.stringify(normalizeSiteTheme(form)) !== JSON.stringify(savedTheme.value))
const validColors = computed(() => colorFields.every(field => colorPattern.test(form[field.light]) && colorPattern.test(form[field.dark])))
const resolvedPreview = computed(() => resolveSiteTheme(form, previewPalette.value === 'dark'))
const previewStyle = computed(() => {
  const { colors, density, corners: cornerStyle, shadows: shadowStyle, textSize, contentWidth, contrast } = resolvedPreview.value
  const radii = { square: ['5px', '5px'], soft: ['18px', '11px'], rounded: ['28px', '18px'] }[cornerStyle]
  return {
    '--p-primary': colors.primary, '--p-secondary': colors.secondary, '--p-accent': colors.accent,
    '--p-background': colors.background, '--p-surface': colors.surface,
    '--p-on-surface': previewPalette.value === 'dark' ? '#f5f7fb' : '#17243d',
    '--p-muted': previewPalette.value === 'dark' ? '#aeb8c9' : '#687387',
    '--p-card-radius': radii[0], '--p-control-radius': radii[1],
    '--p-shadow': shadowStyle === 'none' ? 'none' : shadowStyle === 'normal' ? '0 18px 42px rgba(4,12,28,.22)' : '0 8px 22px rgba(4,12,28,.10)',
    '--p-gap': density === 'compact' ? '8px' : density === 'spacious' ? '18px' : '12px',
    '--p-font': textSize === 'small' ? '.9' : textSize === 'large' ? '1.08' : '1',
    '--p-content': contentWidth === 'focused' ? '86%' : '100%',
    '--p-border': contrast === 'high' ? '24%' : '10%'
  }
})

function fieldKey(field) { return previewPalette.value === 'dark' ? field.dark : field.light }
function preview() { window.dispatchEvent(new CustomEvent('villas:theme-preview', { detail: normalizeSiteTheme(form) })) }
function choosePreset(preset) {
  if (!canEdit.value) return
  Object.assign(form, preset.colors, { preset: preset.key })
}
function syncPreset() {
  if (!ready.value) return
  const match = siteThemePresets.find(preset => colorFields.every(field => preset.colors[field.light] === form[field.light] && preset.colors[field.dark] === form[field.dark]))
  form.preset = match?.key || 'custom'
}
function normalizeField(key) {
  const value = String(form[key] || '').trim()
  if (/^[0-9a-f]{6}$/i.test(value)) form[key] = `#${value.toLowerCase()}`
  else if (colorPattern.test(value)) form[key] = value.toLowerCase()
}
function restoreDefaults() {
  if (!canEdit.value) return
  const adminCanView = form.adminCanView
  Object.assign(form, defaultSiteTheme, { adminCanView })
  feedback.show('Valores padrão repostos na pré-visualização.', 'info')
}
async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/admin/site/theme')
    const theme = normalizeSiteTheme(data.theme)
    canEdit.value = Boolean(data.canEdit)
    savedTheme.value = { ...theme }
    Object.assign(form, theme)
    previewPalette.value = theme.mode === 'dark' ? 'dark' : 'light'
    preview()
  } catch (error) {
    if (error?.response?.status === 403) return router.replace('/admin')
    feedback.show(errorMessage(error), 'error')
  }
  finally { loading.value = false; ready.value = true }
}
async function save() {
  colorFields.flatMap(field => [field.light, field.dark]).forEach(normalizeField)
  if (!validColors.value) return feedback.show('Corrija as cores: use o formato #RRGGBB.', 'warning')
  saving.value = true
  try {
    const theme = normalizeSiteTheme((await api.put('/admin/site/theme', normalizeSiteTheme(form))).data.theme)
    savedTheme.value = { ...theme }
    Object.assign(form, theme)
    preview()
    window.dispatchEvent(new CustomEvent('villas:theme-access', { detail: { adminCanView: theme.adminCanView, modeEnabled: theme.modeEnabled } }))
    feedback.show('A aparência foi aplicada a todo o portal.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}

watch(form, () => { if (ready.value && canEdit.value && validColors.value) preview() }, { deep: true })
watch(() => colorFields.flatMap(field => [form[field.light], form[field.dark]]), syncPreset)
onMounted(load)
onBeforeUnmount(() => window.dispatchEvent(new CustomEvent('villas:theme-preview', { detail: savedTheme.value })))
</script>

<template>
  <div class="page appearance-page">
    <div class="page-head">
      <div>
        <div class="text-overline text-secondary font-weight-bold">{{ canEdit ? 'Exclusivo Developer' : 'Consulta de administrador' }}</div>
        <h1>Aparência do site</h1>
        <p>{{ canEdit ? 'Controle o visual do portal e quais opções ficam ativas.' : 'Consulte a configuração definida pelo Developer.' }}</p>
      </div>
      <div class="head-actions">
        <v-btn v-if="canEdit" variant="text" prepend-icon="mdi-restore" @click="restoreDefaults">Repor padrão</v-btn>
        <v-btn v-if="canEdit" color="primary" prepend-icon="mdi-content-save-outline" :disabled="!dirty || !validColors" :loading="saving" @click="save">Guardar aparência</v-btn>
        <v-chip v-else prepend-icon="mdi-eye-outline" color="info" variant="tonal">Só de leitura</v-chip>
      </div>
    </div>
    <v-progress-linear v-if="loading" indeterminate color="secondary" class="mb-5" />

    <template v-else>
      <v-card v-if="canEdit" class="soft-card access-card mb-6">
        <div><v-icon color="secondary">mdi-shield-account-outline</v-icon><div><b>Consulta para administradores</b><p>Quando ativo, os administradores veem esta página e a configuração, mas não podem alterar nada.</p></div></div>
        <v-switch v-model="form.adminCanView" color="secondary" hide-details inset aria-label="Permitir consulta aos administradores" />
      </v-card>

      <div class="appearance-layout">
        <div class="settings-column">
          <v-card class="soft-card setting-card">
            <div class="setting-head mb-0"><div class="setting-icon"><v-icon>mdi-theme-light-dark</v-icon></div><div><h2>Modo escuro para utilizadores</h2><p>Disponibiliza Claro, Escuro e Automático no menu do nome de cada utilizador. A escolha é individual.</p></div><v-switch v-model="form.modeEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div>
          </v-card>

          <v-card class="soft-card setting-card color-card">
            <div class="setting-head"><div class="setting-icon"><v-icon>mdi-palette-outline</v-icon></div><div><h2>Cores e combinações</h2><p>Escolha uma base pronta ou ajuste cada cor.</p></div><v-switch v-model="form.colorsEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div>
            <div class="preset-grid" :class="{ disabled: !form.colorsEnabled }">
              <button v-for="preset in siteThemePresets" :key="preset.key" type="button" class="preset-card" :class="{ active: form.preset === preset.key }" :disabled="!canEdit || !form.colorsEnabled" :aria-pressed="form.preset === preset.key" @click="choosePreset(preset)">
                <span class="preset-colors"><i v-for="key in ['primary', 'secondary', 'accent', 'background']" :key="key" :style="{ background: preset.colors[key] }" /></span>
                <span><b>{{ preset.name }}</b><small>{{ preset.description }}</small></span>
                <v-icon>{{ form.preset === preset.key ? 'mdi-check-circle' : 'mdi-chevron-right' }}</v-icon>
              </button>
            </div>
            <div class="palette-toolbar">
              <span>Cores para o modo</span>
              <v-btn-toggle v-model="previewPalette" mandatory density="compact" variant="outlined">
                <v-btn value="light" prepend-icon="mdi-white-balance-sunny">Claro</v-btn><v-btn value="dark" prepend-icon="mdi-weather-night">Escuro</v-btn>
              </v-btn-toggle>
            </div>
            <div class="color-list" :class="{ disabled: !form.colorsEnabled }">
              <div v-for="field in colorFields" :key="field.light" class="color-row">
                <label :for="`theme-${fieldKey(field)}`"><b>{{ field.label }}</b><small>{{ field.hint }}</small></label>
                <div class="color-input-wrap">
                  <input :id="`theme-${fieldKey(field)}`" v-model="form[fieldKey(field)]" type="color" :disabled="!canEdit || !form.colorsEnabled" :aria-label="field.label" />
                  <v-text-field v-model="form[fieldKey(field)]" hide-details density="compact" maxlength="7" :disabled="!canEdit || !form.colorsEnabled" :error="!colorPattern.test(form[fieldKey(field)])" aria-label="Código hexadecimal" @blur="normalizeField(fieldKey(field))" />
                </div>
              </div>
            </div>
          </v-card>

          <div class="compact-settings">
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-format-line-spacing</v-icon></div><div><h2>Espaçamento</h2><p>Densidade dos conteúdos.</p></div><v-switch v-model="form.densityEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.density" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.densityEnabled"><v-btn v-for="item in densities" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-rounded-corner</v-icon></div><div><h2>Cantos</h2><p>Forma de cartões e controlos.</p></div><v-switch v-model="form.cornersEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.corners" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.cornersEnabled"><v-btn v-for="item in corners" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-box-shadow</v-icon></div><div><h2>Sombras</h2><p>Profundidade dos painéis.</p></div><v-switch v-model="form.shadowsEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.shadows" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.shadowsEnabled"><v-btn v-for="item in shadows" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-format-size</v-icon></div><div><h2>Tamanho do texto</h2><p>Escala geral de leitura.</p></div><v-switch v-model="form.textSizeEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.textSize" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.textSizeEnabled"><v-btn v-for="item in textSizes" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-arrow-expand-horizontal</v-icon></div><div><h2>Largura do conteúdo</h2><p>Área útil das páginas.</p></div><v-switch v-model="form.contentWidthEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.contentWidth" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.contentWidthEnabled"><v-btn v-for="item in contentWidths" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-transition</v-icon></div><div><h2>Transições</h2><p>Movimento entre estados.</p></div><v-switch v-model="form.motionEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.motion" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.motionEnabled"><v-btn v-for="item in motions" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-contrast-box</v-icon></div><div><h2>Contraste</h2><p>Separação visual e leitura.</p></div><v-switch v-model="form.contrastEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.contrast" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.contrastEnabled"><v-btn v-for="item in contrasts" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
            <v-card class="soft-card setting-card"><div class="setting-head"><div class="setting-icon"><v-icon>mdi-table</v-icon></div><div><h2>Estilo das tabelas</h2><p>Leitura de listas extensas.</p></div><v-switch v-model="form.tableStyleEnabled" :disabled="!canEdit" color="secondary" hide-details inset /></div><v-btn-toggle v-model="form.tableStyle" mandatory divided variant="outlined" class="choice-group" :disabled="!canEdit || !form.tableStyleEnabled"><v-btn v-for="item in tableStyles" :key="item.value" :value="item.value">{{ item.label }}</v-btn></v-btn-toggle></v-card>
          </div>
        </div>

        <aside class="preview-column">
          <div class="preview-heading"><div><h2>Pré-visualização real</h2><p>Botões, cartões, tabela e formulário antes de guardar.</p></div><v-btn-toggle v-model="previewPalette" mandatory density="compact" variant="outlined"><v-btn value="light" icon="mdi-white-balance-sunny" aria-label="Pré-visualizar modo claro" /><v-btn value="dark" icon="mdi-weather-night" aria-label="Pré-visualizar modo escuro" /></v-btn-toggle></div>
          <div class="site-preview" :style="previewStyle">
            <div class="preview-bar"><span class="preview-brand">VITOR <i>Gouveia</i></span><span class="preview-avatar">VG</span></div>
            <div class="preview-body">
              <div class="preview-title"><div><small>VISÃO GERAL</small><h3>Exemplo do portal</h3></div><button>Nova encomenda</button></div>
              <div class="preview-metrics"><article><span>Encomendas</span><b>24</b></article><article><span>Faturação</span><b>8 420 €</b></article></div>
              <article class="preview-panel">
                <div class="preview-form"><label>Pesquisar produto</label><div><v-icon size="15">mdi-magnify</v-icon><span>Referência ou nome</span></div></div>
                <div :class="['preview-table', `table-${resolvedPreview.tableStyle}`]"><div><b>Produto</b><b>Estado</b><b>Preço</b></div><div><span>Pilhas profissionais</span><em>Ativo</em><strong>12,50 €</strong></div><div><span>Expositor comercial</span><em>Ativo</em><strong>48,00 €</strong></div></div>
                <div class="preview-actions"><button>Guardar</button><button>Cancelar</button></div>
              </article>
            </div>
          </div>
          <v-alert v-if="canEdit && dirty" type="info" variant="tonal" density="compact" class="mt-3">Está a ver alterações ainda não guardadas.</v-alert>
          <v-alert v-if="!validColors" type="warning" variant="tonal" density="compact" class="mt-3">Existe uma cor com formato inválido.</v-alert>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.head-actions{align-items:center;display:flex;gap:10px}.access-card{align-items:center;display:flex;justify-content:space-between;padding:18px 22px}.access-card>div{align-items:center;display:flex;gap:14px}.access-card b,.access-card p{display:block}.access-card p{color:rgba(var(--v-theme-on-surface),.62);font-size:.78rem;margin:3px 0 0}.appearance-layout{align-items:start;display:grid;gap:24px;grid-template-columns:minmax(0,1.18fr) minmax(430px,.82fr)}.settings-column{display:grid;gap:18px}.setting-card{padding:22px}.setting-head{align-items:center;display:grid;gap:12px;grid-template-columns:42px minmax(0,1fr) auto;margin-bottom:18px}.setting-icon{align-items:center;background:rgba(var(--v-theme-primary),.08);border-radius:12px;color:rgb(var(--v-theme-primary));display:flex;height:42px;justify-content:center;width:42px}.setting-head h2,.preview-heading h2{font-size:1rem;margin:0}.setting-head p,.preview-heading p{color:rgba(var(--v-theme-on-surface),.62);font-size:.75rem;margin:3px 0 0}.choice-group{display:grid!important;grid-auto-flow:column;grid-auto-columns:1fr;width:100%}.choice-group :deep(.v-btn){min-width:0;text-transform:none}.preset-grid{display:grid;gap:10px;grid-template-columns:repeat(2,minmax(0,1fr))}.preset-grid.disabled,.color-list.disabled{opacity:.48}.preset-card{align-items:center;background:rgba(var(--v-theme-primary),.025);border:1px solid rgba(var(--v-theme-on-surface),.1);border-radius:14px;color:rgb(var(--v-theme-on-surface));cursor:pointer;display:grid;gap:11px;grid-template-columns:42px minmax(0,1fr) 20px;min-height:82px;padding:11px;text-align:left}.preset-card:disabled{cursor:default}.preset-card:not(:disabled):hover{border-color:rgba(var(--v-theme-primary),.4)}.preset-card.active{border-color:rgb(var(--v-theme-primary));box-shadow:0 0 0 2px rgba(var(--v-theme-primary),.08)}.preset-colors{border-radius:10px;display:grid;grid-template-columns:1fr 1fr;height:42px;overflow:hidden}.preset-colors i{display:block}.preset-card b,.preset-card small{display:block}.preset-card b{font-size:.82rem}.preset-card small{color:rgba(var(--v-theme-on-surface),.58);font-size:.64rem;line-height:1.35;margin-top:3px}.palette-toolbar{align-items:center;border-top:1px solid rgba(var(--v-theme-on-surface),.08);display:flex;justify-content:space-between;margin-top:20px;padding-top:18px}.palette-toolbar>span{font-size:.76rem;font-weight:700}.color-list{display:grid;margin-top:8px}.color-row{align-items:center;border-bottom:1px solid rgba(var(--v-theme-on-surface),.07);display:grid;gap:16px;grid-template-columns:minmax(0,1fr) 174px;padding:10px 0}.color-row:last-child{border-bottom:0}.color-row label b,.color-row label small{display:block}.color-row label b{font-size:.78rem}.color-row label small{color:rgba(var(--v-theme-on-surface),.56);font-size:.65rem;margin-top:2px}.color-input-wrap{align-items:center;display:grid;gap:8px;grid-template-columns:40px 1fr}.color-input-wrap input{background:transparent;border:1px solid rgba(var(--v-theme-on-surface),.16);border-radius:9px;height:40px;padding:3px;width:40px}.compact-settings{display:grid;gap:18px;grid-template-columns:repeat(2,minmax(0,1fr))}.preview-column{position:sticky;top:86px}.preview-heading{align-items:center;display:flex;gap:12px;justify-content:space-between;margin-bottom:13px}.site-preview{background:var(--p-background);border:1px solid color-mix(in srgb,var(--p-on-surface) 12%,transparent);border-radius:var(--p-card-radius);box-shadow:var(--p-shadow);color:var(--p-on-surface);font-size:calc(14px * var(--p-font));overflow:hidden;transition:background-color .18s ease,border-radius .18s ease}.preview-bar{align-items:center;background:var(--p-primary);color:white;display:flex;height:58px;justify-content:space-between;padding:0 18px}.preview-brand{font-family:Georgia,serif;font-size:1.02em;letter-spacing:.08em}.preview-brand i{font-size:.72em;font-weight:400;margin-left:4px}.preview-avatar{align-items:center;background:var(--p-secondary);border-radius:50%;display:flex;font-size:.65em;font-weight:800;height:30px;justify-content:center;width:30px}.preview-body{display:grid;gap:var(--p-gap);padding:calc(var(--p-gap) * 1.4)}.preview-title{align-items:center;display:flex;justify-content:space-between}.preview-title small{color:var(--p-secondary);font-size:.56em;font-weight:850;letter-spacing:.11em}.preview-title h3{font-size:1.18em;margin:3px 0 0}.preview-title button,.preview-actions button:first-child{background:var(--p-primary);border:0;border-radius:var(--p-control-radius);color:white;font-size:.7em;padding:9px 12px}.preview-metrics{display:grid;gap:var(--p-gap);grid-template-columns:1fr 1fr}.preview-metrics article,.preview-panel{background:var(--p-surface);border:1px solid color-mix(in srgb,var(--p-on-surface) 9%,transparent);border-radius:var(--p-card-radius);box-shadow:var(--p-shadow)}.preview-metrics article{padding:12px}.preview-metrics span,.preview-metrics b{display:block}.preview-metrics span{color:var(--p-muted);font-size:.66em}.preview-metrics b{font-size:1.08em;margin-top:4px}.preview-panel{display:grid;gap:var(--p-gap);padding:14px}.preview-form label{display:block;font-size:.66em;font-weight:700;margin-bottom:5px}.preview-form>div{align-items:center;border:1px solid color-mix(in srgb,var(--p-on-surface) 18%,transparent);border-radius:var(--p-control-radius);color:var(--p-muted);display:flex;font-size:.68em;gap:7px;min-height:36px;padding:0 10px}.preview-table{border:1px solid color-mix(in srgb,var(--p-on-surface) 10%,transparent);border-radius:var(--p-control-radius);overflow:hidden}.preview-table>div{display:grid;font-size:.64em;gap:7px;grid-template-columns:1fr 52px 55px;padding:8px}.preview-table>div+div{border-top:1px solid color-mix(in srgb,var(--p-on-surface) 8%,transparent)}.preview-table em{color:var(--p-secondary);font-style:normal}.preview-table strong{text-align:right}.preview-actions{display:flex;gap:8px;justify-content:flex-end}.preview-actions button{border:1px solid color-mix(in srgb,var(--p-on-surface) 16%,transparent);border-radius:var(--p-control-radius);font-size:.68em;padding:7px 11px}.preview-actions button:last-child{background:transparent;color:var(--p-on-surface)}@media(max-width:1180px){.appearance-layout{grid-template-columns:1fr}.preview-column{position:static}}@media(max-width:720px){.head-actions,.access-card,.palette-toolbar,.preview-heading{align-items:stretch;flex-direction:column}.access-card{gap:12px}.compact-settings,.preset-grid{grid-template-columns:1fr}.setting-head{grid-template-columns:42px minmax(0,1fr) auto}.choice-group{grid-auto-flow:row;grid-auto-rows:1fr}.color-row{align-items:start;grid-template-columns:1fr}.preview-title{align-items:flex-start;gap:10px}.preview-title button{font-size:0;padding:9px}.preview-title button::after{content:'+';font-size:16px}.page-head .head-actions{width:100%}.head-actions .v-btn{width:100%}}
.preview-body{box-sizing:border-box;margin-inline:auto;width:var(--p-content)}
.preview-table.table-clean>div+div{border-top:0}
.preview-table.table-lines>div+div{border-top-color:color-mix(in srgb,var(--p-on-surface) var(--p-border),transparent)}
.preview-table.table-striped>div:nth-child(odd){background:color-mix(in srgb,var(--p-primary) 7%,transparent)}
</style>
