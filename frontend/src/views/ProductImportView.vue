<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const route = useRoute()
const catalog = ref('interpilhas')
const catalogs = ref([])
const file = ref(null)
const preview = ref(null)
const loading = ref(false)
const importing = ref(false)
const updateExisting = ref(true)
const pdfCategoryLabel = ref('')
const pdfFile = ref(null)
const pdfPreview = ref(null)
const pdfLoading = ref(false)
const pdfImporting = ref(false)
const overwritePdfImages = ref(false)
const history = ref([])
const historyLoading = ref(false)
const rollingBack = ref(null)
const selectedFile = computed(() => Array.isArray(file.value) ? file.value[0] : file.value)
const isPdfProductFile = computed(() => String(selectedFile.value?.name || '').toLowerCase().endsWith('.pdf'))
const selectedPdfFile = computed(() => Array.isArray(pdfFile.value) ? pdfFile.value[0] : pdfFile.value)
const canImport = computed(() => preview.value?.rows?.length && !preview.value?.errors?.length)
const catalogOptions = computed(() => catalogs.value.map(item => ({ title: item.label, value: item.slug })))

async function loadCatalogs() {
  try {
    catalogs.value = (await api.get('/admin/catalogs')).data.catalogs || []
    const requested = String(route.query.catalog || '')
    if (catalogs.value.some(item => item.slug === requested)) catalog.value = requested
    else if (!catalogs.value.some(item => item.slug === catalog.value)) catalog.value = catalogs.value[0]?.slug || 'villas'
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}

async function loadHistory() {
  historyLoading.value = true
  try { history.value = (await api.get('/admin/import/products/history')).data.batches || [] }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { historyLoading.value = false }
}

function sourceType() {
  if (preview.value?.sourceType === 'pdf') return 'pdf'
  return String(selectedFile.value?.name || '').toLowerCase().endsWith('.csv') ? 'csv' : 'spreadsheet'
}

function formatDate(value) {
  return value ? new Intl.DateTimeFormat('pt-PT', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
}

async function rollbackImport(batch) {
  if (!await feedback.confirm(`Reverter a importação “${batch.filename}”? Os produtos alterados depois da importação serão protegidos e assinalados como conflito.`, 'Reverter importação')) return
  rollingBack.value = batch.id
  try {
    const { data } = await api.post(`/admin/import/products/history/${batch.id}/rollback`)
    const conflicts = data.conflicts?.length ? ` ${data.conflicts.length} produtos foram protegidos por terem alterações posteriores.` : ''
    feedback.show(`Importação revertida: ${data.restored} restaurados, ${data.removed} removidos e ${data.categoriesRemoved} categorias removidas.${conflicts}`, data.conflicts?.length ? 'warning' : 'success')
    await loadHistory()
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { rollingBack.value = null }
}

async function buildPreview() {
  if (!selectedFile.value) return feedback.show('Escolha um ficheiro Excel, CSV ou PDF.', 'warning')
  loading.value = true
  preview.value = null
  try {
    const form = new FormData()
    form.append('catalog', catalog.value)
    if (isPdfProductFile.value) form.append('category_label', pdfCategoryLabel.value.trim())
    form.append('file', selectedFile.value)
    preview.value = (await api.post('/admin/import/products/preview', form)).data
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

async function commitImport() {
  if (!canImport.value) return
  const summary = preview.value.summary
  const importingPdf = isPdfProductFile.value
  const sourceFile = selectedFile.value
  const message = importingPdf
    ? `Importar ${summary.valid} produtos e associar as imagens deste PDF? ${summary.create} serão criados e ${summary.update} atualizados.`
    : `Importar ${summary.valid} produtos? ${summary.create} serão criados e ${summary.update} já existem.`
  if (!await feedback.confirm(message, 'Confirmar importação')) return
  importing.value = true
  try {
    const { data } = await api.post('/admin/import/products/commit', {
      filename: preview.value.filename || sourceFile?.name || 'importacao',
      source_type: sourceType(),
      catalog: catalog.value,
      rows: preview.value.rows.map(row => row.payload),
      categories: preview.value.categories || [],
      update_existing: updateExisting.value,
    })
    let imageMessage = ''
    if (importingPdf && sourceFile) {
      const form = new FormData()
      form.append('catalog', catalog.value)
      form.append('overwrite', overwritePdfImages.value ? 'true' : 'false')
      form.append('file', sourceFile)
      const imageResult = (await api.post('/admin/import/products/pdf-images/commit', form)).data
      imageMessage = ` Imagens: ${imageResult.updated} associadas e ${imageResult.skipped} mantidas.`
    }
    feedback.show(`Importação concluída: ${data.created} criados, ${data.updated} atualizados e ${data.skipped} ignorados.${imageMessage}`)
    preview.value = null
    file.value = null
    if (importingPdf) {
      pdfPreview.value = null
      pdfFile.value = null
    }
    await loadHistory()
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    importing.value = false
  }
}

async function buildPdfPreview() {
  if (!selectedPdfFile.value) return feedback.show('Escolha um ficheiro PDF.', 'warning')
  pdfLoading.value = true
  pdfPreview.value = null
  try {
    const form = new FormData()
    form.append('catalog', catalog.value)
    form.append('file', selectedPdfFile.value)
    pdfPreview.value = (await api.post('/admin/import/products/pdf-images/preview', form)).data
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { pdfLoading.value = false }
}

async function commitPdfImages() {
  if (!pdfPreview.value?.summary?.matched || pdfPreview.value.issues?.length) return
  if (!await feedback.confirm(`Associar imagens a ${pdfPreview.value.summary.matched} produtos reconhecidos?`, 'Importar imagens do PDF')) return
  pdfImporting.value = true
  try {
    const form = new FormData()
    form.append('catalog', catalog.value)
    form.append('overwrite', overwritePdfImages.value ? 'true' : 'false')
    form.append('file', selectedPdfFile.value)
    const { data } = await api.post('/admin/import/products/pdf-images/commit', form)
    feedback.show(`Imagens associadas: ${data.updated}. Ignoradas: ${data.skipped}. Referências sem produto: ${data.missing}.`)
    pdfPreview.value = null
    pdfFile.value = null
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { pdfImporting.value = false }
}
onMounted(() => Promise.all([loadCatalogs(), loadHistory()]))
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><h1>Importar produtos</h1><p>Valide o ficheiro antes de aplicar todas as alterações numa única transação.</p></div>
      <div class="d-flex flex-wrap ga-2"><v-btn href="/api/v1/admin/import/products/template.xlsx" variant="tonal" prepend-icon="mdi-file-download-outline">Descarregar modelo Excel</v-btn><v-btn to="/admin/produtos" variant="tonal" prepend-icon="mdi-package-variant-closed">Ver produtos</v-btn></div>
    </div>

    <v-card class="soft-card pa-5 mb-6">
      <v-row class="align-start">
        <v-col cols="12" md="3"><v-select v-model="catalog" :items="catalogOptions" label="Catálogo de destino" :disabled="loading || importing" /></v-col>
        <v-col cols="12" md="6"><v-file-input v-model="file" accept=".xlsx,.csv,.pdf,text/csv,application/pdf,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" label="Ficheiro Excel, CSV ou PDF" prepend-icon="mdi-file-document-outline" hint="O PDF deve ter texto pesquisável. Tudo é validado antes da importação." persistent-hint :disabled="loading || importing" /></v-col>
        <v-col cols="12" md="3"><v-btn block height="56" color="primary" prepend-icon="mdi-eye-check-outline" :loading="loading" :disabled="!selectedFile || importing" @click="buildPreview">Validar ficheiro</v-btn></v-col>
        <v-col v-if="isPdfProductFile" cols="12" md="6" offset-md="3"><v-text-field v-model="pdfCategoryLabel" label="Categoria dos produtos (opcional)" prepend-inner-icon="mdi-shape-outline" hint="Se já existir, é reutilizada; caso contrário será criada." persistent-hint :disabled="loading || importing" /></v-col>
      </v-row>
    </v-card>

    <v-card class="soft-card pa-5 mb-6 pdf-import-card">
      <div class="d-flex align-start ga-3 mb-4"><v-avatar color="error" variant="tonal"><v-icon>mdi-file-pdf-box</v-icon></v-avatar><div><div class="text-h6 font-weight-bold">Associar imagens por PDF</div><div class="text-body-2 text-medium-emphasis">Reconhece tabelas de fornecedor, valida cada referência e extrai automaticamente a imagem da respetiva linha.</div></div></div>
      <v-row class="align-start"><v-col cols="12" md="9"><v-file-input v-model="pdfFile" accept=".pdf,application/pdf" label="Catálogo PDF com imagens" prepend-icon="mdi-file-pdf-box" hint="O PDF é analisado primeiro; nenhuma imagem é gravada sem confirmação." persistent-hint :disabled="pdfLoading || pdfImporting" /></v-col><v-col cols="12" md="3"><v-btn block height="56" color="primary" variant="tonal" prepend-icon="mdi-image-search-outline" :loading="pdfLoading" :disabled="!selectedPdfFile || pdfImporting" @click="buildPdfPreview">Analisar PDF</v-btn></v-col></v-row>
      <template v-if="pdfPreview">
        <v-row class="mt-2"><v-col cols="6" md="3"><v-card variant="tonal" class="import-metric"><span>Detetadas</span><strong>{{ pdfPreview.summary.detected }}</strong></v-card></v-col><v-col cols="6" md="3"><v-card variant="tonal" class="import-metric"><span>Correspondências</span><strong>{{ pdfPreview.summary.matched }}</strong></v-card></v-col><v-col cols="6" md="3"><v-card variant="tonal" class="import-metric" :class="{ 'has-errors': pdfPreview.summary.missing }"><span>Sem produto</span><strong>{{ pdfPreview.summary.missing }}</strong></v-card></v-col><v-col cols="6" md="3"><v-card variant="tonal" class="import-metric"><span>Já com imagem</span><strong>{{ pdfPreview.summary.withExistingImage }}</strong></v-card></v-col></v-row>
        <v-alert v-if="pdfPreview.issues.length" type="error" variant="tonal" class="my-4" title="Associação automática não é segura"><div v-for="issue in pdfPreview.issues" :key="issue.page">Página {{ issue.page }}: {{ issue.message }}</div></v-alert>
        <v-alert v-else type="success" variant="tonal" class="my-4" title="Associação validada">Todas as linhas reconhecidas têm uma imagem correspondente no PDF.</v-alert>
        <v-table density="compact" class="pdf-preview-table"><thead><tr><th>Página</th><th>Referência</th><th>Produto</th><th>Estado</th></tr></thead><tbody><tr v-for="row in pdfPreview.rows.slice(0, 60)" :key="row.ref"><td>{{ row.page }}</td><td class="font-weight-bold">{{ row.ref }}</td><td>{{ row.productName || '—' }}</td><td><v-chip size="x-small" :color="row.matched ? row.hasExistingImage ? 'warning' : 'success' : 'error'" variant="tonal">{{ row.matched ? row.hasExistingImage ? 'Já tem imagem' : 'Pronto' : 'Sem produto' }}</v-chip></td></tr></tbody></v-table>
        <div v-if="pdfPreview.rows.length > 60" class="text-caption text-medium-emphasis text-center py-3">A mostrar 60 de {{ pdfPreview.rows.length }} correspondências.</div>
        <div class="import-actions mt-4"><v-switch v-model="overwritePdfImages" color="primary" label="Substituir imagens existentes" hide-details /><v-btn color="primary" size="large" prepend-icon="mdi-image-multiple-outline" :disabled="Boolean(pdfPreview.issues.length) || !pdfPreview.summary.matched" :loading="pdfImporting" @click="commitPdfImages">Associar {{ pdfPreview.summary.matched }} imagens</v-btn></div>
      </template>
    </v-card>

    <template v-if="preview">
      <v-row>
        <v-col cols="6" md="3"><v-card class="import-metric soft-card"><span>Válidos</span><strong>{{ preview.summary.valid }}</strong></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="import-metric soft-card"><span>Novos</span><strong>{{ preview.summary.create }}</strong></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="import-metric soft-card"><span>Atualizações</span><strong>{{ preview.summary.update }}</strong></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="import-metric soft-card" :class="{ 'has-errors': preview.summary.errors }"><span>Erros</span><strong>{{ preview.summary.errors }}</strong></v-card></v-col>
      </v-row>

      <v-alert v-if="preview.errors.length" type="error" variant="tonal" class="my-5" title="Corrija o ficheiro antes de importar">
        <div v-for="error in preview.errors.slice(0, 20)" :key="`${error.row}-${error.ref}`" class="mt-1"><b>Linha {{ error.row }}<span v-if="error.ref"> · {{ error.ref }}</span>:</b> {{ error.messages.join(', ') }}</div>
        <div v-if="preview.errors.length > 20" class="mt-2 font-weight-bold">E mais {{ preview.errors.length - 20 }} erros.</div>
      </v-alert>
      <v-alert v-if="preview.warnings.length" type="warning" variant="tonal" class="my-5" :text="`${preview.warnings.length} produtos não têm categoria definida.`" />
      <v-alert v-if="preview.categories?.length" type="info" variant="tonal" class="my-5" :text="`${preview.categories.length} categorias ou subcategorias novas serão criadas automaticamente.`" />

      <v-card v-if="preview.sourceType === 'pdf'" class="pdf-ready-action pa-5 my-5" color="primary" variant="tonal">
        <div>
          <div class="text-h6 font-weight-bold">Pronto para importar</div>
          <div class="text-body-2">A análise ainda não gravou produtos. Serão criados {{ preview.summary.create }} e atualizados {{ preview.summary.update }}; as imagens do mesmo PDF também serão associadas.</div>
        </div>
        <v-btn color="primary" size="large" prepend-icon="mdi-database-import-outline" :disabled="!canImport" :loading="importing" @click="commitImport">Importar agora os {{ preview.summary.valid }} produtos</v-btn>
      </v-card>

      <v-card class="soft-card overflow-hidden mt-5">
        <div class="d-flex flex-wrap align-center justify-space-between ga-3 pa-5">
          <div><div class="text-h6 font-weight-bold">Pré-visualização</div><div class="text-caption text-medium-emphasis">{{ preview.filename }} · folha {{ preview.sheet }}</div></div>
          <v-chip variant="tonal" color="primary">{{ preview.rows.length }} linhas válidas</v-chip>
        </div>
        <v-table density="comfortable" class="import-table">
          <thead><tr><th>{{ preview.sourceType === 'pdf' ? 'Página' : 'Linha' }}</th><th>Estado</th><th>Referência</th><th>Produto</th><th>Categoria</th><th class="text-right">Preço</th><th>Quantidades</th></tr></thead>
          <tbody><tr v-for="row in preview.rows.slice(0, 150)" :key="`${row.sourceRow}-${row.payload.ref}`"><td>{{ row.sourceRow }}</td><td><v-chip size="x-small" :color="row.status === 'create' ? 'success' : 'info'" variant="tonal">{{ row.status === 'create' ? 'Novo' : 'Atualizar' }}</v-chip></td><td class="font-weight-bold">{{ row.payload.ref }}</td><td>{{ row.payload.name }}</td><td>{{ row.categoryLabel || 'Sem categoria' }}</td><td class="text-right">{{ Number(row.payload.price).toFixed(row.payload.catalog_slug === 'interpilhas' ? 3 : 2) }} €</td><td>{{ row.payload.quick_quantities?.length ? row.payload.quick_quantities.join(' · ') : '—' }}</td></tr></tbody>
        </v-table>
        <div v-if="preview.rows.length > 150" class="text-center text-caption text-medium-emphasis pa-4">A mostrar as primeiras 150 linhas. Todas serão importadas.</div>
      </v-card>

      <v-card class="soft-card pa-5 mt-5 import-actions">
        <v-switch v-model="updateExisting" color="primary" label="Atualizar produtos que já existem" hide-details />
        <v-btn color="primary" size="large" prepend-icon="mdi-database-import-outline" :disabled="!canImport" :loading="importing" @click="commitImport">Importar {{ preview.summary.valid }} produtos</v-btn>
      </v-card>
    </template>

    <v-card class="soft-card pa-5 mt-6">
      <div class="d-flex flex-wrap align-center justify-space-between ga-3 mb-4">
        <div><div class="text-h6 font-weight-bold">Histórico de importações</div><div class="text-body-2 text-medium-emphasis">Consulte e reverta produtos e categorias criados por cada importação. As imagens são preservadas.</div></div>
        <v-btn variant="text" prepend-icon="mdi-refresh" :loading="historyLoading" @click="loadHistory">Atualizar</v-btn>
      </div>
      <v-skeleton-loader v-if="historyLoading && !history.length" type="table-row@3" />
      <v-alert v-else-if="!history.length" type="info" variant="tonal" text="Ainda não existem importações registadas nesta versão." />
      <v-table v-else density="comfortable" class="history-table">
        <thead><tr><th>Data</th><th>Ficheiro</th><th>Catálogo</th><th>Resultado</th><th>Estado</th><th></th></tr></thead>
        <tbody><tr v-for="batch in history" :key="batch.id"><td>{{ formatDate(batch.createdAt) }}</td><td><strong>{{ batch.filename }}</strong><div class="text-caption text-medium-emphasis">{{ batch.actor }} · {{ batch.sourceType }}</div></td><td>{{ batch.catalog }}</td><td>{{ batch.created }} novos · {{ batch.updated }} atualizados<span v-if="batch.skipped"> · {{ batch.skipped }} ignorados</span></td><td><v-chip size="small" variant="tonal" :color="batch.status === 'applied' ? 'success' : batch.status.includes('conflicts') ? 'warning' : 'default'">{{ batch.status === 'applied' ? 'Aplicada' : batch.status.includes('conflicts') ? 'Revertida parcialmente' : 'Revertida' }}</v-chip></td><td class="text-right"><v-btn v-if="batch.status === 'applied'" color="error" variant="text" prepend-icon="mdi-backup-restore" :loading="rollingBack === batch.id" @click="rollbackImport(batch)">Reverter</v-btn><span v-else class="text-caption text-medium-emphasis">{{ formatDate(batch.rolledBackAt) }}</span></td></tr></tbody>
      </v-table>
    </v-card>
  </div>
</template>

<style scoped>
.import-metric { display: flex; flex-direction: column; padding: 20px; }
.import-metric span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; font-weight: 750; text-transform: uppercase; }
.import-metric strong { font-size: 1.8rem; font-variant-numeric: tabular-nums; }
.import-metric.has-errors { border-color: rgba(var(--v-theme-error), .45); }
.import-table { overflow-x: auto; }
.history-table { overflow-x: auto; }
.import-actions { align-items: center; display: flex; flex-wrap: wrap; gap: 16px; justify-content: space-between; }
.pdf-ready-action { align-items: center; display: flex; flex-wrap: wrap; gap: 18px; justify-content: space-between; }
.pdf-ready-action > div:first-child { flex: 1 1 360px; }
@media (max-width: 600px) { .import-actions :deep(.v-btn), .import-actions :deep(.v-input) { width: 100%; } }
</style>
