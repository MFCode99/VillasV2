<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useCartStore } from '../stores/cart'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
import { api, rootApi, errorMessage, idempotencyKey } from '../services/api'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()
const auth = useAuthStore()
const feedback = useFeedbackStore()
const submitting = ref(false)
const notes = ref('')
const pdfNotes = ref('')
const includePdfNotes = ref(false)
const customers = ref([])
const selectedCustomer = ref(null)
const orderForSomeoneElse = ref(false)
const manualQuantity = ref(false)
const ignoreMinimum = ref(false)
const customerQ = ref('')
const availableCatalogs = ref([])

const routeCatalog = computed(() => String(route.params.catalog || auth.catalogs[0] || 'villas').toLowerCase())
const catalogSlug = computed(() => routeCatalog.value === 'utilidades' ? 'interpilhas' : routeCatalog.value)
const catalogOptions = computed(() => availableCatalogs.value.map(item => ({ ...item, publicSlug: item.slug === 'interpilhas' ? 'utilidades' : item.slug })))
const activeCatalog = computed(() => availableCatalogs.value.find(item => item.slug === catalogSlug.value))
const catalogLabel = computed(() => activeCatalog.value?.label || (catalogSlug.value === 'interpilhas' ? 'Utilidades' : catalogSlug.value))
const publicCatalogSlug = computed(() => catalogSlug.value === 'interpilhas' ? 'utilidades' : catalogSlug.value)
const minimumTotal = computed(() => Number(cart.cart.minimum_total || (catalogSlug.value === 'interpilhas' ? 300 : 250)))
const total = computed(() => Number(cart.cart.total || 0))
const remaining = computed(() => Math.max(0, minimumTotal.value - total.value))
const meetsMinimum = computed(() => total.value >= minimumTotal.value)
const minimumSatisfied = computed(() => meetsMinimum.value || (auth.isAdmin && ignoreMinimum.value))
const customerItems = computed(() => customers.value.filter(customer => !customerQ.value || `${customer.fullName} ${customer.companyName} ${customer.username}`.toLowerCase().includes(customerQ.value.toLowerCase())))
const notesStorageKey = computed(() => `villas_cart_notes_${catalogSlug.value}`)
const customerStorageKey = computed(() => `villas_cart_customer_id_${catalogSlug.value}`)
const orderOwnerStorageKey = computed(() => `villas_cart_for_someone_else_${catalogSlug.value}`)
const manualQuantityStorageKey = computed(() => `villas_cart_manual_quantity_${catalogSlug.value}`)
const ignoreMinimumStorageKey = computed(() => `villas_cart_ignore_minimum_${catalogSlug.value}`)
const selectedCustomerData = computed(() => customers.value.find(customer => customer.id === selectedCustomer.value) || null)

