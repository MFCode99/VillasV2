<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import ProductPreviewDialog from '../components/ProductPreviewDialog.vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const data = ref({ products: [], categories: [], catalogs: [], counts: {} })
const q = ref('')
const catalogFilter = ref('all')
const dialog = ref(false)
const editing = ref(false)
const imageFile = ref(null)
const sortKey = ref('name')
const sortDesc = ref(false)
const previewOpen = ref(false)
const previewProduct = ref(null)
const form = reactive(emptyForm())

function emptyForm() {
  return { ref: '', catalog_slug: 'villas', name: '', product_type: '', category_slug: null, brand: '', family: '', ean: '', price: '0.00', price_base: null, eco_value: '0.00', pvp: null, case_inner: null, case_outer: null, colors: [], sizes: [], season: 'ambos', quantity_step: 12, quick_quantities: [], sort_order: 0, active: true, manual_active: true, gift_only: false, description: '' }
}
function productPrice(product) { return Number(product.price || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2) }
function openPreview(product) { previewProduct.value = product; previewOpen.value = true }
const isInterpilhasForm = computed(() => form.catalog_slug === 'interpilhas')
const catalogOptions = computed(() => data.value.catalogs.map(item => ({ title: item.label, value: item.slug })))
const categoryMap = computed(() => Object.fromEntries(data.value.categories.map(item => [item.slug, item])))
const categoryOptions = computed(() => data.value.categories.filter(category => category.catalogSlug === form.catalog_slug).map(category => {
  const parent = category.parentSlug ? categoryMap.value[category.parentSlug] : null
  return { title: `${parent ? `${parent.label} › ` : ''}${category.label}${category.active ? '' : ' (desativada)'}`, value: category.slug, disabled: !category.active || Boolean(parent && !parent.active) }
}))
const products = computed(() => {
  const value = q.value.toLowerCase()
  const rows = data.value.products.filter(product => {
    if (catalogFilter.value !== 'all' && product.catalogSlug !== catalogFilter.value) return false
    return !value || `${product.ref} ${product.name} ${product.type} ${product.categoryLabel} ${product.catalogLabel} ${product.brand} ${product.family} ${product.ean}`.toLowerCase().includes(value)
  })
  const field = {
    product: product => `${product.name} ${product.ref}`,
    catalog: product => product.catalogLabel,
    category: product => `${product.categoryParentLabel} ${product.categoryLabel}`,
    price: product => Number(product.price || 0),
    pvp: product => Number(product.pvp || 0),
    active: product => Number(Boolean(product.active && product.categoryActive)),
  }[sortKey.value] || (product => product.name)
  return rows.sort((a, b) => {
    const left = field(a); const right = field(b)
    const order = typeof left === 'number' ? left - right : String(left).localeCompare(String(right), 'pt')
    return sortDesc.value ? -order : order
  })
})

function sortBy(key) {
  if (sortKey.value === key) sortDesc.value = !sortDesc.value
  else { sortKey.value = key; sortDesc.value = false }
}
async function load() {
  try { data.value = (await api.get('/admin/catalog')).data }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}
