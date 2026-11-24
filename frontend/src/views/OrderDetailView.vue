<script setup>
import { markRaw, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
import { useCartStore } from '../stores/cart'
import { idempotencyKey } from '../services/api'
import PdfPagePreview from '../components/PdfPagePreview.vue'

const defaultNoPriceLayout = {
  showCustomer: true,
  showContact: true,
  showCarrier: true,
  showProductName: true,
  showSummary: true,
  showCategories: true,
  blankColumn: true,
  fontSize: 'normal',
  headerStyle: 'compact',
  showDocumentHeading: false,
}
const defaultPricedLayout = {
  ...defaultNoPriceLayout,
  showCarrier: false,
  showCategories: false,
  blankColumn: false,
  headerStyle: 'full',
  showDocumentHeading: true,
}
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const feedback = useFeedbackStore()
const cart = useCartStore()
const data = ref(null)
const status = ref('')
const note = ref('')
const internalNotes = ref('')
const pdfNotes = ref('')
const includePdfNotes = ref(false)
const saving = ref(false)
const savingNotes = ref(false)
const savingPdfNotes = ref(false)
const pdfEditorOpen = ref(false)
const pdfKind = ref('no_prices')
const pdfLayout = ref({ ...defaultNoPriceLayout })
const pdfEditorReady = ref(false)
const previewLoading = ref(false)
const previewUrl = ref('')
const previewDocument = ref(null)
const previewPageCount = ref(0)
const previewError = ref('')
const savingLayout = ref(false)
const repeating = ref(false)
const pdfLayoutCustomized = ref(false)
let previewTimer = null
let previewRequest = 0
let activePdfTask = null
let pdfModulePromise = null

const money = value => `${Number(value || 0).toFixed(2)} €`

async function load() {
  try {
    data.value = (await api.get(`/orders/${route.params.id}`)).data
    status.value = data.value.order.orderStatus
    internalNotes.value = data.value.order.internalNotes || ''
    pdfNotes.value = data.value.order.pdfNotes || ''
    includePdfNotes.value = Boolean(data.value.order.includePdfNotes)
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}

async function changeStatus() {
  saving.value = true
  try {
    const response = await api.patch(`/admin/orders/${route.params.id}/status`, { status: status.value, note: note.value })
    data.value.order = response.data.order
    await load()
    feedback.show('Estado atualizado.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}

async function saveInternalNotes() {
  savingNotes.value = true
  try {
    const response = await api.patch(`/admin/orders/${route.params.id}/notes`, { notes: internalNotes.value })
    data.value.order = response.data.order
    internalNotes.value = response.data.order.internalNotes || ''
    feedback.show('Nota interna guardada.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingNotes.value = false }
}

async function savePdfNotes() {
  savingPdfNotes.value = true
  try {
    const response = await api.patch(`/admin/orders/${route.params.id}/pdf-notes`, { notes: pdfNotes.value, include: includePdfNotes.value })
    data.value.order = response.data.order
    pdfNotes.value = response.data.order.pdfNotes || ''
    includePdfNotes.value = Boolean(response.data.order.includePdfNotes)
    feedback.show(includePdfNotes.value ? 'Observações incluídas no PDF.' : 'Observações do PDF guardadas e ocultas.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingPdfNotes.value = false }
}

async function remove() {
  if (!await feedback.confirm(`Eliminar definitivamente a encomenda ${data.value.order.publicNumber}?`, 'Eliminar encomenda')) return
  try {
    await api.delete(`/admin/orders/${data.value.order.publicNumber}`)
    feedback.show('Encomenda eliminada.')
    router.replace('/admin/encomendas')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}

async function repeatOrder() {
  if (!await feedback.confirm('Adicionar novamente os produtos disponíveis desta encomenda ao carrinho atual?', 'Repetir encomenda')) return
  repeating.value = true
  try {
    const { data: result } = await api.post(`/orders/${route.params.id}/repeat`, { idempotency_key: idempotencyKey('repeat') })
    cart.setCart(result.catalog, result.cart)
    const skipped = result.skipped?.length ? ` ${result.skipped.length} artigo(s) indisponível(eis) foram ignorados.` : ''
    feedback.show(`${result.added} artigo(s) adicionados ao carrinho.${skipped}`, result.skipped?.length ? 'warning' : 'success')
    router.push(`/carrinho/${result.catalog === 'interpilhas' ? 'utilidades' : result.catalog}`)
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { repeating.value = false }
}

function clearPreview() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value)
  previewUrl.value = ''
  const previousDocument = previewDocument.value
  previewDocument.value = null
  previewPageCount.value = 0
  if (previousDocument) previousDocument.destroy().catch(() => {})
}

async function loadPdfRenderer() {
  if (!pdfModulePromise) {
    pdfModulePromise = Promise.all([
      import('pdfjs-dist/legacy/build/pdf.mjs'),
      import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),
    ]).then(([pdfjs, worker]) => {
      pdfjs.GlobalWorkerOptions.workerSrc = worker.default
      return pdfjs
    })
  }
  return pdfModulePromise
}

async function loadPreviewDocument(pdfData, requestId) {
  const pdfjs = await loadPdfRenderer()
  if (requestId !== previewRequest) return null
  const loadingTask = pdfjs.getDocument({ data: new Uint8Array(pdfData) })
  activePdfTask = loadingTask
  const pdf = await loadingTask.promise
  if (activePdfTask === loadingTask) activePdfTask = null
  if (requestId !== previewRequest) {
    await pdf.destroy()
    return null
  }
  return markRaw(pdf)
}

async function refreshPreview() {
  const requestId = ++previewRequest
  if (activePdfTask) {
    activePdfTask.destroy().catch(() => {})
    activePdfTask = null
  }
  previewLoading.value = true
  previewError.value = ''
  try {
    const response = await api.post(`/admin/orders/${route.params.id}/pdf-preview`, pdfLayout.value, { params: { kind: pdfKind.value }, responseType: 'arraybuffer' })
    if (requestId !== previewRequest) return
    const nextPdfUrl = URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }))
    const pdf = await loadPreviewDocument(response.data, requestId)
    if (!pdf || requestId !== previewRequest) {
      URL.revokeObjectURL(nextPdfUrl)
      return
    }
    const previousPdfUrl = previewUrl.value
    const previousDocument = previewDocument.value
    previewUrl.value = nextPdfUrl
    previewDocument.value = pdf
    previewPageCount.value = pdf.numPages
    if (previousPdfUrl) URL.revokeObjectURL(previousPdfUrl)
    if (previousDocument) previousDocument.destroy().catch(() => {})
  } catch (error) {
    if (requestId === previewRequest) {
      previewError.value = errorMessage(error)
      feedback.show(previewError.value, 'error')
    }
  } finally {
    if (requestId === previewRequest) previewLoading.value = false
  }
}

function schedulePreview() {
  clearTimeout(previewTimer)
  previewTimer = setTimeout(refreshPreview, 300)
}

const defaultsForKind = kind => kind === 'priced' ? defaultPricedLayout : defaultNoPriceLayout

async function loadPdfLayout(kind) {
  pdfEditorReady.value = false
  const response = await api.get('/admin/pdf-layout', { params: { kind, user_id: data.value.order.userId } })
  pdfLayout.value = { ...defaultsForKind(kind), ...response.data.layout }
  pdfLayoutCustomized.value = Boolean(response.data.customized)
  await refreshPreview()
  pdfEditorReady.value = true
}

async function openPdfEditor(kind = 'no_prices') {
  pdfEditorOpen.value = true
  pdfKind.value = kind
  previewLoading.value = true
  try {
    await loadPdfLayout(kind)
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
    pdfEditorOpen.value = false
  } finally { previewLoading.value = false }
}

async function switchPdfKind(kind) {
  if (!kind || kind === pdfKind.value) return
  pdfKind.value = kind
  clearPreview()
  previewLoading.value = true
  try { await loadPdfLayout(kind) }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { previewLoading.value = false }
}

function closePdfEditor() {
  pdfEditorOpen.value = false
  pdfEditorReady.value = false
  clearTimeout(previewTimer)
  previewRequest += 1
  if (activePdfTask) activePdfTask.destroy().catch(() => {})
  activePdfTask = null
  clearPreview()
}

function resetPdfLayout() { pdfLayout.value = { ...defaultsForKind(pdfKind.value) } }

async function savePdfLayout() {
  savingLayout.value = true
  try {
    const response = await api.put('/admin/pdf-layout', pdfLayout.value, { params: { kind: pdfKind.value, user_id: data.value.order.userId } })
    pdfLayout.value = { ...defaultsForKind(pdfKind.value), ...response.data.layout }
    pdfLayoutCustomized.value = true
    feedback.show(`Modelo do PDF ${pdfKind.value === 'priced' ? 'com preços' : 'sem preços'} guardado para ${data.value.order.customerName}.`)
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingLayout.value = false }
}

async function useGlobalPdfLayout() {
  if (!await feedback.confirm(`Remover a personalização deste cliente e voltar a usar o modelo padrão do PDF ${pdfKind.value === 'priced' ? 'com preços' : 'sem preços'}?`, 'Usar modelo padrão')) return
  savingLayout.value = true
  try {
    const response = await api.delete('/admin/pdf-layout', { params: { kind: pdfKind.value, user_id: data.value.order.userId } })
    pdfLayout.value = { ...defaultsForKind(pdfKind.value), ...response.data.layout }
    pdfLayoutCustomized.value = false
    feedback.show('Este cliente voltou a usar o modelo padrão.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingLayout.value = false }
}

watch(pdfLayout, () => {
  if (pdfEditorOpen.value && pdfEditorReady.value) schedulePreview()
}, { deep: true })

onMounted(async () => { await load(); if (auth.isAdmin && route.query.editPdf === '1') openPdfEditor('no_prices') })
onBeforeUnmount(() => {
  clearTimeout(previewTimer)
  previewRequest += 1
  if (activePdfTask) activePdfTask.destroy().catch(() => {})
  clearPreview()
})
</script>

<template>
  <div class="page">
    <v-btn :to="auth.isAdmin ? '/admin/encomendas' : '/encomendas'" variant="text" prepend-icon="mdi-arrow-left" class="mb-4">Voltar</v-btn>
    <v-skeleton-loader v-if="!data" type="article, table" />
    <template v-else>
      <div class="page-head">
        <div><h1>{{ data.order.publicNumber }}</h1><p>Criada em {{ new Date(data.order.createdAt).toLocaleString('pt-PT') }}</p></div>
        <div class="d-flex flex-wrap ga-2">
          <v-btn v-if="!auth.isAdmin" color="primary" prepend-icon="mdi-cart-arrow-down" :loading="repeating" @click="repeatOrder">Repetir encomenda</v-btn>
          <v-btn :href="data.order.pdfUrl" target="_blank" variant="tonal" prepend-icon="mdi-currency-eur">PDF com preços</v-btn>
          <v-btn :href="data.order.pdfNoPricesUrl" target="_blank" variant="tonal" prepend-icon="mdi-eye-off-outline">PDF sem preços</v-btn>
          <v-btn v-if="auth.isAdmin" color="secondary" variant="tonal" prepend-icon="mdi-file-edit-outline" @click="openPdfEditor('no_prices')">Editar PDFs</v-btn>
          <v-btn v-if="auth.isAdmin" color="error" variant="tonal" prepend-icon="mdi-delete-outline" @click="remove">Eliminar</v-btn>
          <v-chip size="large" :color="data.order.orderStatus === 'pending' ? 'warning' : data.order.orderStatus === 'confirmed' ? 'success' : 'info'">{{ data.order.orderStatusLabel }}</v-chip>
        </div>
      </div>

      <v-row>
        <v-col cols="12" lg="8">
          <v-card class="soft-card">
            <v-card-title class="pa-5">Produtos</v-card-title>
            <v-table><thead><tr><th>Produto</th><th>Variante</th><th>Qtd.</th><th class="text-right">Total</th></tr></thead><tbody><tr v-for="item in data.order.items" :key="item.id"><td><b>{{ item.name }}</b><div class="text-caption">{{ item.ref }}</div></td><td>{{ [item.color,item.size].filter(Boolean).join(' · ') || '—' }}</td><td>{{ item.quantity }}</td><td class="text-right font-weight-bold">{{ money(item.lineTotal) }}</td></tr></tbody></v-table>
            <v-divider /><div class="d-flex justify-end pa-5 text-h6">Total: <b class="ml-3">{{ money(data.order.total) }}</b></div>
          </v-card>
        </v-col>
        <v-col cols="12" lg="4">
          <v-card class="soft-card pa-5 mb-4"><div class="text-h6 font-weight-bold mb-4">Cliente</div><b>{{ data.order.customerName }}</b><div>{{ data.order.customerCompany }}</div><div class="text-medium-emphasis mt-3">{{ (data.order.customerEmails || [data.order.customerEmail]).filter(Boolean).join(', ') }}<br>{{ data.order.customerPhone }}<br>{{ data.order.customerNif }}</div><v-divider class="my-4"/><div class="text-caption text-medium-emphasis">MORADA</div><div>{{ data.order.customerBillingAddressLine1 || '—' }}<br>{{ data.order.customerBillingPostalCode }} {{ data.order.customerBillingCity }}</div><div class="text-caption text-medium-emphasis mt-3">MORADA DE ENTREGA</div><div>{{ data.order.customerDeliveryAddressLine1 || '—' }}<br>{{ data.order.customerDeliveryPostalCode }} {{ data.order.customerDeliveryCity }}</div><div class="text-caption text-medium-emphasis mt-3">TRANSPORTADORA / TRANSITÁRIO</div><b>{{ data.order.customerCarrier || '—' }}</b></v-card>
          <v-card v-if="auth.isAdmin" class="soft-card pa-5 mb-4"><div class="d-flex align-center ga-2 mb-3"><v-icon color="secondary">mdi-note-text-outline</v-icon><div class="text-h6 font-weight-bold">Notas internas</div></div><v-textarea v-model="internalNotes" label="Notas visíveis apenas para administradores" rows="4" hide-details class="mb-4" /><v-btn color="primary" variant="tonal" block :loading="savingNotes" @click="saveInternalNotes">Guardar nota interna</v-btn></v-card>
          <v-card v-if="auth.isAdmin" class="soft-card pa-5 mb-4"><div class="d-flex align-center ga-2 mb-3"><v-icon color="secondary">mdi-file-document-edit-outline</v-icon><div><div class="text-h6 font-weight-bold">Observações no PDF</div><div class="text-caption text-medium-emphasis">Aplicam-se ao PDF com e sem preços.</div></div></div><v-switch v-model="includePdfNotes" color="secondary" label="Mostrar estas observações no PDF" hide-details class="mb-2" /><v-textarea v-model="pdfNotes" label="Texto das observações" rows="4" hide-details class="mb-4" /><v-btn color="primary" variant="tonal" block :loading="savingPdfNotes" @click="savePdfNotes">Guardar observações do PDF</v-btn></v-card>
          <v-card v-if="auth.isAdmin" class="soft-card pa-5"><div class="text-h6 font-weight-bold mb-4">Atualizar estado</div><v-select v-model="status" label="Estado" :items="[{title:'Pendente',value:'pending'},{title:'Confirmada',value:'confirmed'},{title:'Enviada',value:'shipped'}]" /><v-textarea v-model="note" label="Nota do histórico" rows="2" /><v-btn color="primary" block :loading="saving" @click="changeStatus">Guardar estado</v-btn></v-card>
        </v-col>
      </v-row>
      <v-card v-if="data.history.length" class="soft-card pa-5 mt-5"><div class="text-h6 font-weight-bold mb-4">Histórico</div><v-timeline side="end" density="compact"><v-timeline-item v-for="row in data.history" :key="row.id" dot-color="secondary" size="small"><b>{{ row.newStatusLabel || row.newStatus }}</b><div class="text-caption text-medium-emphasis">{{ new Date(row.changedAt).toLocaleString('pt-PT') }} · {{ row.changedByUsername }}</div><div v-if="row.note">{{ row.note }}</div></v-timeline-item></v-timeline></v-card>
    </template>

    <v-dialog v-model="pdfEditorOpen" max-width="1440" :fullscreen="$vuetify.display.smAndDown" @after-leave="closePdfEditor">
      <v-card class="pdf-editor-card">
        <v-card-title class="pdf-editor-title"><div><div class="d-flex flex-wrap align-center ga-2"><div class="text-h5 font-weight-bold">Editor dos PDFs</div><v-chip :color="pdfLayoutCustomized ? 'secondary' : 'grey'" size="small" variant="tonal">{{ pdfLayoutCustomized ? 'Personalizado' : 'Padrão global' }}</v-chip></div><div class="text-body-2 text-medium-emphasis">Modelo de {{ data?.order.customerName }} · cada documento é independente.</div></div><v-btn icon="mdi-close" variant="text" aria-label="Fechar editor" @click="closePdfEditor" /></v-card-title>
        <v-divider />
        <v-tabs :model-value="pdfKind" color="primary" grow class="pdf-kind-tabs" @update:model-value="switchPdfKind">
          <v-tab value="priced" prepend-icon="mdi-currency-eur">Com preços</v-tab>
          <v-tab value="no_prices" prepend-icon="mdi-eye-off-outline">Sem preços</v-tab>
        </v-tabs>
        <v-divider />
        <div class="pdf-editor-grid">
          <aside class="pdf-editor-settings">
            <div class="text-overline text-medium-emphasis mb-2">Blocos do documento</div>
            <v-switch v-model="pdfLayout.showCustomer" label="Dados do cliente" color="primary" inset hide-details />
            <v-switch v-model="pdfLayout.showContact" label="Contacto e morada" color="primary" inset hide-details />
            <v-switch v-model="pdfLayout.showCarrier" label="Transportadora / Transitário" color="primary" inset hide-details />
            <v-switch v-model="pdfLayout.showSummary" label="Resumo de referências" color="primary" inset hide-details />
            <v-divider class="my-4" />
            <div class="text-overline text-medium-emphasis mb-2">Cabeçalho</div>
            <v-select v-model="pdfLayout.headerStyle" label="Formato do cabeçalho" :items="[{ title: 'Compacto', value: 'compact' }, { title: 'Completo', value: 'full' }, { title: 'Sem cabeçalho', value: 'hidden' }]" hide-details />
            <v-switch v-model="pdfLayout.showDocumentHeading" label="Mostrar título grande no documento" color="primary" inset hide-details class="mt-2" />
            <v-divider class="my-4" />
            <div class="text-overline text-medium-emphasis mb-2">Tabela de artigos</div>
            <v-switch v-model="pdfLayout.showCategories" label="Separar por categorias" color="primary" inset hide-details />
            <v-switch v-model="pdfLayout.showProductName" label="Mostrar nome do produto" color="primary" inset hide-details />
            <v-switch v-model="pdfLayout.blankColumn" label="Coluna em branco entre Ref. e Qtd." color="primary" inset hide-details />
            <v-select v-model="pdfLayout.fontSize" class="mt-5" label="Tamanho da letra" :items="[{ title: 'Compacta', value: 'compact' }, { title: 'Normal', value: 'normal' }, { title: 'Grande', value: 'large' }]" hide-details />
            <v-alert type="info" variant="tonal" density="compact" class="mt-5">Está a editar o PDF <b>{{ pdfKind === 'priced' ? 'com preços' : 'sem preços' }}</b>. A pré-visualização atualiza automaticamente.</v-alert>
            <v-btn variant="text" prepend-icon="mdi-restore" class="mt-3" @click="resetPdfLayout">Repor valores recomendados</v-btn>
            <v-btn v-if="pdfLayoutCustomized" variant="tonal" color="secondary" prepend-icon="mdi-account-arrow-left-outline" class="mt-2" block @click="useGlobalPdfLayout">Usar padrão global</v-btn>
          </aside>
          <section class="pdf-preview" aria-label="Pré-visualização do PDF">
            <div class="pdf-preview-toolbar"><div><b>Pré-visualização</b><span class="text-medium-emphasis ml-2">{{ data?.order.publicNumber }}</span></div><v-btn v-if="previewUrl" :href="previewUrl" target="_blank" size="small" variant="text" prepend-icon="mdi-open-in-new">Abrir</v-btn></div>
            <div class="pdf-preview-stage" :aria-busy="previewLoading">
              <div v-if="previewDocument && previewPageCount" class="pdf-preview-pages">
                <PdfPagePreview v-for="pageNumber in previewPageCount" :key="pageNumber" :document="previewDocument" :page-number="pageNumber" />
              </div>
              <div v-else-if="previewError" class="pdf-preview-empty"><v-alert type="error" variant="tonal" title="Não foi possível mostrar a pré-visualização"><div>{{ previewError }}</div><v-btn class="mt-3" variant="tonal" @click="refreshPreview">Tentar novamente</v-btn></v-alert></div>
              <div v-else class="pdf-preview-empty text-medium-emphasis">A preparar a pré-visualização…</div>
              <div v-if="previewLoading" class="pdf-preview-loading" role="status" aria-live="polite"><v-progress-circular indeterminate color="secondary" size="48" /><span>A atualizar o documento…</span></div>
            </div>
          </section>
        </div>
        <v-divider />
        <v-card-actions class="pdf-editor-actions"><v-btn variant="text" @click="closePdfEditor">Cancelar</v-btn><v-btn color="primary" prepend-icon="mdi-content-save-outline" :loading="savingLayout" @click="savePdfLayout">Guardar modelo</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.pdf-editor-card { max-height: 92vh; overflow: hidden; }
.pdf-editor-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 20px 24px; }
.pdf-editor-grid { display: grid; grid-template-columns: 350px minmax(0, 1fr); min-height: 0; flex: 1; overflow: hidden; }
.pdf-editor-settings { padding: 22px 24px; overflow-y: auto; border-right: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.pdf-preview { min-width: 0; display: flex; flex-direction: column; background: #eef1f5; }
.pdf-preview-toolbar { min-height: 52px; padding: 8px 18px; display: flex; align-items: center; justify-content: space-between; background: white; border-bottom: 1px solid #dfe4ec; }
.pdf-kind-tabs { flex: 0 0 auto; }
.pdf-preview-stage { position: relative; min-height: 620px; height: calc(92vh - 228px); padding: 18px; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch; }
.pdf-preview-pages { width: min(100%, 820px); margin: 0 auto; display: grid; gap: 16px; }
.pdf-preview-empty { min-height: 100%; display: flex; align-items: center; justify-content: center; text-align: center; }
.pdf-preview-loading { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: rgba(238, 241, 245, .78); color: #253147; font-weight: 600; backdrop-filter: blur(2px); }
.pdf-editor-actions { justify-content: flex-end; gap: 8px; padding: 14px 24px; }
@media (max-width: 959px) {
  .pdf-editor-card { max-height: none; height: 100%; }
  .pdf-editor-title { padding-top: max(20px, env(safe-area-inset-top)); }
  .pdf-editor-grid { grid-template-columns: 1fr; overflow-y: auto; }
  .pdf-editor-settings { border-right: 0; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); overflow: visible; }
  .pdf-preview { order: -1; }
  .pdf-preview-stage { min-height: 52dvh; height: auto; padding: 12px; overflow-y: visible; }
  .pdf-preview-pages { gap: 12px; }
  .pdf-editor-actions { position: sticky; bottom: 0; padding-bottom: max(14px, env(safe-area-inset-bottom)); background: white; z-index: 2; }
}
</style>
