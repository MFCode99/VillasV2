<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../services/api'
import { useCartStore } from '../stores/cart'
import { useFeedbackStore } from '../stores/feedback'
const feedback = useFeedbackStore(); const cart = useCartStore(); const result = ref({ items: [], categories: [], total: 0, pages: 1, page: 1 }); const loading = ref(false)
const filters = reactive({ q: '', category: null, season: null, sort: 'ref_asc', page: 1 }); let timer
const selections = reactive({}); const adding = reactive({})
const seasons = [{ title: 'Todas as estações', value: null }, { title: 'Todo o ano', value: 'ambos' }, { title: 'Inverno', value: 'inverno' }, { title: 'Verão', value: 'verao' }]
const sorts = [{ title: 'Referência', value: 'ref_asc' }, { title: 'Nome A–Z', value: 'name_asc' }, { title: 'Preço crescente', value: 'price_asc' }, { title: 'Preço decrescente', value: 'price_desc' }]
function setProducts(data) { data.items.forEach(product => { if (!selections[product.ref]) selections[product.ref] = { color: product.colors[0] || '', size: product.sizes[0] || '', quantity: product.quantityStep } }); result.value = data }
async function load() { loading.value = true; try { setProducts((await api.get('/catalog', { params: { ...filters, per_page: 24 } })).data) } catch (e) { feedback.show(errorMessage(e), 'error') } finally { loading.value = false } }
function adjust(product, direction) { const choice = selections[product.ref]; choice.quantity = Math.max(product.quantityStep, choice.quantity + direction * product.quantityStep) }
function seasonMeta(season) { return ({ inverno: { label: 'Inverno', icon: 'mdi-snowflake' }, verao: { label: 'Verão', icon: 'mdi-white-balance-sunny' }, ambos: { label: 'Todo o ano', icon: 'mdi-calendar-check-outline' } }[season] || { label: season, icon: 'mdi-calendar-outline' }) }
async function add(product) { adding[product.ref] = true; try { const choice = selections[product.ref]; await cart.add(product, choice.color, choice.size, choice.quantity); feedback.show('Produto adicionado ao carrinho.') } catch (e) { feedback.show(errorMessage(e), 'error') } finally { adding[product.ref] = false } }
watch(filters, () => { clearTimeout(timer); timer = setTimeout(load, 250) }, { deep: true }); onMounted(() => { load(); cart.load().catch(() => {}) })
</script>
<template><div class="page"><div class="page-head"><div><h1>Catálogo</h1><p>{{ result.total }} produtos disponíveis.</p></div><v-btn to="/carrinho" color="primary" prepend-icon="mdi-cart-outline">Ver carrinho</v-btn></div>
  <v-card class="soft-card pa-4 mb-6"><v-row dense><v-col cols="12" md="5"><v-text-field v-model="filters.q" hide-details clearable label="Pesquisar nome ou referência" prepend-inner-icon="mdi-magnify" /></v-col><v-col cols="12" sm="4" md="3"><v-select v-model="filters.category" hide-details clearable label="Categoria" :items="result.categories" item-title="label" item-value="slug" /></v-col><v-col cols="6" sm="4" md="2"><v-select v-model="filters.season" hide-details label="Estação" :items="seasons" /></v-col><v-col cols="6" sm="4" md="2"><v-select v-model="filters.sort" hide-details label="Ordenar" :items="sorts" /></v-col></v-row></v-card>
  <v-row v-if="loading"><v-col v-for="i in 8" :key="i" cols="12" sm="6" md="4" lg="3"><v-skeleton-loader type="image, article" /></v-col></v-row>
  <v-row v-else><v-col v-for="product in result.items" :key="product.ref" cols="12" sm="6" md="4" lg="3"><v-card class="soft-card h-100 d-flex flex-column overflow-hidden"><v-img :src="product.imageUrl" height="220" class="product-image catalog-product-image" contain><template #error><div class="d-flex fill-height align-center justify-center"><v-icon size="54" color="grey-lighten-1">mdi-image-outline</v-icon></div></template></v-img><v-card-text class="d-flex flex-column flex-grow-1"><div class="text-caption text-medium-emphasis">{{ product.ref }} · {{ product.categoryLabel }}</div><router-link :to="`/catalogo/${product.ref}`" class="catalog-product-name text-subtitle-1 font-weight-bold mt-1">{{ product.name }}</router-link><div class="d-flex justify-space-between align-end mt-3 mb-3"><v-chip size="small" variant="tonal" :prepend-icon="seasonMeta(product.season).icon">{{ seasonMeta(product.season).label }}</v-chip><span class="text-h6 font-weight-black">{{ Number(product.price).toFixed(2) }} €</span></div><v-select v-if="product.colors.length" v-model="selections[product.ref].color" :items="product.colors" label="Cor" density="compact" variant="outlined" hide-details class="mb-3" /><v-select v-if="product.sizes.length" v-model="selections[product.ref].size" :items="product.sizes" label="Tamanho" density="compact" variant="outlined" hide-details class="mb-3" /><div class="d-flex align-center mt-auto"><div class="quantity-control"><v-btn icon="mdi-minus" size="small" variant="tonal" :disabled="selections[product.ref].quantity <= product.quantityStep" @click="adjust(product, -1)" /><b>{{ selections[product.ref].quantity }}</b><v-btn icon="mdi-plus" size="small" variant="tonal" @click="adjust(product, 1)" /></div></div><v-btn block color="primary" class="mt-4" prepend-icon="mdi-cart-plus" :loading="adding[product.ref]" @click="add(product)">Adicionar ao carrinho</v-btn></v-card-text></v-card></v-col></v-row>
  <div v-if="!loading && !result.items.length" class="empty-state"><v-icon size="52">mdi-package-variant-remove</v-icon><div class="text-h6 mt-3">Nenhum produto encontrado</div><div>Experimente alterar a pesquisa ou os filtros.</div></div>
  <v-pagination v-if="result.pages > 1" v-model="filters.page" :length="result.pages" class="mt-8" />
</div></template>
<style scoped>
.catalog-product-image :deep(.v-img__img) { object-position: center; }
.catalog-product-name { color: inherit; line-height: 1.35; min-height: 2.7em; text-decoration: none; }
.catalog-product-name:hover { color: rgb(var(--v-theme-primary)); }
.quantity-control { align-items: center; display: flex; gap: 10px; }
.quantity-control b { min-width: 30px; text-align: center; }
</style>