function open(product = null) {
  editing.value = Boolean(product)
  imageFile.value = null
  Object.assign(form, product ? {
    ref: product.ref,
    catalog_slug: product.catalogSlug,
    name: product.name,
    product_type: product.type,
    category_slug: product.categorySlug,
    brand: product.brand,
    family: product.family,
    ean: product.ean,
    price: product.price,
    price_base: product.priceBase,
    eco_value: product.ecoValue,
    pvp: product.pvp,
    case_inner: product.caseInner,
    case_outer: product.caseOuter,
    colors: [...product.colors],
    sizes: [...product.sizes],
    season: product.season,
    quantity_step: product.quantityStep,
    quick_quantities: [...(product.quickQuantities || [])],
    sort_order: product.sortOrder,
    active: product.active,
    manual_active: product.manualActive,
    gift_only: product.giftOnly,
    description: product.description,
  } : emptyForm())
  dialog.value = true
}
async function save() {
  try {
    const transaction = new FormData()
    const quickQuantities = [...new Set((form.quick_quantities || []).flatMap(value => String(value).split(/[,;\s]+/)).map(Number).filter(value => Number.isInteger(value) && value > 0))].sort((a, b) => a - b).slice(0, 4)
    transaction.append('payload', JSON.stringify({ ...form, quick_quantities: quickQuantities }))
    if (editing.value) transaction.append('original_ref', form.ref)
    const file = Array.isArray(imageFile.value) ? imageFile.value[0] : imageFile.value
    if (file) transaction.append('image', file)
    await api.post('/admin/products/save', transaction)
    dialog.value = false
    await load()
    feedback.show(`Produto ${editing.value ? 'atualizado' : 'criado'}.`)
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  }
}
async function toggle(product) {
  const previous = product.active
  product.active = !previous
  try {
    await api.patch(`/admin/products/${product.ref}/active`, { active: product.active })
    feedback.show('Estado atualizado.')
  } catch (error) {
    product.active = previous
    feedback.show(errorMessage(error), 'error')
  }
}
async function remove(product) {
  if (!await feedback.confirm(`Eliminar definitivamente o produto “${product.name}”?`, 'Eliminar produto')) return
  try {
    await api.delete(`/admin/products/${product.ref}`)
    await load()
    feedback.show('Produto eliminado.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  }
}

watch(() => form.catalog_slug, slug => {
  const selected = categoryMap.value[form.category_slug]
  if (selected && selected.catalogSlug !== slug) form.category_slug = null
  if (slug === 'interpilhas') form.season = 'ambos'
})
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head"><div><h1>Produtos</h1><p>{{ data.counts.totalProducts || 0 }} produtos · {{ data.counts.activeProducts || 0 }} ativos</p></div><v-btn color="primary" prepend-icon="mdi-plus" @click="open()">Novo produto</v-btn></div>
    <v-card class="soft-card pa-4 mb-5">
      <v-row density="compact">
        <v-col cols="12" md="8"><v-text-field v-model="q" hide-details clearable prepend-inner-icon="mdi-magnify" label="Pesquisar referência, produto, marca ou EAN" /></v-col>
        <v-col cols="12" md="4"><v-select v-model="catalogFilter" hide-details label="Catálogo" :items="[{ title: 'Todos os catálogos', value: 'all' }, ...catalogOptions]" /></v-col>
      </v-row>
    </v-card>

    <v-card class="soft-card table-wrap">
      <v-table>
        <thead><tr>
          <th class="cursor-pointer" @click="sortBy('product')">Produto <v-icon size="14">{{ sortKey === 'product' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th>
          <th class="cursor-pointer" @click="sortBy('catalog')">Catálogo <v-icon size="14">{{ sortKey === 'catalog' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th>
          <th class="cursor-pointer" @click="sortBy('category')">Categoria / marca <v-icon size="14">{{ sortKey === 'category' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th>
          <th class="text-right cursor-pointer" @click="sortBy('price')">Preço s/ IVA <v-icon size="14">{{ sortKey === 'price' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th>
          <th class="text-right cursor-pointer" @click="sortBy('pvp')">PVP <v-icon size="14">{{ sortKey === 'pvp' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th>
          <th class="text-center cursor-pointer" @click="sortBy('active')">Ativo <v-icon size="14">{{ sortKey === 'active' ? (sortDesc ? 'mdi-arrow-down' : 'mdi-arrow-up') : 'mdi-swap-vertical' }}</v-icon></th><th></th>
        </tr></thead>
        <tbody><tr v-for="product in products" :key="product.ref" :class="{ 'opacity-60': !product.active || !product.categoryActive }">
          <td><div class="d-flex align-center ga-3"><v-avatar rounded="lg" color="grey-lighten-3"><v-img v-if="product.imageUrl" :src="product.imageUrl" /><v-icon v-else>mdi-package-variant</v-icon></v-avatar><div><b>{{ product.name }}</b><div class="text-caption">{{ product.ref }} · {{ product.type }}</div><v-chip v-if="product.giftOnly" size="x-small" color="success" variant="tonal" prepend-icon="mdi-gift-outline" class="mt-1">Apenas oferta</v-chip></div></div></td>
          <td><v-chip size="small" variant="tonal" :color="product.catalogSlug === 'interpilhas' ? 'info' : 'primary'">{{ product.catalogLabel }}</v-chip></td>
          <td><div>{{ [product.categoryParentLabel, product.categoryLabel].filter(Boolean).join(' › ') || 'Sem categoria' }}</div><div v-if="product.brand" class="text-caption text-medium-emphasis">{{ product.brand }}<span v-if="product.family"> · {{ product.family }}</span></div><v-chip v-if="!product.categoryActive" size="x-small" color="error" class="mt-1">Categoria off</v-chip></td>
          <td class="text-right font-weight-bold price-number">{{ productPrice(product) }} €</td>
          <td class="text-right price-number">{{ product.pvp == null ? '—' : `${Number(product.pvp).toFixed(2)} €` }}</td>
          <td class="text-center"><v-switch :model-value="product.active" :disabled="!product.categoryActive && product.active" :aria-label="`${product.active ? 'Desativar' : 'Ativar'} ${product.name}`" hide-details color="success" class="d-inline-flex" @update:model-value="toggle(product)" /></td>
          <td class="text-no-wrap"><v-btn icon="mdi-eye-outline" variant="text" :aria-label="`Pré-visualizar ${product.name}`" @click="openPreview(product)" /><v-btn icon="mdi-pencil-outline" variant="text" :aria-label="`Editar ${product.name}`" @click="open(product)" /><v-btn icon="mdi-delete-outline" variant="text" color="error" :aria-label="`Eliminar ${product.name}`" @click="remove(product)" /></td>
        </tr></tbody>
      </v-table>
    </v-card>

    <v-dialog v-model="dialog" max-width="980">
      <v-card>
        <v-card-title class="pa-6 pb-2">{{ editing ? 'Editar produto' : 'Novo produto' }}</v-card-title>
        <v-card-text class="pa-6">
          <v-row density="compact">
            <v-col cols="12" md="4"><v-select v-model="form.catalog_slug" label="Catálogo" :items="catalogOptions" :disabled="editing" /></v-col>
            <v-col cols="12" md="3"><v-text-field v-model="form.ref" label="Referência" :disabled="editing" /></v-col>
            <v-col cols="12" md="5"><v-text-field v-model="form.name" label="Nome" /></v-col>
            <v-col cols="12" md="6"><v-text-field v-model="form.product_type" label="Tipo" /></v-col>
            <v-col cols="12" md="6"><v-select v-model="form.category_slug" clearable label="Categoria / subcategoria" :items="categoryOptions" /></v-col>

            <template v-if="isInterpilhasForm">
              <v-col cols="12" md="4"><v-text-field v-model="form.brand" label="Marca" /></v-col>
              <v-col cols="12" md="4"><v-text-field v-model="form.family" label="Família" /></v-col>
              <v-col cols="12" md="4"><v-text-field v-model="form.ean" label="EAN / código de barras" inputmode="numeric" /></v-col>
              <v-col cols="6" md="3"><v-text-field v-model="form.price_base" type="number" step="0.001" label="Preço base" /></v-col>
              <v-col cols="6" md="3"><v-text-field v-model="form.eco_value" type="number" step="0.001" label="Ecovalor" /></v-col>
              <v-col cols="6" md="3"><v-text-field v-model="form.case_inner" type="number" min="1" label="Caixa interior" /></v-col>
              <v-col cols="6" md="3"><v-text-field v-model="form.case_outer" type="number" min="1" label="Caixa exterior" /></v-col>
            </template>

            <v-col cols="6" md="3"><v-text-field v-model="form.price" type="number" :step="isInterpilhasForm ? '0.001' : '0.01'" label="Preço final s/ IVA" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model="form.pvp" type="number" step="0.01" label="PVP" /></v-col>
            <v-col v-if="!isInterpilhasForm" cols="6" md="3"><v-select v-model="form.season" label="Estação" :items="[{ title: 'Todo o ano', value: 'ambos' }, { title: 'Inverno', value: 'inverno' }, { title: 'Verão', value: 'verao' }]" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model.number="form.quantity_step" type="number" min="1" label="Múltiplo" /></v-col>
            <v-col cols="12" md="6"><v-combobox v-model="form.quick_quantities" multiple chips closable-chips label="Atalhos de quantidade" hint="Valores em unidades, por exemplo 12, 24 e 144." persistent-hint /></v-col>
            <v-col v-if="!isInterpilhasForm" cols="12" md="6"><v-combobox v-model="form.colors" multiple chips label="Cores" /></v-col>
            <v-col v-if="!isInterpilhasForm" cols="12" md="6"><v-combobox v-model="form.sizes" multiple chips label="Tamanhos" /></v-col>
            <v-col cols="12"><v-file-input v-model="imageFile" accept="image/*,.heic,.heif,.tif,.tiff,.bmp,.gif" label="Imagem do produto" prepend-icon="mdi-camera-outline" hint="A imagem é validada e formatos incompatíveis são convertidos automaticamente." persistent-hint /></v-col>
            <v-col cols="12"><v-textarea v-model="form.description" label="Descrição" rows="3" /></v-col>
            <v-col cols="6"><v-switch v-model="form.active" color="success" label="Ativo" /></v-col>
            <v-col cols="6"><v-switch v-model="form.manual_active" color="success" label="Ativação manual" /></v-col>
            <v-col cols="12"><v-switch v-model="form.gift_only" color="success" label="Produto exclusivo para ofertas" hint="Fica disponível na gestão, mas não aparece no catálogo dos clientes." persistent-hint /></v-col>
          </v-row>
        </v-card-text>
        <v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="dialog = false">Cancelar</v-btn><v-btn color="primary" @click="save">Guardar</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
    <ProductPreviewDialog v-model="previewOpen" :product="previewProduct" />
  </div>
</template>

<style scoped>
.price-number { font-variant-numeric: tabular-nums; }
</style>
