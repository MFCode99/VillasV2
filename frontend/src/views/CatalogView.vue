<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import ProductEditDialog from '../components/ProductEditDialog.vue'
import ProductPreviewDialog from '../components/ProductPreviewDialog.vue'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useFeedbackStore } from '../stores/feedback'
import { useTablet } from '../composables/useTablet'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const feedback = useFeedbackStore()
const cart = useCartStore()
const { tabletLandscape } = useTablet()
const result = ref({ items: [], categories: [], catalogs: [], filters: { brands: [], families: [] }, total: 0, pages: 1, page: 1, catalog: null })
const loading = ref(false)
const searchOpen = ref(false)
const filtersOpen = ref(false)
const previewOpen = ref(false)
const previewProduct = ref(null)
const editOpen = ref(false)
const editingProduct = ref(null)
const editingKey = ref('')
const adminCatalog = ref({ products: [], catalogs: [], categories: [] })
const publicCategories = { pilhas: 'interpilhas-pilhas', ambientadores: 'interpilhas-ambientadores', colas: 'interpilhas-colas-adesivos' }
const publicCategoryKeys = Object.fromEntries(Object.entries(publicCategories).map(([key, slug]) => [slug, key]))
function categoryFromRoute(value = route.query.categoria) {
  const raw = String(value || '')
  return String(route.params.catalog || '').toLowerCase() === 'utilidades' ? publicCategories[raw.toLowerCase()] || raw || null : raw || null
}
function subcategoryFromRoute(value = route.query.subcategoria) { return String(value || '') || null }
const filters = reactive({ q: '', category: categoryFromRoute(), subcategory: subcategoryFromRoute(), brand: null, family: null, season: null, sort: 'ref_asc', page: 1 })
const selections = reactive({})
const adding = reactive({})
let timer

const publicCatalogSlug = computed(() => String(route.params.catalog || 'villas').toLowerCase())
const catalogSlug = computed(() => publicCatalogSlug.value === 'utilidades' ? 'interpilhas' : publicCatalogSlug.value)
const activeCart = computed(() => cart.carts[catalogSlug.value] || { items: [], units: 0, total: '0.00' })
const isInterpilhas = computed(() => catalogSlug.value === 'interpilhas')
const activeCatalog = computed(() => catalogSlug.value === 'interpilhas'
  ? { ...(result.value.catalog || {}), slug: 'interpilhas', label: 'Utilidades' }
  : result.value.catalog || result.value.catalogs.find(item => item.slug === catalogSlug.value) || { slug: 'villas', label: 'Villas' })
const topCategories = computed(() => result.value.categories.filter(category => !category.parentSlug))
const subcategories = computed(() => filters.category
  ? result.value.categories.filter(category => category.parentSlug === filters.category)
  : [])
const selectedTopCategory = computed(() => topCategories.value.find(category => category.slug === filters.category) || null)
const activeFilterCount = computed(() => [
  filters.subcategory,
  filters.brand,
  filters.family,
  filters.season,
  filters.sort !== 'ref_asc' ? filters.sort : null,
].filter(Boolean).length)
const brands = computed(() => [{ title: 'Todas as marcas', value: null }, ...(result.value.filters?.brands || []).map(value => ({ title: value, value }))])
const families = computed(() => [{ title: 'Todas as famílias', value: null }, ...(result.value.filters?.families || []).map(value => ({ title: value, value }))])
const seasons = [{ title: 'Todas as estações', value: null }, { title: 'Todo o ano', value: 'ambos' }, { title: 'Inverno', value: 'inverno' }, { title: 'Verão', value: 'verao' }]
const sorts = [{ title: 'Referência', value: 'ref_asc' }, { title: 'Nome A–Z', value: 'name_asc' }, { title: 'Preço crescente', value: 'price_asc' }, { title: 'Preço decrescente', value: 'price_desc' }]
const categoryIcons = {
  'interpilhas-pilhas': 'mdi-battery-charging-medium',
  'interpilhas-pilhas-alcalinas': 'mdi-battery-high',
  'interpilhas-pilhas-zinco': 'mdi-battery-medium',
  'interpilhas-pilhas-litio': 'mdi-battery-charging',
  'interpilhas-pilhas-recarregaveis': 'mdi-battery-sync-outline',
  'interpilhas-pilhas-relogio': 'mdi-watch-variant',
  'interpilhas-pilhas-especiais': 'mdi-battery-plus-outline',
  'interpilhas-ambientadores': 'mdi-spray-bottle',
  'interpilhas-ambientadores-mon-areon': 'mdi-car-seat',
  'interpilhas-ambientadores-smile': 'mdi-emoticon-happy-outline',
  'interpilhas-ambientadores-fresco': 'mdi-flower-outline',
  'interpilhas-ambientadores-fresh-wave': 'mdi-weather-windy',
  'interpilhas-ambientadores-smile-toy': 'mdi-teddy-bear',
  'interpilhas-colas-adesivos': 'mdi-bottle-tonic-outline',
  'interpilhas-colas-instantaneas': 'mdi-flash-outline',
  'interpilhas-colas-contacto': 'mdi-handshake-outline',
  'interpilhas-silicones-selantes': 'mdi-water-outline',
  'interpilhas-massas-adesivas': 'mdi-shape-outline',
  'interpilhas-fitas-adesivas': 'mdi-link-variant',
  'interpilhas-escolar-escritorio': 'mdi-pencil-ruler',
  'interpilhas-ferramentas-acessorios': 'mdi-tools',
  'interpilhas-colas-especiais-universais': 'mdi-all-inclusive',
}

