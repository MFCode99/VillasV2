<script setup>
import { computed } from 'vue'
import { useDisplay } from 'vuetify'

const props = defineProps({
  products: { type: Array, default: () => [] },
  selected: { type: Array, default: () => [] },
  selectedOne: { type: String, default: '' },
  allowedCatalog: { type: String, default: '' },
  single: Boolean,
  gift: Boolean,
})
const emit = defineEmits(['select'])
const { xs, sm, md } = useDisplay()
const columns = computed(() => xs.value ? 2 : sm.value ? 3 : md.value ? 4 : 5)
const rows = computed(() => {
  const output = []
  for (let index = 0; index < props.products.length; index += columns.value) output.push(props.products.slice(index, index + columns.value))
  return output
})
const selectedSet = computed(() => new Set(props.selected))
function isSelected(product) { return props.single ? props.selectedOne === product.ref : selectedSet.value.has(product.ref) }
function disabled(product) { return Boolean(props.allowedCatalog && product.catalogSlug !== props.allowedCatalog) }
function price(product) { return Number(product.price || 0).toLocaleString('pt-PT', { style: 'currency', currency: 'EUR' }) }
</script>

<template>
  <v-virtual-scroll v-if="rows.length" :items="rows" :height="'58vh'" :item-height="232" class="virtual-product-picker">
    <template #default="{ item: row }">
      <div class="virtual-product-row" :style="{ '--picker-columns': columns }">
        <button
          v-for="product in row"
          :key="product.ref"
          v-memo="[product.ref, isSelected(product), disabled(product)]"
          type="button"
          class="virtual-product-card"
          :class="{ selected: isSelected(product), incompatible: disabled(product), gift }"
          :disabled="disabled(product)"
          :aria-pressed="isSelected(product)"
          @click="emit('select', product.ref)"
        >
          <span class="virtual-picker-check"><v-icon>{{ isSelected(product) ? 'mdi-check-circle' : disabled(product) ? 'mdi-lock-outline' : 'mdi-circle-outline' }}</v-icon></span>
          <v-img v-if="product.imageUrl" :src="product.imageUrl" height="130" cover />
          <div v-else class="virtual-picker-placeholder"><v-icon size="42">{{ gift ? 'mdi-gift-outline' : 'mdi-package-variant' }}</v-icon></div>
          <b>{{ product.name }}</b>
          <small>{{ product.ref }}<template v-if="!gift"> · {{ price(product) }}</template></small>
          <span v-if="product.catalogLabel">{{ product.catalogLabel }}</span>
        </button>
      </div>
    </template>
  </v-virtual-scroll>
  <div v-else class="virtual-picker-empty"><v-icon size="44">mdi-package-variant-closed-remove</v-icon><span>Não foram encontrados produtos.</span></div>
</template>

<style scoped>
.virtual-product-picker { overscroll-behavior: contain; padding: 2px; }
.virtual-product-row { display: grid; gap: 12px; grid-template-columns: repeat(var(--picker-columns), minmax(0, 1fr)); min-height: 232px; padding: 2px 8px 12px 2px; }
.virtual-product-card { background: rgb(var(--v-theme-surface)); border: 2px solid rgba(var(--v-theme-on-surface), .1); border-radius: 14px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: flex; flex-direction: column; min-width: 0; overflow: hidden; padding: 0; position: relative; text-align: left; }
.virtual-product-card:focus-visible { border-color: rgb(var(--v-theme-primary)); outline: 3px solid rgba(var(--v-theme-primary), .24); outline-offset: 2px; }
.virtual-product-card.selected { border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), .12); }
.virtual-product-card.gift.selected { border-color: rgb(var(--v-theme-success)); }
.virtual-product-card.incompatible { cursor: not-allowed; filter: grayscale(.65); opacity: .5; }
.virtual-product-card b { font-size: .8rem; line-height: 1.3; overflow-wrap: anywhere; padding: 9px 10px 2px; }
.virtual-product-card small { color: rgba(var(--v-theme-on-surface), .62); font-size: .7rem; overflow-wrap: anywhere; padding: 0 10px 2px; }
.virtual-product-card > span:last-child:not(.virtual-picker-check) { color: rgb(var(--v-theme-primary)); font-size: .68rem; font-weight: 800; padding: 0 10px 10px; }
.virtual-picker-check { background: rgb(var(--v-theme-surface)); border-radius: 999px; color: rgb(var(--v-theme-primary)); display: grid; padding: 2px; place-items: center; position: absolute; right: 8px; top: 8px; z-index: 1; }
.virtual-picker-placeholder { align-items: center; background: rgba(var(--v-theme-primary), .055); color: rgba(var(--v-theme-primary), .55); display: flex; height: 130px; justify-content: center; }
.virtual-picker-empty { align-items: center; color: rgba(var(--v-theme-on-surface), .6); display: flex; flex-direction: column; gap: 10px; justify-content: center; min-height: 190px; }
@media (hover: hover) { .virtual-product-card:hover:not(:disabled) { border-color: rgba(var(--v-theme-primary), .55); } }
</style>