function money(value) { return Number(value || 0).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' }) }
function originalLineTotal(item) { return Number(item.original_price || 0) * Number(item.quantity || 0) }
async function loadCatalog() {
  if (!auth.catalogs.includes(catalogSlug.value)) {
    const fallback = auth.catalogs[0] === 'interpilhas' ? 'utilidades' : auth.catalogs[0] || 'villas'
    await router.replace(`/carrinho/${fallback}`)
    return
  }
  cart.select(catalogSlug.value)
  notes.value = localStorage.getItem(notesStorageKey.value) || ''
  const savedCustomer = Number(localStorage.getItem(customerStorageKey.value))
  const validSavedCustomer = savedCustomer && customers.value.some(customer => customer.id === savedCustomer) ? savedCustomer : null
  orderForSomeoneElse.value = auth.isAdmin && (localStorage.getItem(orderOwnerStorageKey.value) === '1' || Boolean(validSavedCustomer))
  manualQuantity.value = auth.isAdmin && localStorage.getItem(manualQuantityStorageKey.value) === '1'
  ignoreMinimum.value = auth.isAdmin && localStorage.getItem(ignoreMinimumStorageKey.value) === '1'
  selectedCustomer.value = orderForSomeoneElse.value ? validSavedCustomer : null
  await cart.load(catalogSlug.value)
}
function productQuantityStep(item) {
  const step = Number(item.quantity_step)
  return Number.isInteger(step) && step > 0 ? step : 1
}
function effectiveQuantityStep(item) { return auth.isAdmin && manualQuantity.value ? 1 : productQuantityStep(item) }
function adjustedQuantity(item, direction) {
  const quantity = Number(item.quantity || 0)
  const step = effectiveQuantityStep(item)
  if (step === 1) return quantity + direction
  return direction > 0
    ? (Math.floor(quantity / step) + 1) * step
    : Math.max(step, (Math.ceil(quantity / step) - 1) * step)
}
function adjust(item, direction) { update(item, adjustedQuantity(item, direction)) }
function addQuickQuantity(item, amount) { update(item, item.quantity + Number(amount)) }
async function commitManualQuantity(item, event) {
  const input = event.target
  const quantity = Number(input.value)
  if (!Number.isInteger(quantity) || quantity < 1) {
    input.value = String(item.quantity)
    feedback.show('Indique uma quantidade inteira igual ou superior a 1.', 'warning')
    return
  }
  if (quantity === Number(item.quantity)) return
  await update(item, quantity)
}
async function remove(item) {
  if (!await feedback.confirm(`Remover ${item.name} do carrinho ${catalogLabel.value}?`)) return
  try { await cart.remove(item, catalogSlug.value); feedback.show('Produto removido.') } catch (error) { feedback.show(errorMessage(error), 'error') }
}
async function update(item, value) {
  const quantity = Number(value)
  const step = effectiveQuantityStep(item)
  if (quantity < step || quantity % step) return feedback.show(`Use múltiplos de ${step}.`, 'warning')
  try { await cart.update(item, quantity, catalogSlug.value, auth.isAdmin && manualQuantity.value) } catch (error) { await cart.load(catalogSlug.value); feedback.show(errorMessage(error), 'error') }
}
async function submit() {
  if (auth.isAdmin && orderForSomeoneElse.value && !selectedCustomer.value) return feedback.show('Selecione para quem é esta encomenda.', 'warning')
  if (!minimumSatisfied.value) return feedback.show(`Faltam ${money(remaining.value)} para o mínimo de ${money(minimumTotal.value)}.`, 'warning')
  const owner = auth.isAdmin && orderForSomeoneElse.value ? selectedCustomerData.value?.fullName : auth.user?.fullName
  if (!await feedback.confirm(`Confirmar esta encomenda ${catalogLabel.value} em nome de ${owner || 'si'}?`, 'Criar encomenda')) return
  submitting.value = true
  try {
    const { data } = await rootApi.post('/me/orders', {
      catalog_slug: catalogSlug.value,
      idempotency_key: idempotencyKey('order'),
      cart_revision: cart.cart.revision,
      notes: String(notes.value || '').trim() || null,
      pdf_notes: String(pdfNotes.value || '').trim() || null,
      include_pdf_notes: includePdfNotes.value,
      customer_user_id: auth.isAdmin && orderForSomeoneElse.value ? selectedCustomer.value : null,
      ignore_quantity_step: auth.isAdmin && manualQuantity.value,
      ignore_minimum_total: auth.isAdmin && ignoreMinimum.value,
    })
    await cart.load(catalogSlug.value)
    notes.value = ''
    pdfNotes.value = ''
    includePdfNotes.value = false
    localStorage.removeItem(notesStorageKey.value)
    if (auth.isAdmin) {
      selectedCustomer.value = null
      orderForSomeoneElse.value = false
      manualQuantity.value = false
      ignoreMinimum.value = false
      localStorage.removeItem(customerStorageKey.value)
      localStorage.removeItem(orderOwnerStorageKey.value)
      localStorage.removeItem(manualQuantityStorageKey.value)
      localStorage.removeItem(ignoreMinimumStorageKey.value)
    }
    feedback.show(auth.isAdmin ? 'Encomenda criada e confirmada.' : 'Encomenda criada com sucesso.')
    router.push(auth.isAdmin ? `/admin/encomendas/${data.order.publicNumber}` : `/encomendas/${data.order.publicNumber}`)
  } catch (error) {
    if (error?.response?.data?.detail === 'cart_revision_mismatch') await cart.load(catalogSlug.value)
    feedback.show(errorMessage(error), 'error')
  } finally { submitting.value = false }
}

watch(catalogSlug, () => loadCatalog().catch(error => feedback.show(errorMessage(error), 'error')))
watch(notes, value => { const text = String(value || '').trim(); if (text) localStorage.setItem(notesStorageKey.value, text); else localStorage.removeItem(notesStorageKey.value) })
watch(selectedCustomer, value => { if (!auth.isAdmin) return; if (value) localStorage.setItem(customerStorageKey.value, String(value)); else localStorage.removeItem(customerStorageKey.value) })
watch(orderForSomeoneElse, value => {
  if (!auth.isAdmin) return
  if (value) localStorage.setItem(orderOwnerStorageKey.value, '1')
  else {
    selectedCustomer.value = null
    localStorage.removeItem(orderOwnerStorageKey.value)
    localStorage.removeItem(customerStorageKey.value)
  }
})
watch(manualQuantity, value => {
  if (!auth.isAdmin) return
  if (value) localStorage.setItem(manualQuantityStorageKey.value, '1')
  else localStorage.removeItem(manualQuantityStorageKey.value)
})
watch(ignoreMinimum, value => {
  if (!auth.isAdmin) return
  if (value) localStorage.setItem(ignoreMinimumStorageKey.value, '1')
  else localStorage.removeItem(ignoreMinimumStorageKey.value)
})
onMounted(async () => {
  try {
    availableCatalogs.value = (await api.get('/catalog/navigation')).data.catalogs || []
    if (auth.isAdmin) customers.value = (await api.get('/admin/users?role=client&active=true')).data.users
    await loadCatalog()
  } catch (error) { feedback.show(errorMessage(error), 'error') }
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><div class="text-overline text-secondary font-weight-bold">Carrinho {{ catalogLabel }}</div><h1>Carrinho</h1><p>{{ cart.cart.lines }} linhas · {{ cart.cart.units }} unidades</p></div>
      <v-btn :to="`/catalogo/${publicCatalogSlug}`" variant="tonal" prepend-icon="mdi-plus">Adicionar produtos</v-btn>
    </div>

    <div v-if="catalogOptions.length > 1" class="catalog-cart-switch mb-6" role="navigation" aria-label="Escolher carrinho">
      <v-btn v-for="option in catalogOptions" :key="option.slug" :to="`/carrinho/${option.publicSlug}`" :variant="catalogSlug === option.slug ? 'flat' : 'tonal'" :color="catalogSlug === option.slug ? 'primary' : undefined" :prepend-icon="option.icon">
        {{ option.label }}
        <v-chip v-if="cart.carts[option.slug]?.units" size="x-small" class="ml-2" :color="catalogSlug === option.slug ? 'secondary' : undefined">{{ cart.carts[option.slug].units }}</v-chip>
      </v-btn>
    </div>

    <v-progress-linear v-if="cart.loading" indeterminate color="secondary" />
    <v-row v-else-if="cart.cart.items.length">
      <v-col cols="12" lg="8">
        <v-card class="soft-card"><v-list lines="three"><template v-for="(item, index) in cart.cart.items" :key="item.id"><v-divider v-if="index" /><v-list-item class="py-4" :class="{ 'gift-line': item.is_gift }"><template #prepend><v-avatar rounded="lg" size="72" color="grey-lighten-3"><v-img v-if="item.image_path" :src="`/media/${item.image_path}`" /><v-icon v-else>mdi-gift-outline</v-icon></v-avatar></template><v-list-item-title class="font-weight-bold">{{ item.name }}</v-list-item-title><v-list-item-subtitle>{{ item.ref }} · {{ [item.color, item.size].filter(Boolean).join(' · ') || item.type }}</v-list-item-subtitle><v-chip v-if="item.is_gift" size="small" color="success" variant="tonal" prepend-icon="mdi-gift-outline" class="mt-2">Oferta adicionada automaticamente</v-chip><v-chip v-else-if="item.promotion" size="x-small" color="success" variant="tonal" prepend-icon="mdi-sale-outline" class="mt-2">{{ item.promotion.label }}</v-chip><template #append><div class="cart-line-actions"><template v-if="!item.is_gift"><div v-if="item.quick_quantities?.length" class="cart-quick-quantities" aria-label="Atalhos de quantidade"><v-btn v-for="amount in item.quick_quantities" :key="amount" size="small" variant="text" color="primary" :aria-label="`Adicionar ${amount} unidades de ${item.name}`" @click="addQuickQuantity(item, amount)">+{{ amount }}</v-btn></div><div class="quantity-control"><v-btn icon="mdi-minus" size="small" variant="tonal" :aria-label="`Diminuir ${effectiveQuantityStep(item)} unidades de ${item.name}`" :disabled="item.quantity <= effectiveQuantityStep(item)" @click="adjust(item, -1)" /><v-text-field v-if="auth.isAdmin && manualQuantity" :model-value="item.quantity" type="number" inputmode="numeric" pattern="[0-9]*" min="1" step="1" density="compact" variant="outlined" hide-details class="cart-quantity-field" :aria-label="`Quantidade manual de ${item.name}`" @change="commitManualQuantity(item, $event)" @keydown.enter="$event.target.blur()" @wheel="$event.target.blur()" /><b v-else>{{ item.quantity }}</b><v-btn icon="mdi-plus" size="small" variant="tonal" :aria-label="`Aumentar ${effectiveQuantityStep(item)} unidades de ${item.name}`" @click="adjust(item, 1)" /></div></template><div class="text-right line-total"><small v-if="item.promotion && !item.is_gift" class="original-line-total">{{ money(originalLineTotal(item)) }}</small><div class="font-weight-bold">{{ item.is_gift ? `${item.quantity} × Oferta` : money(item.line_total) }}</div></div><v-btn v-if="!item.is_gift" icon="mdi-delete-outline" variant="text" color="error" :aria-label="`Remover ${item.name}`" @click="remove(item)" /></div></template></v-list-item></template></v-list></v-card>
      </v-col>
      <v-col cols="12" lg="4">
        <v-card class="soft-card pa-5 position-sticky" style="top:90px">
          <div class="d-flex align-center justify-space-between mb-5"><div class="text-h6 font-weight-bold">Resumo</div><v-chip size="small" variant="tonal" color="primary">{{ catalogLabel }}</v-chip></div>
          <div v-if="auth.isAdmin" class="order-owner mb-5">
            <v-checkbox v-model="orderForSomeoneElse" label="Esta encomenda não é para mim" color="primary" density="comfortable" hide-details :ripple="false" />
            <div class="text-caption text-medium-emphasis px-4 pb-3">Marque esta opção para criar a encomenda em nome de um cliente.</div>
            <v-expand-transition>
              <div v-if="orderForSomeoneElse" class="px-3 pb-3">
                <v-autocomplete v-model="selectedCustomer" v-model:search="customerQ" :items="customerItems" item-title="fullName" item-value="id" label="Para quem é a encomenda?" placeholder="Pesquisar e selecionar cliente" prepend-inner-icon="mdi-account-search-outline" clearable hide-details="auto"><template #item="{ props, item }"><v-list-item v-bind="props" :subtitle="item.companyName || item.username" /></template></v-autocomplete>
              </div>
            </v-expand-transition>
            <div v-if="!orderForSomeoneElse" class="order-owner-current"><v-icon size="20" color="success">mdi-account-check-outline</v-icon><span>A encomenda ficará em nome de <b>{{ auth.user?.fullName }}</b>.</span></div>
          </div>
          <div v-if="auth.isAdmin" class="admin-options mb-5">
            <div class="admin-options-title"><v-icon size="20">mdi-tune-variant</v-icon><span>Opções administrativas</span></div>
            <div class="admin-option-row">
              <div><b>Quantidade manual</b><p>Desativada: os botões + e − usam o múltiplo do produto. Ativada: pode escrever a quantidade ou alterar uma unidade de cada vez.</p></div>
              <v-switch v-model="manualQuantity" color="primary" inset density="compact" hide-details aria-label="Ativar quantidade manual" />
            </div>
            <v-divider />
            <div class="admin-option-row">
              <div><b>Ignorar mínimo da encomenda</b><p>Permite confirmar abaixo do mínimo de {{ money(minimumTotal) }}.</p></div>
              <v-switch v-model="ignoreMinimum" color="warning" inset density="compact" hide-details aria-label="Ignorar mínimo da encomenda" />
            </div>
          </div>
          <div class="d-flex justify-space-between mb-3"><span class="text-medium-emphasis">Unidades</span><b>{{ cart.cart.units }}</b></div>
          <div class="d-flex justify-space-between mb-5"><span class="text-medium-emphasis">Subtotal</span><b>{{ money(cart.cart.subtotal) }}</b></div>
          <v-divider />
          <div class="d-flex justify-space-between my-5 text-h6"><span>Total</span><b>{{ money(cart.cart.total) }}</b></div>
          <v-alert v-if="!meetsMinimum && auth.isAdmin && ignoreMinimum" type="info" variant="tonal" density="compact" class="mb-4">Exceção administrativa ativa. Esta encomenda pode ser confirmada abaixo do mínimo de {{ money(minimumTotal) }}.</v-alert>
          <v-alert v-else-if="!meetsMinimum" type="warning" variant="tonal" density="compact" class="mb-4">Mínimo de {{ money(minimumTotal) }} para {{ catalogLabel }}. Faltam <b>{{ money(remaining) }}</b>.</v-alert>
          <v-alert v-else type="success" variant="tonal" density="compact" class="mb-4">Mínimo de {{ money(minimumTotal) }} atingido.</v-alert>
          <v-textarea v-model="notes" label="Notas internas da encomenda" hint="Visíveis apenas na gestão da encomenda." persistent-hint rows="3" />
          <v-switch v-model="includePdfNotes" color="secondary" label="Incluir observações no PDF" hide-details class="mt-2" />
          <v-expand-transition><v-textarea v-if="includePdfNotes" v-model="pdfNotes" label="Observações a mostrar no PDF" rows="3" class="mt-2" /></v-expand-transition>
          <v-btn block color="primary" size="large" :disabled="!minimumSatisfied || (auth.isAdmin && orderForSomeoneElse && !selectedCustomer)" :loading="submitting" @click="submit">Confirmar encomenda {{ catalogLabel }}</v-btn>
        </v-card>
      </v-col>
    </v-row>
    <div v-else class="empty-state"><v-icon size="64">mdi-cart-outline</v-icon><div class="text-h5 font-weight-bold mt-4">O carrinho {{ catalogLabel }} está vazio</div><p>Escolha produtos no catálogo {{ catalogLabel }} para criar uma encomenda.</p><v-btn :to="`/catalogo/${publicCatalogSlug}`" color="primary" class="mt-2">Abrir catálogo {{ catalogLabel }}</v-btn></div>
  </div>
</template>

<style scoped>
.catalog-cart-switch { display: flex; flex-wrap: wrap; gap: 10px; }
.cart-line-actions { align-items: center; display: flex; gap: 12px; }
.quantity-control { align-items: center; display: flex; gap: 10px; }
.quantity-control b { min-width: 30px; text-align: center; }
.cart-quantity-field { flex: 0 0 82px; width: 82px; }
.cart-quantity-field :deep(input) { font-size: 1rem; font-variant-numeric: tabular-nums; font-weight: 800; padding-inline: 6px; text-align: center; }
.cart-quantity-field :deep(input::-webkit-inner-spin-button), .cart-quantity-field :deep(input::-webkit-outer-spin-button) { appearance: none; margin: 0; }
.cart-quick-quantities { display: flex; flex-wrap: wrap; gap: 4px; justify-content: flex-end; }
.cart-quick-quantities :deep(.v-btn) { min-height: 44px; min-width: 48px; }
.line-total { font-variant-numeric: tabular-nums; width: 92px; }
.original-line-total { color: rgba(var(--v-theme-on-surface), .52); display: block; text-decoration: line-through; }
.gift-line { background: rgba(var(--v-theme-success), .045); }
.order-owner { background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-theme-primary), .16); border-radius: 14px; box-shadow: none; }
.order-owner :deep(.v-selection-control__input::before) { background-color: rgb(var(--v-theme-primary)); }
.order-owner-current { align-items: center; background: rgba(var(--v-theme-success), .09); border-radius: 10px; display: flex; gap: 8px; margin: 0 12px 12px; padding: 10px 12px; }
.admin-options { background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-theme-primary), .16); border-radius: 14px; overflow: hidden; }
.admin-options-title { align-items: center; display: flex; font-size: .875rem; font-weight: 700; gap: 8px; padding: 12px 14px 4px; }
.admin-option-row { align-items: center; display: flex; gap: 12px; justify-content: space-between; min-width: 0; padding: 12px 14px; }
.admin-option-row > div { min-width: 0; }
.admin-option-row p { color: rgba(var(--v-theme-on-surface), .62); font-size: .75rem; line-height: 1.45; margin: 3px 0 0; }
.admin-option-row :deep(.v-switch) { flex: 0 0 auto; margin: 0; }
@media (max-width: 700px) {
  .cart-line-actions { align-items: flex-end; flex-direction: column; }
  .line-total { width: auto; }
  .admin-option-row { align-items: flex-start; }
}
</style>
