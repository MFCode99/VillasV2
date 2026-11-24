<script setup>
import { computed } from 'vue'

const props = defineProps({
  modelValue: { type: Boolean, default: false },
  product: { type: Object, default: null },
})
const emit = defineEmits(['update:modelValue'])

const isUtilities = computed(() => props.product?.catalogSlug === 'interpilhas')
const digits = computed(() => isUtilities.value ? 3 : 2)
const hasEcoTax = computed(() => isUtilities.value && Number(props.product?.ecoValue || 0) > 0)
const price = computed(() => {
  const value = hasEcoTax.value && props.product?.priceBase != null ? props.product.priceBase : props.product?.price
  return Number(value || 0).toFixed(digits.value).replace('.', ',')
})
const originalPrice = computed(() => {
  let value = Number(props.product?.originalPrice || 0)
  if (hasEcoTax.value) value -= Number(props.product?.ecoValue || 0)
  return Math.max(0, value).toFixed(digits.value).replace('.', ',')
})
const ecoTax = computed(() => Number(props.product?.ecoValue || 0).toFixed(digits.value).replace('.', ','))
function close() { emit('update:modelValue', false) }
</script>

<template>
  <v-dialog :model-value="modelValue" max-width="780" scrollable @update:model-value="emit('update:modelValue', $event)">
    <v-card v-if="product" class="product-preview-card">
      <v-card-title class="preview-header">
        <div class="preview-heading">
          <span class="text-caption text-medium-emphasis">{{ product.ref }} · {{ product.categoryLabel }}</span>
          <strong id="product-preview-title">{{ product.name }}</strong>
        </div>
        <v-btn icon="mdi-close" variant="text" aria-label="Fechar pré-visualização" @click="close" />
      </v-card-title>
      <v-divider />
      <v-card-text class="pa-0">
        <v-row no-gutters>
          <v-col cols="12" sm="6" class="preview-image-column">
            <v-img :src="product.imageUrl" height="360" class="preview-image" :style="{ '--product-image-zoom': product.imageZoom || 1 }" contain>
              <template #error><div class="d-flex fill-height align-center justify-center"><v-icon size="56" color="grey-lighten-1">mdi-image-outline</v-icon></div></template>
            </v-img>
          </v-col>
          <v-col cols="12" sm="6" class="preview-details">
            <div class="d-flex flex-wrap ga-2 mb-4">
              <v-chip v-if="product.brand" size="small" color="primary" variant="tonal">{{ product.brand }}</v-chip>
              <v-chip v-if="product.family" size="small" variant="tonal">{{ product.family }}</v-chip>
            </div>
            <p class="text-body-2 text-medium-emphasis mb-5">{{ product.description || product.type || 'Sem descrição adicional.' }}</p>
            <div class="preview-price mb-5">
              <div v-if="product.promotion" class="d-flex flex-wrap align-center ga-2 mb-1"><span class="original-price">{{ originalPrice }} €</span><v-chip size="x-small" color="success" variant="tonal" prepend-icon="mdi-sale-outline">{{ product.promotion.label }}</v-chip></div>
              <strong>{{ price }} €</strong>
              <small v-if="hasEcoTax">+ {{ ecoTax }} € ecotaxa</small>
              <span>Preço sem IVA</span>
            </div>
            <div v-if="product.colors?.length" class="preview-options"><span>Cores</span><div><v-chip v-for="color in product.colors" :key="color" size="small" variant="outlined">{{ color }}</v-chip></div></div>
            <div v-if="product.sizes?.length" class="preview-options"><span>Tamanhos</span><div><v-chip v-for="size in product.sizes" :key="size" size="small" variant="outlined">{{ size }}</v-chip></div></div>
            <div v-if="product.ean" class="text-caption text-medium-emphasis mt-5">EAN: {{ product.ean }}</div>
          </v-col>
        </v-row>
      </v-card-text>
    </v-card>
  </v-dialog>
</template>

<style scoped>
.product-preview-card { border-radius: 18px !important; }
.preview-header { align-items: flex-start; display: flex; gap: 16px; justify-content: space-between; padding: 18px 18px 16px 22px; }
.preview-heading { display: flex; flex-direction: column; min-width: 0; }
.preview-heading strong { font-size: 1.1rem; line-height: 1.35; white-space: normal; }
.preview-image-column { background: rgba(var(--v-theme-on-surface), .025); }
.preview-image { overflow: hidden; }
.preview-image :deep(.v-img__img) { transform: scale(var(--product-image-zoom, 1)); transform-origin: center; }
.preview-details { padding: 28px !important; }
.preview-price { display: flex; flex-direction: column; }
.preview-price > strong { font-size: 1.65rem; font-variant-numeric: tabular-nums; }
.preview-price > small, .preview-price > span { color: rgba(var(--v-theme-on-surface), .58); font-size: .76rem; margin-top: 3px; }
.original-price { color: rgba(var(--v-theme-on-surface), .5); font-size: .82rem; text-decoration: line-through; }
.preview-options { margin-top: 16px; }
.preview-options > span { display: block; font-size: .75rem; font-weight: 700; margin-bottom: 7px; }
.preview-options > div { display: flex; flex-wrap: wrap; gap: 6px; }
@media (max-width: 600px) {
  .preview-image { height: 260px !important; }
  .preview-details { padding: 22px !important; }
}
</style>
