<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'
import VirtualProductPicker from '../components/VirtualProductPicker.vue'

const feedback = useFeedbackStore()
const promotions = ref([])
const products = ref([])
const catalogs = ref([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const productPicker = ref(false)
const brandPicker = ref(false)
const giftPicker = ref(false)
const giftTierIndex = ref(0)
const giftManager = ref(false)
const giftCreate = ref(false)
const productSearch = ref('')
const brandSearch = ref('')
const giftSearch = ref('')
const giftFile = ref(null)
const creatingGift = ref(false)
const uploadingGiftRef = ref('')
const editingId = ref(null)
const search = ref('')
const form = reactive(emptyForm())
const giftForm = reactive(emptyGiftForm())

function emptyTier(conditionType = 'quantity') { return { minimum_threshold: conditionType === 'quantity' ? '1' : '100.00', maximum_threshold: '', gift_product_ref: null, gift_quantity: 1 } }
function emptyForm() {
  return { title: '', description: '', catalog_slug: 'villas', eligibility_mode: 'products', eligible_brands: [], condition_type: 'quantity', product_refs: [], tiers: [emptyTier()], max_redemptions_per_user: 1, active: false, starts_at: '', ends_at: '' }
}
function emptyGiftForm() { return { ref: '', catalog_slug: 'villas', name: '', product_type: 'Oferta', price: '0.00', active: true } }
function localDate(value) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
function apiDate(value) { return value ? new Date(value).toISOString() : null }
function money(value) { return Number(value || 0).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' }) }
const catalogOptions = computed(() => catalogs.value.map(item => ({ title: item.label, value: item.slug })))
const catalogProducts = computed(() => products.value.filter(item => item.catalogSlug === form.catalog_slug))
const eligibleOptions = computed(() => products.value.filter(item => item.ref !== form.gift_product_ref && !item.giftOnly))
const brandOptions = computed(() => [...new Set(catalogProducts.value.filter(item => !item.giftOnly && item.brand?.trim()).map(item => item.brand.trim()))].sort((a, b) => a.localeCompare(b, 'pt')))
const visibleBrandOptions = computed(() => { const value = brandSearch.value.trim().toLocaleLowerCase('pt'); return brandOptions.value.filter(brand => !value || brand.toLocaleLowerCase('pt').includes(value)) })
const giftOptions = computed(() => catalogProducts.value.filter(item => item.giftOnly && !form.product_refs.includes(item.ref)))
const selectedProducts = computed(() => form.product_refs.map(ref => products.value.find(item => item.ref === ref)).filter(Boolean))
const giftProducts = computed(() => products.value.filter(item => item.giftOnly))
const visibleEligibleOptions = computed(() => { const value = productSearch.value.trim().toLowerCase(); return eligibleOptions.value.filter(item => !value || `${item.ref} ${item.name} ${item.type} ${item.categoryLabel} ${item.brand}`.toLowerCase().includes(value)) })
const visibleGiftOptions = computed(() => { const value = giftSearch.value.trim().toLowerCase(); return giftOptions.value.filter(item => !value || `${item.ref} ${item.name} ${item.type}`.toLowerCase().includes(value)) })
const filteredPromotions = computed(() => {
  const value = search.value.trim().toLowerCase()
  return value ? promotions.value.filter(item => `${item.title} ${item.giftProduct?.name} ${item.productRefs.join(' ')} ${(item.eligibleBrands || []).join(' ')}`.toLowerCase().includes(value)) : promotions.value
})
const previewText = computed(() => {
  const criteria = form.eligibility_mode === 'brands' ? `nas marcas ${form.eligible_brands.join(', ') || 'a selecionar'}` : `nos ${form.product_refs.length} produtos escolhidos`
  const rules = form.tiers.map((tier, index) => {
    const gift = tierGiftProduct(tier)
    return `${index + 1}. ${tierRangeLabel(tier, form.condition_type)}: ${Number(tier.gift_quantity || 1)} × ${gift?.name || 'produto de oferta'}`
  }).join(' · ')
  const limit = Number(form.max_redemptions_per_user || 1)
  return `${criteria}: ${rules}. Cada cliente pode receber uma oferta desta promoção até ${limit} ${limit === 1 ? 'vez' : 'vezes'}.`
})

async function load() {
  loading.value = true
  try {
    const [promotionResult, catalogResult] = await Promise.all([api.get('/admin/gift-promotions'), api.get('/admin/catalog')])
    promotions.value = promotionResult.data.promotions || []
    products.value = catalogResult.data.products || []
    catalogs.value = catalogResult.data.catalogs || []
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
function createPromotion() { editingId.value = null; Object.assign(form, emptyForm()); dialog.value = true }
function editPromotion(item) {
  editingId.value = item.id
  const tiers = item.tiers?.length ? item.tiers.map(tier => ({ minimum_threshold: tier.minimumThreshold, maximum_threshold: tier.maximumThreshold || '', gift_product_ref: tier.giftProductRef, gift_quantity: tier.giftQuantity })) : [{ minimum_threshold: item.conditionType === 'quantity' ? String(item.thresholdQuantity || 1) : item.thresholdValue, maximum_threshold: '', gift_product_ref: item.giftProductRef, gift_quantity: item.giftQuantity }]
  Object.assign(form, { title: item.title, description: item.description, catalog_slug: item.catalogSlug, eligibility_mode: item.eligibilityMode || 'products', eligible_brands: [...(item.eligibleBrands || [])], condition_type: item.conditionType, product_refs: [...item.productRefs], tiers, max_redemptions_per_user: item.maxRedemptionsPerUser || 1, active: item.active, starts_at: localDate(item.startsAt), ends_at: localDate(item.endsAt) })
  dialog.value = true
}
function payload(active = form.active) {
  const tiers = form.tiers.map(tier => ({ minimum_threshold: String(tier.minimum_threshold), maximum_threshold: tier.maximum_threshold === '' || tier.maximum_threshold == null ? null : String(tier.maximum_threshold), gift_product_ref: tier.gift_product_ref, gift_quantity: Number(tier.gift_quantity) }))
  const first = tiers[0] || {}
  return { ...form, tiers, active, starts_at: apiDate(form.starts_at), ends_at: apiDate(form.ends_at), threshold_quantity: form.condition_type === 'quantity' ? Number(first.minimum_threshold) : null, threshold_value: form.condition_type === 'value' ? String(first.minimum_threshold) : null, gift_product_ref: first.gift_product_ref || null, gift_quantity: Number(first.gift_quantity || 1), max_redemptions_per_user: Number(form.max_redemptions_per_user) }
}
async function save() {
  const hasCriteria = form.eligibility_mode === 'brands' ? form.eligible_brands.length : form.product_refs.length
  const validTiers = form.tiers.length && form.tiers.every(tier => Number(tier.minimum_threshold) > 0 && tier.gift_product_ref && Number(tier.gift_quantity) > 0 && (!tier.maximum_threshold || Number(tier.maximum_threshold) > Number(tier.minimum_threshold)))
  if (!form.title.trim() || !hasCriteria || !validTiers) return feedback.show(`Indique o nome, ${form.eligibility_mode === 'brands' ? 'as marcas' : 'os produtos elegíveis'} e complete todos os escalões de oferta.`, 'warning')
  saving.value = true
  try {
    if (editingId.value) await api.put(`/admin/gift-promotions/${editingId.value}`, payload())
    else await api.post('/admin/gift-promotions', payload())
    dialog.value = false
    await load()
    feedback.show('Promoção de oferta guardada.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function toggle(item, active) {
  const previous = item.active; item.active = active
  try {
    await api.put(`/admin/gift-promotions/${item.id}`, { title: item.title, description: item.description, catalog_slug: item.catalogSlug, eligibility_mode: item.eligibilityMode || 'products', eligible_brands: item.eligibleBrands || [], condition_type: item.conditionType, threshold_quantity: item.thresholdQuantity, threshold_value: item.thresholdValue, product_refs: item.productRefs, gift_product_ref: item.giftProductRef, gift_quantity: item.giftQuantity, tiers: (item.tiers || []).map(tier => ({ minimum_threshold: tier.minimumThreshold, maximum_threshold: tier.maximumThreshold, gift_product_ref: tier.giftProductRef, gift_quantity: tier.giftQuantity })), max_redemptions_per_user: item.maxRedemptionsPerUser || 1, active, starts_at: item.startsAt, ends_at: item.endsAt })
    await load(); feedback.show(active ? 'Promoção ativada.' : 'Promoção desativada.')
  } catch (error) { item.active = previous; feedback.show(errorMessage(error), 'error') }
}
async function remove(item) {
  if (!await feedback.confirm(`Eliminar a promoção “${item.title}”? O histórico de ofertas desta regra também será removido.`, 'Eliminar promoção')) return
  try { await api.delete(`/admin/gift-promotions/${item.id}`); await load(); feedback.show('Promoção eliminada.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}
function conditionLabel(item) { const count = item.tiers?.length || 1; return `${count} ${count === 1 ? 'escalão' : 'escalões'} por ${item.conditionType === 'quantity' ? 'quantidade' : 'valor'}` }
function eligibilityLabel(item) { return item.eligibilityMode === 'brands' ? `Marcas: ${(item.eligibleBrands || []).join(', ')}` : `${item.productRefs.length} referências selecionadas` }
function promotionTiers(item) { return item.tiers?.length ? item.tiers : [{ minimumThreshold: item.conditionType === 'quantity' ? item.thresholdQuantity : item.thresholdValue, maximumThreshold: null, giftProduct: item.giftProduct, giftProductRef: item.giftProductRef, giftQuantity: item.giftQuantity }] }
function toggleSelectedProduct(ref) {
  const product = products.value.find(item => item.ref === ref)
  if (!product || product.catalogSlug !== form.catalog_slug) return
  form.product_refs = form.product_refs.includes(ref) ? form.product_refs.filter(value => value !== ref) : [...form.product_refs, ref]
}
function toggleSelectedBrand(brand) { form.eligible_brands = form.eligible_brands.includes(brand) ? form.eligible_brands.filter(value => value !== brand) : [...form.eligible_brands, brand] }
function resetCatalogSelection() { form.product_refs = []; form.eligible_brands = []; form.tiers = form.tiers.map(tier => ({ ...tier, gift_product_ref: null })) }
function tierGiftProduct(tier) { return products.value.find(item => item.ref === tier?.gift_product_ref) || null }
function tierRangeLabel(tier, conditionType) {
  const minimum = conditionType === 'quantity' ? `${Number(tier.minimum_threshold || 0)} un.` : money(tier.minimum_threshold)
  if (!tier.maximum_threshold) return `${minimum} ou mais`
  const maximum = conditionType === 'quantity' ? `${Number(tier.maximum_threshold)} un.` : money(tier.maximum_threshold)
  return `${minimum} até menos de ${maximum}`
}
function openGiftPicker(index) { giftTierIndex.value = index; giftSearch.value = ''; giftPicker.value = true }
function chooseGift(ref) { if (form.tiers[giftTierIndex.value]) form.tiers[giftTierIndex.value].gift_product_ref = ref; giftPicker.value = false }
function addTier() { form.tiers.push(emptyTier(form.condition_type)) }
function removeTier(index) { if (form.tiers.length > 1) form.tiers.splice(index, 1) }
function resetTierThresholds() { form.tiers = form.tiers.map((tier, index) => ({ ...tier, minimum_threshold: index === 0 ? (form.condition_type === 'quantity' ? '1' : '100.00') : '', maximum_threshold: '' })) }
function openGiftCreate() { Object.assign(giftForm, emptyGiftForm(), { catalog_slug: form.catalog_slug || 'villas' }); giftFile.value = null; giftCreate.value = true }
async function createGiftProduct() {
  if (!giftForm.ref.trim() || !giftForm.name.trim()) return feedback.show('Indique a referência e o nome do produto de oferta.', 'warning')
  creatingGift.value = true
  try {
    const transaction = new FormData()
    transaction.append('payload', JSON.stringify({ ...giftForm, category_slug: null, brand: null, family: null, ean: null, price_base: null, eco_value: '0.000', pvp: null, case_inner: null, case_outer: null, colors: [], sizes: [], season: 'ambos', quantity_step: 1, quick_quantities: [], sort_order: 0, manual_active: true, gift_only: true, description: 'Produto exclusivo para ofertas automáticas.' }))
    const file = Array.isArray(giftFile.value) ? giftFile.value[0] : giftFile.value
    if (file) transaction.append('image', file)
    await api.post('/admin/products/save', transaction)
    giftCreate.value = false
    await load()
    feedback.show('Produto de oferta criado.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { creatingGift.value = false }
}
async function updateGiftImage(product, value) {
  const file = Array.isArray(value) ? value[0] : value
  if (!file) return
  uploadingGiftRef.value = product.ref
  try {
    const transaction = new FormData()
    transaction.append('image', file)
    await api.post(`/admin/products/${encodeURIComponent(product.ref)}/image`, transaction)
    await load()
    feedback.show(`Fotografia de “${product.name}” atualizada.`)
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { uploadingGiftRef.value = '' }
}

onMounted(load)
</script>

<template>
  <div class="page gift-promotions-page">
    <div class="page-head"><div><h1>Promoções com oferta</h1><p>Crie regras automáticas por marcas ou referências e defina quantas vezes cada cliente pode receber.</p></div><div class="d-flex flex-wrap ga-2"><v-btn variant="tonal" prepend-icon="mdi-gift-open-outline" @click="giftManager = true">Produtos de oferta</v-btn><v-btn color="primary" prepend-icon="mdi-plus" @click="createPromotion">Nova promoção</v-btn></div></div>
    <v-card class="soft-card pa-4 mb-5"><v-text-field v-model="search" label="Pesquisar promoção, produto ou referência" prepend-inner-icon="mdi-magnify" clearable hide-details /></v-card>
    <v-progress-linear v-if="loading" indeterminate color="secondary" class="mb-4" />
    <div v-if="!loading && filteredPromotions.length" class="promotion-grid">
      <v-card v-for="item in filteredPromotions" :key="item.id" class="soft-card pa-5 promotion-card">
        <div class="d-flex align-start justify-space-between ga-4"><div><div class="d-flex flex-wrap align-center ga-2"><h2 class="text-h6">{{ item.title }}</h2><v-chip size="small" :color="item.currentlyActive ? 'success' : item.active ? 'warning' : 'grey'" variant="tonal">{{ item.currentlyActive ? 'Ativa' : item.active ? 'Agendada' : 'Inativa' }}</v-chip></div><p v-if="item.description" class="text-body-2 text-medium-emphasis mt-1">{{ item.description }}</p></div><v-switch :model-value="item.active" color="success" hide-details :aria-label="`Ativar ${item.title}`" @update:model-value="toggle(item, $event)" /></div>
        <div class="promotion-rule-title my-4"><v-icon>mdi-chart-timeline-variant-shimmer</v-icon><span>{{ conditionLabel(item) }}</span></div>
        <div class="tier-summary-list mb-4">
          <div v-for="tier in promotionTiers(item)" :key="tier.id || `${tier.minimumThreshold}-${tier.giftProductRef}`" class="tier-summary-row">
            <div class="tier-summary-range"><span>{{ tierRangeLabel({ minimum_threshold: tier.minimumThreshold, maximum_threshold: tier.maximumThreshold }, item.conditionType) }}</span></div>
            <v-icon class="flow-arrow" aria-hidden="true">mdi-arrow-right</v-icon>
            <div class="tier-summary-gift">
              <v-avatar rounded="lg" size="72" color="grey-lighten-4"><v-img v-if="tier.giftProduct?.imageUrl" :src="tier.giftProduct.imageUrl" :alt="tier.giftProduct.name" contain /><v-icon v-else size="34">mdi-gift-outline</v-icon></v-avatar>
              <span><b>{{ tier.giftQuantity }} × {{ tier.giftProduct?.name || 'Oferta' }}</b><small>{{ tier.giftProductRef }}</small></span>
            </div>
          </div>
        </div>
        <div class="text-caption text-medium-emphasis mb-3">{{ eligibilityLabel(item) }} · catálogo {{ item.giftProduct?.catalogLabel }} · máximo {{ item.maxRedemptionsPerUser }} {{ item.maxRedemptionsPerUser === 1 ? 'vez' : 'vezes' }} por cliente</div>
        <v-expansion-panels v-if="item.redemptionCount" variant="accordion" class="mb-3"><v-expansion-panel><v-expansion-panel-title><v-icon class="mr-2">mdi-account-check-outline</v-icon>{{ item.redemptionCount }} oferta{{ item.redemptionCount === 1 ? '' : 's' }} atribuída{{ item.redemptionCount === 1 ? '' : 's' }} a {{ item.recipientCount }} cliente{{ item.recipientCount === 1 ? '' : 's' }}</v-expansion-panel-title><v-expansion-panel-text><v-list density="compact"><v-list-item v-for="entry in item.redemptions" :key="entry.id" :title="entry.customerName" :subtitle="`${entry.companyName || 'Cliente'} · encomenda ${entry.orderNumber}`"><template #append><span class="text-caption">{{ new Date(entry.createdAt).toLocaleDateString('pt-PT') }}</span></template></v-list-item></v-list></v-expansion-panel-text></v-expansion-panel></v-expansion-panels>
        <div class="d-flex justify-end ga-2"><v-btn variant="tonal" prepend-icon="mdi-pencil-outline" @click="editPromotion(item)">Editar</v-btn><v-btn variant="text" color="error" icon="mdi-delete-outline" :aria-label="`Eliminar ${item.title}`" @click="remove(item)" /></div>
      </v-card>
    </div>
    <div v-else-if="!loading" class="empty-state"><v-icon size="64">mdi-gift-outline</v-icon><div class="text-h5 font-weight-bold mt-3">Ainda não existem promoções com oferta</div><p>Crie uma regra e escolha os produtos, o objetivo e o artigo oferecido.</p><v-btn color="primary" class="mt-2" @click="createPromotion">Criar promoção</v-btn></div>

    <v-dialog v-model="dialog" max-width="1050" persistent><v-card><v-card-title class="pa-6 pb-2">{{ editingId ? 'Editar promoção' : 'Nova promoção com oferta' }}</v-card-title><v-card-text class="pa-6"><v-row density="comfortable">
      <v-col cols="12" md="8"><v-text-field v-model="form.title" label="Nome da promoção" maxlength="160" /></v-col><v-col cols="12" md="4"><v-select v-model="form.catalog_slug" :items="catalogOptions" label="Catálogo" :disabled="Boolean(editingId)" @update:model-value="resetCatalogSelection" /></v-col>
      <v-col cols="12"><v-textarea v-model="form.description" label="Descrição interna" rows="2" hint="Ajuda a identificar o objetivo desta promoção." persistent-hint /></v-col>
      <v-col cols="12"><div class="section-label">1. Artigos que contam para a promoção</div><v-btn-toggle v-model="form.eligibility_mode" mandatory color="primary" divided class="eligibility-toggle mb-4"><v-btn value="products" prepend-icon="mdi-barcode-scan">Referências</v-btn><v-btn value="brands" prepend-icon="mdi-tag-multiple-outline">Marcas</v-btn></v-btn-toggle><div v-if="form.eligibility_mode === 'products'" class="selection-box"><div><b>{{ form.product_refs.length ? `${form.product_refs.length} produtos selecionados` : 'Nenhum produto selecionado' }}</b><p>A quantidade ou o valor é somado apenas nestas referências.</p></div><v-btn color="primary" variant="tonal" prepend-icon="mdi-view-grid-plus-outline" @click="productSearch = ''; productPicker = true">Selecionar produtos</v-btn></div><div v-else class="selection-box"><div><b>{{ form.eligible_brands.length ? `${form.eligible_brands.length} marcas selecionadas` : 'Nenhuma marca selecionada' }}</b><p>Todos os produtos atuais e futuros destas marcas contam automaticamente.</p></div><v-btn color="primary" variant="tonal" prepend-icon="mdi-tag-plus-outline" @click="brandSearch = ''; brandPicker = true">Selecionar marcas</v-btn></div><div v-if="form.eligibility_mode === 'products' && selectedProducts.length" class="selected-product-strip"><div v-for="product in selectedProducts.slice(0, 8)" :key="product.ref" class="selected-product"><v-img v-if="product.imageUrl" :src="product.imageUrl" cover /><v-icon v-else>mdi-package-variant</v-icon><span>{{ product.name }}</span><v-btn icon="mdi-close" size="x-small" variant="text" :aria-label="`Remover ${product.name}`" @click="toggleSelectedProduct(product.ref)" /></div><div v-if="selectedProducts.length > 8" class="selected-more">+{{ selectedProducts.length - 8 }}</div></div><div v-if="form.eligibility_mode === 'brands' && form.eligible_brands.length" class="selected-brand-strip"><v-chip v-for="brand in form.eligible_brands" :key="brand" closable color="primary" variant="tonal" @click:close="toggleSelectedBrand(brand)">{{ brand }}</v-chip></div></v-col>
      <v-col cols="12"><div class="section-label">2. Forma de calcular</div><v-btn-toggle v-model="form.condition_type" mandatory color="primary" divided class="mb-2" @update:model-value="resetTierThresholds"><v-btn value="quantity" prepend-icon="mdi-counter">Quantidade</v-btn><v-btn value="value" prepend-icon="mdi-currency-eur">Valor</v-btn></v-btn-toggle><p class="picker-help">A soma considera apenas os artigos ou marcas selecionados acima.</p></v-col>
      <v-col cols="12"><div class="section-label">3. Escalões e ofertas</div><div class="tier-editor-list">
        <div v-for="(tier, index) in form.tiers" :key="index" class="tier-editor-card">
          <div class="tier-editor-head"><div><b>Escalão {{ index + 1 }}</b><span>{{ tierRangeLabel(tier, form.condition_type) }}</span></div><v-btn v-if="form.tiers.length > 1" icon="mdi-delete-outline" size="small" variant="text" color="error" :aria-label="`Remover escalão ${index + 1}`" @click="removeTier(index)" /></div>
          <div class="tier-editor-grid">
            <v-text-field v-model="tier.minimum_threshold" type="number" :inputmode="form.condition_type === 'quantity' ? 'numeric' : 'decimal'" min="1" :step="form.condition_type === 'quantity' ? '1' : '0.01'" label="A partir de" :suffix="form.condition_type === 'quantity' ? 'un.' : '€'" />
            <v-text-field v-model="tier.maximum_threshold" type="number" :inputmode="form.condition_type === 'quantity' ? 'numeric' : 'decimal'" min="1" :step="form.condition_type === 'quantity' ? '1' : '0.01'" label="Até (opcional)" :suffix="form.condition_type === 'quantity' ? 'un.' : '€'" hint="Este valor inicia o escalão seguinte; não é incluído neste." persistent-hint />
            <v-text-field v-model.number="tier.gift_quantity" type="number" inputmode="numeric" min="1" max="1000" label="Qtd. oferecida" />
          </div>
          <div class="tier-gift-choice">
            <template v-if="tierGiftProduct(tier)"><v-avatar rounded="lg" size="88" color="grey-lighten-4"><v-img v-if="tierGiftProduct(tier).imageUrl" :src="tierGiftProduct(tier).imageUrl" :alt="tierGiftProduct(tier).name" contain /><v-icon v-else size="40">mdi-gift-outline</v-icon></v-avatar><div class="gift-choice-text"><b>{{ tierGiftProduct(tier).name }}</b><span>{{ tierGiftProduct(tier).ref }}</span></div></template><div v-else class="gift-choice-text"><b>Escolha o produto oferecido</b><span>A imagem e os dados aparecerão aqui.</span></div><v-btn variant="tonal" color="success" @click="openGiftPicker(index)">{{ tier.gift_product_ref ? 'Alterar oferta' : 'Escolher oferta' }}</v-btn>
          </div>
        </div>
      </div><v-btn variant="tonal" color="primary" prepend-icon="mdi-plus" class="mt-3" @click="addTier">Adicionar escalão</v-btn></v-col>
      <v-col cols="12" md="6"><v-text-field v-model.number="form.max_redemptions_per_user" type="number" inputmode="numeric" min="1" max="1000" label="Máximo por cliente" hint="Número de vezes que cada cliente pode receber uma oferta desta promoção." persistent-hint /></v-col>
      <v-col cols="12" md="6"><v-text-field v-model="form.starts_at" type="datetime-local" label="Início (opcional)" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.ends_at" type="datetime-local" label="Fim (opcional)" /></v-col>
      <v-col cols="12"><v-alert type="info" variant="tonal" icon="mdi-eye-outline" title="Pré-visualização da regra">{{ previewText }}</v-alert></v-col>
      <v-col cols="12"><v-switch v-model="form.active" color="success" inset label="Ativar esta promoção" hint="Pode guardar desativada e ativar mais tarde." persistent-hint /></v-col>
    </v-row></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="dialog = false">Cancelar</v-btn><v-btn color="primary" :loading="saving" prepend-icon="mdi-content-save-outline" @click="save">Guardar promoção</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="productPicker" max-width="1180"><v-card><v-card-title class="pa-6 pb-2">Selecionar produtos</v-card-title><v-card-text class="pa-6"><p class="picker-help mb-4">Estão visíveis todos os artigos do site. Para esta promoção pode selecionar os do catálogo <b>{{ catalogs.find(item => item.slug === form.catalog_slug)?.label }}</b>.</p><v-text-field v-model="productSearch" label="Pesquisar nome, referência, categoria ou marca" prepend-inner-icon="mdi-magnify" clearable autofocus class="mb-4" /><div class="picker-count mb-3">{{ form.product_refs.length }} selecionados · {{ visibleEligibleOptions.length }} encontrados</div><VirtualProductPicker :products="visibleEligibleOptions" :selected="form.product_refs" :allowed-catalog="form.catalog_slug" @select="toggleSelectedProduct" /></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn color="primary" @click="productPicker = false">Concluir seleção</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="brandPicker" max-width="760"><v-card><v-card-title class="pa-6 pb-2">Selecionar marcas</v-card-title><v-card-text class="pa-6"><p class="picker-help mb-4">A regra incluirá automaticamente todas as referências destas marcas no catálogo <b>{{ catalogs.find(item => item.slug === form.catalog_slug)?.label }}</b>.</p><v-text-field v-model="brandSearch" label="Pesquisar marca" prepend-inner-icon="mdi-magnify" clearable autofocus class="mb-4" /><div class="picker-count mb-3">{{ form.eligible_brands.length }} selecionadas · {{ visibleBrandOptions.length }} encontradas</div><div class="brand-picker-grid"><button v-for="brand in visibleBrandOptions" :key="brand" type="button" class="brand-picker-card" :class="{ selected: form.eligible_brands.includes(brand) }" :aria-pressed="form.eligible_brands.includes(brand)" @click="toggleSelectedBrand(brand)"><v-icon>{{ form.eligible_brands.includes(brand) ? 'mdi-check-circle' : 'mdi-tag-outline' }}</v-icon><span>{{ brand }}</span></button></div><div v-if="!visibleBrandOptions.length" class="empty-picker"><v-icon size="48">mdi-tag-search-outline</v-icon><p>Não foram encontradas marcas neste catálogo.</p></div></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn color="primary" @click="brandPicker = false">Concluir seleção</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="giftPicker" max-width="1100"><v-card><v-card-title class="pa-6 pb-2">Escolher produto de oferta · Escalão {{ giftTierIndex + 1 }}</v-card-title><v-card-text class="pa-6"><v-text-field v-model="giftSearch" label="Pesquisar produto de oferta" prepend-inner-icon="mdi-magnify" clearable class="mb-4" /><VirtualProductPicker v-if="visibleGiftOptions.length" :products="visibleGiftOptions" :selected-one="form.tiers[giftTierIndex]?.gift_product_ref || ''" single gift @select="chooseGift" /><div v-else class="empty-picker"><v-icon size="48">mdi-gift-outline</v-icon><p>Ainda não existem produtos de oferta neste catálogo.</p><v-btn color="primary" @click="giftPicker = false; openGiftCreate()">Criar produto de oferta</v-btn></div></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="giftPicker = false">Fechar</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="giftManager" max-width="1180"><v-card><v-card-title class="pa-6 pb-2 d-flex align-center"><span>Produtos de oferta</span><v-spacer /><v-btn color="primary" prepend-icon="mdi-plus" @click="openGiftCreate">Adicionar produto de oferta</v-btn></v-card-title><v-card-text class="pa-6"><p class="text-body-2 text-medium-emphasis mb-5">Cada produto pode ter a sua própria fotografia. Estes artigos ficam disponíveis nas promoções, mas nunca aparecem nos catálogos dos clientes.</p><div v-if="giftProducts.length" class="gift-manager-grid"><div v-for="product in giftProducts" :key="product.ref" class="gift-manager-card"><div class="gift-manager-image"><v-img v-if="product.imageUrl" :src="product.imageUrl" :alt="product.name" contain /><v-icon v-else size="48">mdi-gift-outline</v-icon></div><div class="pa-3"><b>{{ product.name }}</b><div class="text-caption text-medium-emphasis mb-3">{{ product.ref }} · {{ product.catalogLabel }}</div><v-file-input :model-value="null" accept="image/*,.heic,.heif,.tif,.tiff,.bmp,.gif" density="compact" variant="outlined" prepend-icon="" prepend-inner-icon="mdi-camera-outline" :label="product.imageUrl ? 'Substituir fotografia' : 'Adicionar fotografia'" :loading="uploadingGiftRef === product.ref" :disabled="Boolean(uploadingGiftRef)" hide-details @update:model-value="updateGiftImage(product, $event)" /></div></div></div><div v-else class="empty-picker"><v-icon size="56">mdi-gift-open-outline</v-icon><p>Ainda não existem produtos exclusivos para ofertas.</p></div></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="giftManager = false">Fechar</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="giftCreate" max-width="760" persistent><v-card><v-card-title class="pa-6 pb-2">Novo produto de oferta</v-card-title><v-card-text class="pa-6"><v-row><v-col cols="12" md="4"><v-select v-model="giftForm.catalog_slug" :items="catalogOptions" label="Catálogo" /></v-col><v-col cols="12" md="4"><v-text-field v-model.trim="giftForm.ref" label="Referência" /></v-col><v-col cols="12" md="4"><v-text-field v-model.trim="giftForm.product_type" label="Tipo" /></v-col><v-col cols="12" md="8"><v-text-field v-model.trim="giftForm.name" label="Nome do produto" /></v-col><v-col cols="12" md="4"><v-text-field v-model="giftForm.price" type="number" min="0" step="0.01" label="Valor de referência" suffix="€" /></v-col><v-col cols="12"><v-file-input v-model="giftFile" accept="image/*,.heic,.heif,.tif,.tiff,.bmp,.gif" label="Imagem do produto de oferta" prepend-icon="mdi-camera-outline" hint="Será otimizada automaticamente como as restantes imagens de produto." persistent-hint /></v-col><v-col cols="12"><v-alert type="info" variant="tonal" density="compact">Este produto será marcado automaticamente como exclusivo para ofertas e ficará invisível nos catálogos dos clientes.</v-alert></v-col></v-row></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="giftCreate = false">Cancelar</v-btn><v-btn color="primary" :loading="creatingGift" @click="createGiftProduct">Criar produto</v-btn></v-card-actions></v-card></v-dialog>
  </div>
</template>

<style scoped>
.promotion-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 430px), 1fr)); }
.promotion-card { display: flex; flex-direction: column; }
.promotion-rule-title { align-items: center; color: rgb(var(--v-theme-primary)); display: flex; font-size: .82rem; font-weight: 800; gap: 8px; }
.tier-summary-list { border: 1px solid rgba(var(--v-theme-primary), .12); border-radius: 14px; overflow: hidden; }
.tier-summary-row { align-items: center; background: rgba(var(--v-theme-primary), .025); border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: grid; gap: 12px; grid-template-columns: minmax(130px, .8fr) 24px minmax(190px, 1.2fr); padding: 12px; }
.tier-summary-row:last-child { border-bottom: 0; }
.tier-summary-range { color: rgb(var(--v-theme-primary)); font-size: .82rem; font-weight: 800; }
.tier-summary-gift { align-items: center; display: flex; gap: 12px; min-width: 0; }
.tier-summary-gift .v-avatar { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); flex: 0 0 auto; }
.tier-summary-gift > span { display: flex; flex-direction: column; min-width: 0; }
.tier-summary-gift b { font-size: .84rem; overflow-wrap: anywhere; }
.tier-summary-gift small { color: rgba(var(--v-theme-on-surface), .56); font-size: .7rem; }
.flow-arrow { color: rgba(var(--v-theme-on-surface), .42); flex: 0 0 auto; }
.section-label { color: rgb(var(--v-theme-primary)); font-size: .78rem; font-weight: 800; letter-spacing: .05em; margin-bottom: 10px; text-transform: uppercase; }
.eligibility-toggle { min-height: 44px; }
.selection-box { align-items: center; border: 1px solid rgba(var(--v-theme-primary), .18); border-radius: 14px; display: flex; gap: 18px; justify-content: space-between; padding: 14px 16px; }
.selection-box p { color: rgba(var(--v-theme-on-surface), .62); font-size: .8rem; margin: 3px 0 0; }
.selected-product-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
.selected-brand-strip { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.selected-product { align-items: center; background: rgba(var(--v-theme-primary), .06); border-radius: 10px; display: flex; gap: 7px; max-width: 240px; min-height: 44px; padding: 5px 7px; }
.selected-product :deep(.v-img) { border-radius: 7px; flex: 0 0 34px; height: 34px; width: 34px; }.selected-product span { font-size: .75rem; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.selected-more { align-items: center; display: flex; font-weight: 800; padding: 0 8px; }
.gift-choice { align-items: center; border: 1px solid rgba(var(--v-theme-success), .24); border-radius: 14px; display: flex; gap: 12px; min-height: 86px; padding: 10px; }.gift-choice-text { display: flex; flex: 1 1 auto; flex-direction: column; min-width: 0; }.gift-choice-text b, .gift-choice-text span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.gift-choice-text span { color: rgba(var(--v-theme-on-surface), .6); font-size: .75rem; }
.tier-editor-list { display: flex; flex-direction: column; gap: 14px; }
.tier-editor-card { background: rgba(var(--v-theme-primary), .025); border: 1px solid rgba(var(--v-theme-primary), .16); border-radius: 16px; padding: 16px; }
.tier-editor-head { align-items: center; display: flex; justify-content: space-between; margin-bottom: 14px; }
.tier-editor-head > div { display: flex; flex-direction: column; }
.tier-editor-head b { font-size: .95rem; }
.tier-editor-head span { color: rgba(var(--v-theme-on-surface), .6); font-size: .74rem; }
.tier-editor-grid { display: grid; gap: 12px; grid-template-columns: 1fr 1fr minmax(130px, .55fr); }
.tier-gift-choice { align-items: center; background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-theme-success), .24); border-radius: 14px; display: flex; gap: 14px; min-height: 108px; padding: 10px 12px; }
.tier-gift-choice .v-avatar { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); flex: 0 0 auto; }
.picker-help { color: rgba(var(--v-theme-on-surface), .68); font-size: .86rem; line-height: 1.45; }.picker-count { color: rgba(var(--v-theme-on-surface), .62); font-size: .8rem; font-weight: 700; }.product-picker-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); max-height: 58vh; overflow: auto; padding: 2px; }.product-picker-card { background: rgb(var(--v-theme-surface)); border: 2px solid rgba(var(--v-theme-on-surface), .1); border-radius: 14px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: flex; flex-direction: column; min-width: 0; overflow: hidden; padding: 0; position: relative; text-align: left; transition: border-color .15s ease, box-shadow .15s ease; }.product-picker-card:hover, .product-picker-card:focus-visible { border-color: rgba(var(--v-theme-primary), .55); box-shadow: 0 7px 20px rgba(var(--v-theme-primary), .12); outline: none; }.product-picker-card.selected { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), .12); }.product-picker-card.incompatible { cursor: not-allowed; filter: grayscale(.65); opacity: .55; }.product-picker-card.incompatible:hover { border-color: rgba(var(--v-theme-on-surface), .1); box-shadow: none; }.product-picker-card.gift.selected { border-color: rgb(var(--v-theme-success)); }.picker-check { background: rgb(var(--v-theme-surface)); border-radius: 999px; color: rgb(var(--v-theme-primary)); display: grid; padding: 2px; place-items: center; position: absolute; right: 8px; top: 8px; z-index: 1; }.picker-name { font-size: .82rem; font-weight: 800; line-height: 1.3; overflow-wrap: anywhere; padding: 10px 10px 3px; }.picker-meta { color: rgba(var(--v-theme-on-surface), .6); font-size: .7rem; overflow-wrap: anywhere; padding: 0 10px 3px; }.picker-catalog { color: rgb(var(--v-theme-primary)); font-size: .68rem; font-weight: 800; overflow-wrap: anywhere; padding: 0 10px 11px; }.picker-placeholder { align-items: center; background: rgba(var(--v-theme-primary), .055); color: rgba(var(--v-theme-primary), .55); display: flex; height: 160px; justify-content: center; }.empty-picker { align-items: center; color: rgba(var(--v-theme-on-surface), .6); display: flex; flex-direction: column; gap: 10px; min-height: 190px; justify-content: center; text-align: center; }.gift-manager-grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); }.gift-manager-card { border: 1px solid rgba(var(--v-theme-on-surface), .1); border-radius: 14px; min-width: 0; overflow: hidden; }.gift-manager-image { align-items: center; background: rgba(var(--v-theme-primary), .025); display: flex; height: 210px; justify-content: center; padding: 12px; }.gift-manager-image .v-img { height: 100%; width: 100%; }.gift-manager-card b { display: block; overflow-wrap: anywhere; }
.brand-picker-grid { display: grid; gap: 10px; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); max-height: 52vh; overflow: auto; padding: 2px; }.brand-picker-card { align-items: center; background: rgb(var(--v-theme-surface)); border: 2px solid rgba(var(--v-theme-on-surface), .1); border-radius: 12px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: flex; font: inherit; font-weight: 700; gap: 10px; min-height: 52px; padding: 10px 12px; text-align: left; transition: border-color .15s ease, background-color .15s ease; }.brand-picker-card:hover, .brand-picker-card:focus-visible { border-color: rgba(var(--v-theme-primary), .55); outline: none; }.brand-picker-card.selected { background: rgba(var(--v-theme-primary), .07); border-color: rgb(var(--v-theme-primary)); color: rgb(var(--v-theme-primary)); }
@media (max-width: 800px) { .tier-editor-grid { grid-template-columns: 1fr 1fr; }.tier-editor-grid > :last-child { grid-column: 1 / -1; }.tier-summary-row { grid-template-columns: minmax(110px, .8fr) 20px minmax(170px, 1.2fr); } }
@media (max-width: 600px) { .tier-summary-row { align-items: stretch; grid-template-columns: 1fr; }.tier-summary-row > .flow-arrow { transform: rotate(90deg); }.tier-editor-grid { grid-template-columns: 1fr; }.tier-editor-grid > :last-child { grid-column: auto; }.tier-gift-choice { align-items: stretch; flex-wrap: wrap; }.tier-gift-choice .v-btn { width: 100%; }.selection-box { align-items: stretch; flex-direction: column; }.gift-choice { align-items: stretch; flex-wrap: wrap; }.gift-choice .v-btn { width: 100%; }.product-picker-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.picker-name { font-size: .75rem; } }
</style>