function priceValue(value, digits = 2) { return Number(value || 0).toFixed(digits).replace('.', ',') }
function mainPrice(product) {
  const digits = product.catalogSlug === 'interpilhas' ? 3 : 2
  if (product.catalogSlug === 'interpilhas' && Number(product.ecoValue || 0) > 0 && product.priceBase != null) return priceValue(product.priceBase, digits)
  return priceValue(product.price, digits)
}
function originalMainPrice(product) {
  const digits = product.catalogSlug === 'interpilhas' ? 3 : 2
  let value = Number(product.originalPrice || 0)
  if (product.catalogSlug === 'interpilhas' && Number(product.ecoValue || 0) > 0) value -= Number(product.ecoValue || 0)
  return priceValue(Math.max(0, value), digits)
}

function selectionKey(product) { return `${product.catalogSlug}:${product.ref}` }
function productPath(product) { return `/catalogo/${product.catalogSlug === 'interpilhas' ? 'utilidades' : product.catalogSlug}/${encodeURIComponent(product.ref)}` }
function openPreview(product) { previewProduct.value = product; previewOpen.value = true }
async function openEditor(product) {
  editingKey.value = selectionKey(product)
  try {
    const data = (await api.get('/admin/catalog')).data
    const target = data.products.find(item => item.ref === product.ref && item.catalogSlug === product.catalogSlug)
    if (!target) throw new Error('Produto não encontrado.')
    adminCatalog.value = data
    editingProduct.value = target
    editOpen.value = true
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    editingKey.value = ''
  }
}
async function productSaved() { await load() }
function categoryIcon(category) { return category?.icon || categoryIcons[category?.slug] || 'mdi-shape-outline' }
function setProducts(data) {
  data.items.forEach(product => {
    const key = selectionKey(product)
    if (!selections[key]) selections[key] = { color: product.colors[0] || '', size: product.sizes[0] || '', quantity: product.quantityStep, quickStarted: false }
  })
  result.value = data
}
async function load() {
  loading.value = true
  try {
    const params = { ...filters, catalog: catalogSlug.value, per_page: 24 }
    if (isInterpilhas.value) params.season = null
    setProducts((await api.get('/catalog', { params })).data)
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}
function adjust(product, direction) {
  const choice = selections[selectionKey(product)]
  choice.quantity = Math.max(product.quantityStep, choice.quantity + direction * product.quantityStep)
}
function addQuickQuantity(product, amount) {
  const choice = selections[selectionKey(product)]
  const step = Math.max(1, Number(product.quantityStep) || 1)
  const current = Math.max(step, Number(choice.quantity) || step)
  choice.quantity = choice.quickStarted ? current + Number(amount) : Number(amount)
  choice.quickStarted = true
  normalizeQuantity(product)
}
function resetQuickQuantity(product) {
  const choice = selections[selectionKey(product)]
  choice.quantity = Math.max(1, Number(product.quantityStep) || 1)
  choice.quickStarted = false
}
function normalizeQuantity(product) {
  const choice = selections[selectionKey(product)]
  const step = Math.max(1, Number(product.quantityStep) || 1)
  const value = Number(choice.quantity)
  choice.quantity = Number.isFinite(value) ? Math.max(step, Math.round(value / step) * step) : step
}
function seasonMeta(season) {
  return ({ inverno: { label: 'Inverno', icon: 'mdi-snowflake' }, verao: { label: 'Verão', icon: 'mdi-white-balance-sunny' }, ambos: { label: 'Todo o ano', icon: 'mdi-calendar-check-outline' } }[season] || { label: season, icon: 'mdi-calendar-outline' })
}
async function add(product) {
  const key = selectionKey(product)
  adding[key] = true
  try {
    const choice = selections[key]
    normalizeQuantity(product)
    await cart.add(product, choice.color, choice.size, choice.quantity)
    feedback.show('Produto adicionado ao carrinho.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    adding[key] = false
  }
}
function resetFilters() {
  Object.assign(filters, { q: '', category: categoryFromRoute(), subcategory: subcategoryFromRoute(), brand: null, family: null, season: null, sort: 'ref_asc', page: 1 })
}
function resetAdvancedFilters() {
  Object.assign(filters, { subcategory: null, brand: null, family: null, season: null, sort: 'ref_asc', page: 1 })
}
function selectCategory(category) {
  filters.category = category
  const query = { ...route.query }
  const routeValue = isInterpilhas.value ? publicCategoryKeys[category] || category : category
  if (routeValue) query.categoria = routeValue
  else delete query.categoria
  delete query.subcategoria
  router.replace({ path: route.path, query })
}
function selectSubcategory(subcategory) {
  filters.subcategory = subcategory
  const query = { ...route.query }
  if (subcategory) query.subcategoria = subcategory
  else delete query.subcategoria
  router.replace({ path: route.path, query })
}

watch(() => filters.category, () => { filters.subcategory = null; filters.page = 1 }, { flush: 'sync' })
watch(() => filters.q, value => {
  if (value && isInterpilhas.value) Object.assign(filters, { subcategory: null, brand: null, family: null, page: 1 })
})
watch(() => [filters.q, filters.subcategory, filters.brand, filters.family, filters.season, filters.sort], () => { filters.page = 1 })
watch(filters, () => { clearTimeout(timer); timer = setTimeout(load, 250) }, { deep: true })
watch(catalogSlug, () => { clearTimeout(timer); resetFilters(); load(); cart.load(catalogSlug.value).catch(() => {}) })
watch(() => [route.query.categoria, route.query.subcategoria], ([category, subcategory]) => {
  filters.category = categoryFromRoute(category)
  filters.subcategory = subcategoryFromRoute(subcategory)
  filters.page = 1
})
onMounted(() => { load(); cart.load(catalogSlug.value).catch(() => {}) })
</script>

<template>
  <div class="page catalog-page">
    <div class="page-head">
      <div>
        <div class="text-overline text-secondary font-weight-bold">Catálogo {{ activeCatalog.label }}</div>
        <h1 class="d-flex align-center ga-3"><v-icon v-if="isInterpilhas && selectedTopCategory" :icon="categoryIcon(selectedTopCategory)" color="primary" />{{ isInterpilhas && selectedTopCategory ? selectedTopCategory.label : activeCatalog.label }}</h1>
        <p>{{ result.total }} produtos disponíveis.</p>
      </div>
      <v-btn :to="`/carrinho/${publicCatalogSlug}`" color="primary" prepend-icon="mdi-cart-outline">Ver carrinho ({{ cart.carts[catalogSlug]?.units || 0 }})</v-btn>
    </div>

    <div v-if="!isInterpilhas && topCategories.length" class="category-shortcuts mb-5" aria-label="Categorias principais">
      <v-btn :variant="filters.category ? 'tonal' : 'flat'" :color="filters.category ? undefined : 'primary'" prepend-icon="mdi-view-grid-outline" @click="selectCategory(null)">Todos</v-btn>
      <v-btn v-for="category in topCategories" :key="category.slug" :variant="filters.category === category.slug ? 'flat' : 'tonal'" :color="filters.category === category.slug ? 'primary' : undefined" :prepend-icon="categoryIcon(category)" @click="selectCategory(category.slug)">{{ category.label }}</v-btn>
    </div>
    <div v-if="subcategories.length" class="subcategory-shortcuts mb-5" aria-label="Subcategorias">
      <v-btn :variant="filters.subcategory ? 'tonal' : 'flat'" :color="filters.subcategory ? undefined : 'secondary'" prepend-icon="mdi-view-grid-outline" @click="selectSubcategory(null)">Todas</v-btn>
      <v-btn v-for="subcategory in subcategories" :key="subcategory.slug" :variant="filters.subcategory === subcategory.slug ? 'flat' : 'tonal'" :color="filters.subcategory === subcategory.slug ? 'secondary' : undefined" :prepend-icon="categoryIcon(subcategory)" @click="selectSubcategory(subcategory.slug)">{{ subcategory.label }}</v-btn>
    </div>

    <div class="catalog-tools mb-6">
      <div class="catalog-tool-actions">
        <v-badge dot color="secondary" :model-value="Boolean(filters.q)">
          <v-btn icon="mdi-magnify" variant="tonal" :color="searchOpen ? 'primary' : undefined" aria-label="Abrir pesquisa" :aria-expanded="searchOpen" @click="searchOpen = !searchOpen" />
        </v-badge>
        <v-badge :content="activeFilterCount" color="secondary" :model-value="activeFilterCount > 0">
          <v-btn variant="tonal" prepend-icon="mdi-filter-variant" @click="filtersOpen = true">Filtros</v-btn>
        </v-badge>
      </div>
      <v-expand-transition>
        <v-text-field v-if="searchOpen" v-model="filters.q" autofocus hide-details clearable label="Pesquisar nome, referência ou EAN" prepend-inner-icon="mdi-magnify" class="catalog-search" />
      </v-expand-transition>
    </div>

    <v-dialog v-model="filtersOpen" max-width="640" scrollable>
      <v-card class="filter-dialog">
        <v-card-title class="d-flex align-center justify-space-between pa-5 pb-2">
          <span class="text-h6 font-weight-bold">Filtros do catálogo</span>
          <v-btn icon="mdi-close" variant="text" aria-label="Fechar filtros" @click="filtersOpen = false" />
        </v-card-title>
        <v-card-subtitle class="px-5 pb-4">Os resultados são atualizados automaticamente.</v-card-subtitle>
        <v-divider />
        <v-card-text class="pa-5">
          <v-row density="compact">
            <v-col v-if="!isInterpilhas" cols="12" sm="6"><v-select v-model="filters.category" clearable label="Categoria" :items="topCategories" item-title="label" item-value="slug" @update:model-value="selectCategory" /></v-col>
            <v-col v-if="subcategories.length" cols="12" sm="6"><v-select v-model="filters.subcategory" clearable label="Subcategoria" :items="subcategories" item-title="label" item-value="slug" @update:model-value="selectSubcategory" /></v-col>
            <v-col v-if="isInterpilhas" cols="12" sm="6"><v-select v-model="filters.brand" label="Marca" :items="brands" /></v-col>
            <v-col v-if="isInterpilhas && result.filters?.families?.length" cols="12" sm="6"><v-select v-model="filters.family" label="Família" :items="families" /></v-col>
            <v-col v-if="!isInterpilhas" cols="12" sm="6"><v-select v-model="filters.season" label="Estação" :items="seasons" /></v-col>
            <v-col cols="12" sm="6"><v-select v-model="filters.sort" label="Ordenar" :items="sorts" /></v-col>
          </v-row>
        </v-card-text>
        <v-divider />
        <v-card-actions class="pa-4 ga-2">
          <v-btn variant="text" prepend-icon="mdi-filter-remove-outline" :disabled="activeFilterCount === 0" @click="resetAdvancedFilters">Limpar filtros</v-btn>
          <v-spacer />
          <v-btn color="primary" variant="flat" @click="filtersOpen = false">Fechar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <div class="catalog-results-layout" :class="{ 'catalog-results-layout--split': tabletLandscape }">
      <section class="catalog-results" aria-label="Produtos">
    <v-row v-if="loading"><v-col v-for="i in 8" :key="i" cols="12" sm="6" md="4" lg="3"><v-skeleton-loader type="image, article" /></v-col></v-row>
    <v-row v-else>
      <v-col v-for="product in result.items" :key="selectionKey(product)" cols="12" sm="6" md="4" lg="3">
        <v-card class="soft-card product-card h-100 d-flex flex-column overflow-hidden">
          <div class="product-image-shell">
            <v-img :src="product.imageUrl" height="220" class="product-image catalog-product-image" :style="{ '--product-image-zoom': product.imageZoom || 1 }" contain><template #error><div class="d-flex fill-height align-center justify-center"><v-icon size="54" color="grey-lighten-1">mdi-image-outline</v-icon></div></template></v-img>
            <div class="product-card-actions">
              <v-btn icon="mdi-eye-outline" variant="text" size="small" class="product-card-action" title="Pré-visualizar produto" :aria-label="`Pré-visualizar ${product.name}`" @click.stop="openPreview(product)" />
              <v-btn v-if="auth.isAdmin" icon="mdi-pencil-outline" variant="text" size="small" class="product-card-action" title="Editar produto" :aria-label="`Editar ${product.name}`" :loading="editingKey === selectionKey(product)" @click.stop="openEditor(product)" />
            </div>
          </div>
          <v-card-text class="d-flex flex-column flex-grow-1">
            <div class="d-flex align-center justify-space-between ga-2 mb-1"><div class="text-caption text-medium-emphasis">{{ product.ref }} · {{ product.categoryLabel }}</div><v-chip v-if="product.brand" size="x-small" variant="tonal" color="primary">{{ product.brand }}</v-chip></div>
            <router-link :to="productPath(product)" class="catalog-product-name text-subtitle-1 font-weight-bold mt-1">{{ product.name }}</router-link>
            <div class="d-flex justify-space-between align-end mt-3 mb-3">
              <v-chip v-if="!isInterpilhas" size="small" variant="tonal" :prepend-icon="seasonMeta(product.season).icon">{{ seasonMeta(product.season).label }}</v-chip>
              <span v-else class="text-caption text-medium-emphasis">{{ product.family || product.type }}</span>
              <span class="price-stack text-right">
                <small v-if="product.promotion" class="original-price">{{ originalMainPrice(product) }} €</small>
                <strong class="text-h6 font-weight-black price-number">{{ mainPrice(product) }} €</strong>
                <v-chip v-if="product.promotion" size="x-small" color="success" variant="tonal" prepend-icon="mdi-sale-outline">{{ product.promotion.label }}</v-chip>
                <small v-if="isInterpilhas && Number(product.ecoValue || 0) > 0" class="eco-price">+ {{ priceValue(product.ecoValue, 3) }} € ecotaxa</small>
              </span>
            </div>
            <v-select v-if="product.colors.length" v-model="selections[selectionKey(product)].color" :items="product.colors" label="Cor" density="compact" variant="outlined" hide-details class="mb-3" />
            <v-select v-if="product.sizes.length" v-model="selections[selectionKey(product)].size" :items="product.sizes" label="Tamanho" density="compact" variant="outlined" hide-details class="mb-3" />
            <div class="d-flex align-center mt-auto w-100">
              <div v-if="isInterpilhas" class="utility-quantity-picker w-100">
                <div class="utility-quantity-heading"><span>Quantidade selecionada</span><b>{{ selections[selectionKey(product)].quantity }} un.</b></div>
                <div v-if="product.quickQuantities?.length" class="quick-quantities mb-2" aria-label="Atalhos de quantidade">
                  <v-btn v-for="amount in product.quickQuantities" :key="amount" size="small" variant="tonal" color="primary" :aria-label="`Adicionar ${amount} unidades de ${product.name}`" @click="addQuickQuantity(product, amount)">+{{ amount }} un.</v-btn>
                  <v-btn size="small" variant="text" prepend-icon="mdi-restore" @click="resetQuickQuantity(product)">Repor</v-btn>
                </div>
                <v-text-field v-else v-model.number="selections[selectionKey(product)].quantity" type="number" inputmode="numeric" :min="product.quantityStep" :step="product.quantityStep" aria-label="Quantidade em unidades" suffix="un." prepend-inner-icon="mdi-counter" density="compact" variant="solo-filled" flat hide-details class="quantity-field" @blur="normalizeQuantity(product)" @keydown.enter="$event.target.blur()" />
              </div>
              <div v-else class="quantity-control"><v-btn icon="mdi-minus" size="small" variant="tonal" :aria-label="`Diminuir quantidade de ${product.name}`" :disabled="selections[selectionKey(product)].quantity <= product.quantityStep" @click="adjust(product, -1)" /><b>{{ selections[selectionKey(product)].quantity }}</b><v-btn icon="mdi-plus" size="small" variant="tonal" :aria-label="`Aumentar quantidade de ${product.name}`" @click="adjust(product, 1)" /></div>
            </div>
            <v-btn block color="primary" class="mt-4" prepend-icon="mdi-cart-plus" :loading="adding[selectionKey(product)]" @click="add(product)">Adicionar ao carrinho</v-btn>
          </v-card-text>
        </v-card>
      </v-col>
    </v-row>

    <div v-if="!loading && !result.items.length" class="empty-state soft-card rounded-xl">
      <v-icon size="52">{{ isInterpilhas ? 'mdi-package-variant-plus' : 'mdi-package-variant-remove' }}</v-icon>
      <div class="text-h6 mt-3">Nenhum produto encontrado</div>
      <div>Experimente alterar a pesquisa ou os filtros.</div>
      <v-btn v-if="filters.q || filters.category || filters.brand || filters.family" variant="tonal" class="mt-4" prepend-icon="mdi-filter-remove-outline" @click="resetFilters">Limpar filtros</v-btn>
    </div>
    <v-pagination v-if="result.pages > 1" v-model="filters.page" :length="result.pages" class="mt-8" />
      </section>
      <aside v-if="tabletLandscape" class="catalog-cart-panel soft-card" aria-label="Resumo do carrinho">
        <div class="catalog-cart-panel__head"><div><small>Carrinho {{ activeCatalog.label }}</small><strong>{{ activeCart.units || 0 }} unidades</strong></div><v-icon color="primary">mdi-cart-outline</v-icon></div>
        <v-divider />
        <div v-if="activeCart.items.length" class="catalog-cart-lines">
          <div v-for="item in activeCart.items.slice(0, 5)" :key="item.id" class="catalog-cart-line">
            <v-avatar rounded="lg" size="44" color="grey-lighten-3"><v-img v-if="item.image_path" :src="`/media/${item.image_path}`" cover /><v-icon v-else size="20">mdi-package-variant</v-icon></v-avatar>
            <div><b>{{ item.name }}</b><small>{{ item.quantity }} un. · {{ item.ref }}</small></div>
          </div>
          <div v-if="activeCart.items.length > 5" class="text-caption text-medium-emphasis">+ {{ activeCart.items.length - 5 }} artigos no carrinho</div>
        </div>
        <div v-else class="catalog-cart-empty"><v-icon>mdi-cart-outline</v-icon><span>O carrinho está vazio.</span></div>
        <div class="catalog-cart-total"><span>Total</span><b>{{ Number(activeCart.total || 0).toFixed(2).replace('.', ',') }} €</b></div>
        <v-btn block color="primary" :to="`/carrinho/${publicCatalogSlug}`" prepend-icon="mdi-arrow-right">Abrir carrinho</v-btn>
      </aside>
    </div>
    <ProductPreviewDialog v-model="previewOpen" :product="previewProduct" />
    <ProductEditDialog v-model="editOpen" :product="editingProduct" :catalogs="adminCatalog.catalogs" :categories="adminCatalog.categories" @saved="productSaved" />
  </div>
</template>

<style scoped>
.category-shortcuts { display: flex; flex-wrap: wrap; gap: 10px; }
.subcategory-shortcuts { display: flex; flex-wrap: wrap; gap: 8px; padding-left: 8px; }
.catalog-tools { align-items: flex-start; display: flex; flex-direction: column; gap: 12px; }
.catalog-tool-actions { align-items: center; display: flex; gap: 10px; }
.catalog-search { max-width: 720px; width: 100%; }
.catalog-results-layout { min-width: 0; }
.catalog-results-layout--split { align-items: start; display: grid; gap: 20px; grid-template-columns: minmax(0, 1fr) 280px; }
.catalog-results { min-width: 0; }
.catalog-results-layout--split :deep(.v-col-md-4) { flex: 0 0 50%; max-width: 50%; }
.catalog-cart-panel { background: rgb(var(--v-theme-surface)); padding: 16px; position: sticky; top: 84px; }
.catalog-cart-panel__head { align-items: center; display: flex; justify-content: space-between; padding: 2px 2px 14px; }
.catalog-cart-panel__head > div { display: flex; flex-direction: column; gap: 2px; }
.catalog-cart-panel__head small { color: rgba(var(--v-theme-on-surface), .58); }
.catalog-cart-lines { display: grid; gap: 12px; padding-block: 14px; }
.catalog-cart-line { align-items: center; display: grid; gap: 10px; grid-template-columns: 44px minmax(0, 1fr); }
.catalog-cart-line b, .catalog-cart-line small { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog-cart-line b { font-size: .78rem; }
.catalog-cart-line small { color: rgba(var(--v-theme-on-surface), .58); font-size: .68rem; margin-top: 3px; }
.catalog-cart-empty { align-items: center; color: rgba(var(--v-theme-on-surface), .56); display: flex; flex-direction: column; gap: 8px; padding: 28px 8px; }
.catalog-cart-total { align-items: baseline; border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: flex; justify-content: space-between; margin-top: 4px; padding: 14px 2px; }
.catalog-cart-total b { font-size: 1.1rem; font-variant-numeric: tabular-nums; }
.filter-dialog { border-radius: 18px !important; }
.product-image-shell { overflow: hidden; position: relative; }
.catalog-product-image { overflow: hidden; width: 100%; }
.catalog-product-image :deep(.v-img__img) { object-position: center; transform: scale(var(--product-image-zoom, 1)); transform-origin: center; }
.product-card { contain: layout paint style; content-visibility: auto; contain-intrinsic-size: 520px; }
.product-card-actions { display: flex; flex-direction: column; gap: 6px; opacity: .34; position: absolute; right: 8px; top: 8px; transition: opacity .15s ease; z-index: 2; }
.product-card-actions:hover, .product-card-actions:focus-within { opacity: 1; }
.product-card-action { backdrop-filter: blur(3px); background: rgba(var(--v-theme-surface), .38) !important; box-shadow: 0 2px 8px rgba(var(--v-theme-on-surface), .08); color: rgba(var(--v-theme-on-surface), .62) !important; height: 44px !important; min-width: 44px !important; transition: background-color .15s ease, color .15s ease, opacity .15s ease; width: 44px !important; }
.product-card-action:hover, .product-card-action:focus-visible { background: rgba(var(--v-theme-surface), .82) !important; color: rgb(var(--v-theme-primary)) !important; opacity: 1; }
.catalog-product-name { color: inherit; line-height: 1.35; min-height: 2.7em; text-decoration: none; }
.catalog-product-name:hover { color: rgb(var(--v-theme-primary)); }
.quantity-control { align-items: center; display: flex; gap: 10px; }
.quantity-control b { min-width: 30px; text-align: center; }
.utility-quantity-picker { background: rgba(var(--v-theme-primary), .045); border: 1px solid rgba(var(--v-theme-primary), .12); border-radius: 12px; padding: 12px; }
.utility-quantity-heading { align-items: baseline; display: flex; justify-content: space-between; margin-bottom: 8px; }
.utility-quantity-heading > span { font-size: .82rem; font-weight: 800; }
.utility-quantity-heading > b { color: rgb(var(--v-theme-primary)); font-variant-numeric: tabular-nums; }
.utility-quantity-heading small { color: rgba(var(--v-theme-on-surface), .58); font-size: .7rem; }
.quantity-field { width: 100%; }
.quantity-field :deep(.v-field) { background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-theme-on-surface), .09); box-shadow: none; }
.quantity-field :deep(input) { font-size: 1.05rem; font-variant-numeric: tabular-nums; font-weight: 800; }
.quick-quantities { display: flex; flex-wrap: wrap; gap: 8px; }
.quick-quantities :deep(.v-btn) { min-height: 44px; min-width: 70px; }
.price-number { font-variant-numeric: tabular-nums; }
.price-stack { align-items: flex-end; display: inline-flex; flex-direction: column; line-height: 1.15; }
.original-price { color: rgba(var(--v-theme-on-surface), .52); font-variant-numeric: tabular-nums; text-decoration: line-through; }
.eco-price { color: rgba(var(--v-theme-on-surface), .55); font-size: .72rem; font-variant-numeric: tabular-nums; font-weight: 500; margin-top: 4px; white-space: nowrap; }
</style>
