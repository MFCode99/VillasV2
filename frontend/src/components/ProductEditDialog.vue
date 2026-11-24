<script setup>
import { computed, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  product: { type: Object, default: null },
  catalogs: { type: Array, default: () => [] },
  categories: { type: Array, default: () => [] },
})
const emit = defineEmits(['update:modelValue', 'saved'])
const feedback = useFeedbackStore()
const imageFile = ref(null)
const saving = ref(false)
const form = reactive(emptyForm())

function emptyForm() {
  return { ref: '', catalog_slug: 'villas', name: '', product_type: '', category_slug: null, brand: '', family: '', ean: '', price: '0.00', price_base: null, eco_value: '0.00', pvp: null, case_inner: null, case_outer: null, colors: [], sizes: [], season: 'ambos', quantity_step: 1, quick_quantities: [], sort_order: 0, active: true, manual_active: true, gift_only: false, description: '' }
}
const isUtilities = computed(() => form.catalog_slug === 'interpilhas')
const catalogOptions = computed(() => props.catalogs.map(item => ({ title: item.label, value: item.slug })))
const categoryMap = computed(() => Object.fromEntries(props.categories.map(item => [item.slug, item])))
const categoryOptions = computed(() => props.categories.filter(category => category.catalogSlug === form.catalog_slug).map(category => {
  const parent = category.parentSlug ? categoryMap.value[category.parentSlug] : null
  return { title: `${parent ? `${parent.label} › ` : ''}${category.label}${category.active ? '' : ' (desativada)'}`, value: category.slug, disabled: !category.active || Boolean(parent && !parent.active) }
}))

function populate(product) {
  imageFile.value = null
  Object.assign(form, {
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
    colors: [...(product.colors || [])],
    sizes: [...(product.sizes || [])],
    season: product.season,
    quantity_step: product.quantityStep,
    quick_quantities: [...(product.quickQuantities || [])],
    sort_order: product.sortOrder,
    active: product.active,
    manual_active: product.manualActive,
    gift_only: product.giftOnly,
    description: product.description,
  })
}
function close() { emit('update:modelValue', false) }
async function save() {
  if (!props.product || saving.value) return
  saving.value = true
  try {
    const transaction = new FormData()
    const quickQuantities = [...new Set((form.quick_quantities || []).flatMap(value => String(value).split(/[,;\s]+/)).map(Number).filter(value => Number.isInteger(value) && value > 0))].sort((a, b) => a - b).slice(0, 4)
    transaction.append('payload', JSON.stringify({ ...form, quick_quantities: quickQuantities }))
    transaction.append('original_ref', props.product.ref)
    const file = Array.isArray(imageFile.value) ? imageFile.value[0] : imageFile.value
    if (file) transaction.append('image', file)
    await api.post('/admin/products/save', transaction)
    emit('update:modelValue', false)
    emit('saved')
    feedback.show('Produto atualizado.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    saving.value = false
  }
}

watch([() => props.modelValue, () => props.product], ([open, product]) => { if (open && product) populate(product) }, { immediate: true })
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="980" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card v-if="product" class="product-edit-card">
      <v-card-title class="edit-header">
        <div><div class="text-caption text-medium-emphasis">{{ product.ref }}</div><strong>Editar produto</strong></div>
        <v-btn icon="mdi-close" variant="text" aria-label="Fechar edição" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-6">
        <v-row density="compact">
          <v-col cols="12" md="4"><v-select v-model="form.catalog_slug" label="Catálogo" :items="catalogOptions" disabled /></v-col>
          <v-col cols="12" md="3"><v-text-field v-model="form.ref" label="Referência" disabled /></v-col>
          <v-col cols="12" md="5"><v-text-field v-model="form.name" label="Nome" /></v-col>
          <v-col cols="12" md="6"><v-text-field v-model="form.product_type" label="Tipo" /></v-col>
          <v-col cols="12" md="6"><v-select v-model="form.category_slug" clearable label="Categoria / subcategoria" :items="categoryOptions" /></v-col>
          <template v-if="isUtilities">
            <v-col cols="12" md="4"><v-text-field v-model="form.brand" label="Marca" /></v-col>
            <v-col cols="12" md="4"><v-text-field v-model="form.family" label="Família" /></v-col>
            <v-col cols="12" md="4"><v-text-field v-model="form.ean" label="EAN / código de barras" inputmode="numeric" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model="form.price_base" type="number" step="0.001" label="Preço base" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model="form.eco_value" type="number" step="0.001" label="Ecovalor" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model="form.case_inner" type="number" min="1" label="Caixa interior" /></v-col>
            <v-col cols="6" md="3"><v-text-field v-model="form.case_outer" type="number" min="1" label="Caixa exterior" /></v-col>
          </template>
          <v-col cols="6" md="3"><v-text-field v-model="form.price" type="number" :step="isUtilities ? '0.001' : '0.01'" label="Preço final s/ IVA" /></v-col>
          <v-col cols="6" md="3"><v-text-field v-model="form.pvp" type="number" step="0.01" label="PVP" /></v-col>
          <v-col v-if="!isUtilities" cols="6" md="3"><v-select v-model="form.season" label="Estação" :items="[{ title: 'Todo o ano', value: 'ambos' }, { title: 'Inverno', value: 'inverno' }, { title: 'Verão', value: 'verao' }]" /></v-col>
          <v-col cols="6" md="3"><v-text-field v-model.number="form.quantity_step" type="number" min="1" label="Múltiplo" /></v-col>
          <v-col cols="12" md="6"><v-combobox v-model="form.quick_quantities" multiple chips closable-chips label="Atalhos de quantidade" hint="Valores em unidades, por exemplo 12, 24 e 144." persistent-hint /></v-col>
          <v-col v-if="!isUtilities" cols="12" md="6"><v-combobox v-model="form.colors" multiple chips label="Cores" /></v-col>
          <v-col v-if="!isUtilities" cols="12" md="6"><v-combobox v-model="form.sizes" multiple chips label="Tamanhos" /></v-col>
          <v-col cols="12"><v-file-input v-model="imageFile" accept="image/*,.heic,.heif,.tif,.tiff,.bmp,.gif" label="Imagem do produto" prepend-icon="mdi-camera-outline" hint="A imagem é validada e formatos incompatíveis são convertidos automaticamente." persistent-hint /></v-col>
          <v-col cols="12"><v-textarea v-model="form.description" label="Descrição" rows="3" /></v-col>
          <v-col cols="6"><v-switch v-model="form.active" color="success" label="Ativo" /></v-col>
          <v-col cols="6"><v-switch v-model="form.manual_active" color="success" label="Ativação manual" /></v-col>
          <v-col cols="12"><v-switch v-model="form.gift_only" color="success" label="Produto exclusivo para ofertas" hint="Fica disponível na gestão, mas não aparece no catálogo dos clientes." persistent-hint /></v-col>
        </v-row>
      </v-card-text>
      <v-divider />
      <v-card-actions class="pa-5"><v-spacer /><v-btn variant="text" :disabled="saving" @click="close">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="save">Guardar alterações</v-btn></v-card-actions>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.product-edit-card { border-radius: 18px !important; }
.edit-header { align-items: flex-start; display: flex; justify-content: space-between; padding: 18px 18px 16px 24px; }
.edit-header strong { font-size: 1.15rem; }
</style>
