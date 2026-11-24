<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useCartStore } from '../stores/cart'
import { useFeedbackStore } from '../stores/feedback'

const route = useRoute()
const router = useRouter()
const cart = useCartStore()
const feedback = useFeedbackStore()
const product = ref(null)
const color = ref('')
const size = ref('')
const quantity = ref(1)
const quickQuantityStarted = ref(false)
const loading = ref(true)
const adding = ref(false)
const publicCatalogSlug = computed(() => String(route.params.catalog || 'villas').toLowerCase())
const catalogSlug = computed(() => publicCatalogSlug.value === 'utilidades' ? 'interpilhas' : publicCatalogSlug.value)
const backUrl = computed(() => `/catalogo/${publicCatalogSlug.value}`)
const isInterpilhas = computed(() => catalogSlug.value === 'interpilhas')
const hasEcoTax = computed(() => isInterpilhas.value && Number(product.value?.ecoValue || 0) > 0)
const displayPrice = computed(() => {
  const value = hasEcoTax.value && product.value?.priceBase != null ? product.value.priceBase : product.value?.price
  return Number(value || 0).toFixed(isInterpilhas.value ? 3 : 2).replace('.', ',')
})
const displayEcoTax = computed(() => Number(product.value?.ecoValue || 0).toFixed(isInterpilhas.value ? 3 : 2).replace('.', ','))
const displayOriginalPrice = computed(() => {
  let value = Number(product.value?.originalPrice || 0)
  if (hasEcoTax.value) value -= Number(product.value?.ecoValue || 0)
  return Math.max(0, value).toFixed(isInterpilhas.value ? 3 : 2).replace('.', ',')
})
function addQuickQuantity(amount) {
  const step = Math.max(1, Number(product.value?.quantityStep) || 1)
  const current = Math.max(step, Number(quantity.value) || step)
  quantity.value = quickQuantityStarted.value ? current + Number(amount) : Number(amount)
  quickQuantityStarted.value = true
  quantity.value = Math.max(step, Math.round(quantity.value / step) * step)
}
function resetQuickQuantity() {
  quantity.value = Math.max(1, Number(product.value?.quantityStep) || 1)
  quickQuantityStarted.value = false
}

onMounted(async () => {
  try {
    product.value = (await api.get(`/catalog/${catalogSlug.value}/${route.params.ref}`)).data.product
    quantity.value = product.value.quantityStep
    color.value = product.value.colors[0] || ''
    size.value = product.value.sizes[0] || ''
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
    router.replace(backUrl.value)
  } finally {
    loading.value = false
  }
})
async function add() {
  adding.value = true
  try {
    await cart.add(product.value, color.value, size.value, quantity.value)
    feedback.show('Produto adicionado ao carrinho.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <div class="page">
    <v-btn :to="backUrl" variant="text" prepend-icon="mdi-arrow-left" class="mb-4">Voltar a {{ isInterpilhas ? 'Utilidades' : product?.catalogLabel || 'catálogo' }}</v-btn>
    <v-skeleton-loader v-if="loading" type="image, article" />
    <v-card v-else-if="product" class="soft-card pa-3">
      <v-row>
        <v-col cols="12" md="6"><v-img :src="product.imageUrl" height="480" class="product-image product-detail-image rounded-xl" :style="{ '--product-image-zoom': product.imageZoom || 1 }" contain /></v-col>
        <v-col cols="12" md="6" class="pa-6 pa-md-10">
          <div class="d-flex flex-wrap align-center ga-2 mb-2">
            <div class="text-overline text-secondary font-weight-bold">{{ product.ref }} · {{ product.categoryParentLabel || product.categoryLabel }}</div>
            <v-chip v-if="product.brand" size="small" color="primary" variant="tonal">{{ product.brand }}</v-chip>
          </div>
          <h1 class="text-h3 font-weight-black mt-2 mb-3">{{ product.name }}</h1>
          <p class="text-medium-emphasis">{{ product.description || product.type }}</p>
          <div v-if="isInterpilhas" class="product-meta-grid my-6">
            <div v-if="product.categoryLabel"><span>Subcategoria</span><strong>{{ product.categoryLabel }}</strong></div>
            <div v-if="product.family"><span>Família</span><strong>{{ product.family }}</strong></div>
            <div v-if="product.ean"><span>EAN</span><strong>{{ product.ean }}</strong></div>
          </div>
          <div class="product-price my-7">
            <div v-if="product.promotion" class="d-flex flex-wrap align-center ga-2 mb-1"><span class="original-price">{{ displayOriginalPrice }} €</span><v-chip size="small" color="success" variant="tonal" prepend-icon="mdi-sale-outline">{{ product.promotion.label }}</v-chip></div>
            <div class="text-h4 font-weight-black price-number">{{ displayPrice }} €</div>
            <div v-if="hasEcoTax" class="eco-price mt-1">+ {{ displayEcoTax }} € ecotaxa</div>
            <div class="text-caption text-medium-emphasis mt-1">Preço sem IVA</div>
          </div>
          <v-select v-if="product.colors.length" v-model="color" label="Cor" :items="product.colors" />
          <v-select v-if="product.sizes.length" v-model="size" label="Tamanho" :items="product.sizes" />
          <div v-if="product.quickQuantities?.length" class="quick-quantities mb-3" aria-label="Atalhos de quantidade">
            <v-btn v-for="amount in product.quickQuantities" :key="amount" variant="tonal" color="primary" :aria-label="`Adicionar ${amount} unidades`" @click="addQuickQuantity(amount)">+{{ amount }} un.</v-btn>
            <v-btn variant="text" prepend-icon="mdi-restore" @click="resetQuickQuantity">Repor</v-btn>
          </div>
          <div v-if="product.quickQuantities?.length" class="selected-quantity mb-2"><span>Quantidade selecionada</span><strong>{{ quantity }} un.</strong></div>
          <v-text-field v-else v-model.number="quantity" type="number" label="Quantidade" :step="product.quantityStep" :min="product.quantityStep" :hint="product.quantityStep > 1 ? `Múltiplos de ${product.quantityStep}` : 'Quantidade por unidade'" persistent-hint />
          <v-btn color="primary" size="large" block class="mt-6" prepend-icon="mdi-cart-plus" :loading="adding" @click="add">Adicionar ao carrinho</v-btn>
        </v-col>
      </v-row>
    </v-card>
  </div>
</template>

<style scoped>
.product-meta-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.product-detail-image { overflow: hidden; }
.product-detail-image :deep(.v-img__img) { transform: scale(var(--product-image-zoom, 1)); transform-origin: center; }
.product-meta-grid > div { background: rgba(var(--v-theme-primary), .045); border-radius: 12px; display: flex; flex-direction: column; padding: 12px 14px; }
.product-meta-grid span { color: rgba(var(--v-theme-on-surface), .66); font-size: .75rem; }
.product-meta-grid strong { margin-top: 2px; overflow-wrap: anywhere; }
.price-number { font-variant-numeric: tabular-nums; }
.original-price { color: rgba(var(--v-theme-on-surface), .55); font-variant-numeric: tabular-nums; text-decoration: line-through; }
.eco-price { color: rgba(var(--v-theme-on-surface), .55); font-size: .88rem; font-variant-numeric: tabular-nums; font-weight: 500; }
.quick-quantities { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-quantities :deep(.v-btn) { min-height: 44px; }
.selected-quantity { align-items: center; background: rgba(var(--v-theme-primary), .05); border-radius: 12px; display: flex; justify-content: space-between; padding: 12px 14px; }
@media (max-width: 500px) { .product-meta-grid { grid-template-columns: 1fr; } }
</style>
