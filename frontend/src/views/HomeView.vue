<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'

const router = useRouter()
const auth = useAuthStore()
const feedback = useFeedbackStore()
const campaigns = ref([])
const loading = ref(true)
const activeCatalog = ref('')

const publicCatalogLabel = product => product.catalogSlug === 'interpilhas' ? 'Utilidades' : product.catalogLabel || product.catalogSlug
const campaignCatalogs = computed(() => {
  const catalogs = new Map()
  for (const campaign of campaigns.value) {
    for (const product of campaign.products || []) {
      if (!catalogs.has(product.catalogSlug)) catalogs.set(product.catalogSlug, { slug: product.catalogSlug, label: publicCatalogLabel(product), campaigns: [] })
    }
  }
  for (const catalog of catalogs.values()) {
    for (const campaign of campaigns.value) {
      const products = (campaign.products || []).filter(product => product.catalogSlug === catalog.slug)
      if (products.length) catalog.campaigns.push({ ...campaign, products })
    }
  }
  return [...catalogs.values()].sort((a, b) => {
    const aIndex = auth.catalogs.indexOf(a.slug)
    const bIndex = auth.catalogs.indexOf(b.slug)
    return (aIndex < 0 ? 999 : aIndex) - (bIndex < 0 ? 999 : bIndex) || a.label.localeCompare(b.label, 'pt')
  })
})
const activeCampaigns = computed(() => campaignCatalogs.value.find(catalog => catalog.slug === activeCatalog.value)?.campaigns || [])
const activeCatalogLabel = computed(() => campaignCatalogs.value.find(catalog => catalog.slug === activeCatalog.value)?.label || '')

const productRoute = product => `/catalogo/${product.catalogSlug === 'interpilhas' ? 'utilidades' : product.catalogSlug}/${product.ref}`
const campaignRoute = campaign => campaign.products.length === 1 ? productRoute(campaign.products[0]) : { path: '/', hash: `#campanha-${campaign.id}-produtos` }
const money = product => `${Number(product.price || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2)} €`
const originalMoney = product => `${Number(product.originalPrice || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2)} €`

onMounted(async () => {
  try {
    campaigns.value = (await api.get('/campaigns/active')).data.campaigns || []
    if (!campaigns.value.length) await router.replace(auth.isAdmin ? '/admin' : '/encomendas')
    else activeCatalog.value = campaignCatalogs.value[0]?.slug || ''
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
    await router.replace(auth.isAdmin ? '/admin' : '/encomendas')
  } finally { loading.value = false }
})
</script>

<template>
  <div class="page campaign-home">
    <v-progress-linear v-if="loading" indeterminate color="secondary" />
    <template v-else>
      <div class="page-head campaign-home-head"><div><h1>Campanhas</h1><p>Produtos e condições especiais disponíveis neste momento.</p></div></div>

      <v-card v-if="campaignCatalogs.length > 1" class="soft-card campaign-catalog-bar">
        <span>Catálogo</span>
        <v-btn-toggle v-model="activeCatalog" mandatory color="primary" class="campaign-catalog-switch" aria-label="Filtrar campanhas por catálogo">
          <v-btn v-for="catalog in campaignCatalogs" :key="catalog.slug" :value="catalog.slug" :prepend-icon="catalog.slug === 'interpilhas' ? 'mdi-battery-medium' : 'mdi-shopping-outline'">{{ catalog.label }}</v-btn>
        </v-btn-toggle>
      </v-card>

      <section v-for="campaign in activeCampaigns" :key="campaign.id" class="campaign-section">
        <router-link :to="campaignRoute(campaign)" class="campaign-banner" :class="{ 'has-image': campaign.imageUrl, 'image-only': campaign.imageUrl && campaign.showText === false }">
          <img v-if="campaign.imageUrl" :src="campaign.imageUrl" :alt="`Imagem da campanha ${campaign.title}`" class="campaign-banner-image" />
          <div v-if="campaign.showText !== false" class="campaign-banner-copy">
            <span>Campanha · {{ activeCatalogLabel }}</span>
            <h2>{{ campaign.title }}</h2>
            <p v-if="campaign.description">{{ campaign.description }}</p>
            <small>Ver produtos <v-icon size="17" aria-hidden="true">mdi-arrow-right</v-icon></small>
          </div>
        </router-link>
        <div class="campaign-products-head"><h3>Produtos da campanha</h3><span>{{ campaign.products.length }} {{ campaign.products.length === 1 ? 'produto' : 'produtos' }}</span></div>
        <v-row :id="`campanha-${campaign.id}-produtos`" class="mt-1 campaign-products-anchor">
          <v-col v-for="product in campaign.products" :key="product.ref" cols="12" sm="6" md="4" lg="3">
            <v-card :to="productRoute(product)" class="soft-card campaign-product h-100">
              <div class="campaign-product-image">
                <v-img v-if="product.imageUrl" :src="product.imageUrl" :alt="product.name" contain :style="{ '--campaign-product-zoom': product.imageZoom || 1 }" />
                <v-icon v-else size="52" color="secondary">mdi-package-variant-closed</v-icon>
                <v-chip v-if="product.promotion" class="campaign-discount" size="small" color="error" variant="flat">{{ product.promotion.label }}</v-chip>
              </div>
              <v-card-text class="campaign-product-body">
                <div class="campaign-product-meta"><span>{{ publicCatalogLabel(product) }}</span><b>{{ product.ref }}</b></div>
                <div class="campaign-product-name">{{ product.name }}</div>
                <div class="campaign-product-footer"><div><div v-if="product.promotion" class="original-price">Antes {{ originalMoney(product) }}</div><b class="campaign-price">{{ money(product) }}</b></div><v-icon color="primary" size="22" aria-hidden="true">mdi-chevron-right</v-icon></div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </section>
    </template>
  </div>
</template>

<style scoped>
.campaign-home { max-width: 1440px; }
.campaign-home-head { margin-bottom: 20px; }
.campaign-catalog-bar { align-items: center; display: flex; gap: 18px; margin-bottom: 24px; padding: 10px 12px 10px 18px; }
.campaign-catalog-bar > span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; font-weight: 700; }
.campaign-catalog-switch { display: flex; flex-wrap: wrap; gap: 4px; height: auto; }
.campaign-catalog-switch :deep(.v-btn) { min-height: 42px; text-transform: none; }
.campaign-section + .campaign-section { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); margin-top: 36px; padding-top: 36px; }
.campaign-banner { align-items: center; aspect-ratio: 3 / 1; background: rgb(var(--v-theme-primary)); border-radius: 12px; color: white; display: flex; margin-bottom: 18px; min-height: 250px; overflow: hidden; padding: clamp(16px, 3vw, 40px); position: relative; text-decoration: none; width: 100%; }
.campaign-banner-image { height: 100%; inset: 0; object-fit: contain; position: absolute; width: 100%; }
.campaign-banner-copy { background: rgba(var(--v-theme-primary), .92); border-radius: 9px; max-width: min(560px, 66%); padding: clamp(16px, 2.5vw, 30px); position: relative; z-index: 1; }
.campaign-banner:not(.has-image) .campaign-banner-copy { background: transparent; padding-left: 0; }
.campaign-banner-copy > span { font-size: .75rem; font-weight: 700; }
.campaign-banner h2 { font-size: clamp(1.5rem, 3vw, 2.35rem); line-height: 1.12; margin: 5px 0 0; }
.campaign-banner p { font-size: .92rem; margin: 8px 0 0; opacity: .82; white-space: pre-line; }
.campaign-banner-copy small { align-items: center; display: inline-flex; font-size: .78rem; font-weight: 700; gap: 4px; margin-top: 16px; }
.campaign-banner.image-only { background: rgb(var(--v-theme-surface)); padding: 0; }
.campaign-banner.image-only .campaign-banner-image { object-fit: cover; }
.campaign-products-head { align-items: center; display: flex; justify-content: space-between; margin: 0 2px 6px; }
.campaign-products-head h3 { font-size: 1rem; margin: 0; }
.campaign-products-head span { color: rgba(var(--v-theme-on-surface), .58); font-size: .78rem; }
.campaign-products-anchor { scroll-margin-top: 96px; }
.campaign-product { border-radius: 12px; overflow: hidden; transition: border-color .16s ease; }
.campaign-product:hover { border-color: rgba(var(--v-theme-primary), .38) !important; }
.campaign-product:focus-visible { outline: 3px solid rgba(var(--v-theme-primary), .28); outline-offset: 3px; }
.campaign-product-image { align-items: center; background: rgba(var(--v-theme-primary), .025); border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: flex; height: 220px; justify-content: center; overflow: hidden; padding: 16px; position: relative; }
.campaign-product-image .v-img { height: 100%; transform: scale(var(--campaign-product-zoom, 1)); width: 100%; }
.campaign-discount { position: absolute; right: 10px; top: 10px; z-index: 1; }
.campaign-product-body { display: flex; flex-direction: column; min-height: 152px; padding: 16px 18px 18px; }
.campaign-product-meta { align-items: center; color: rgba(var(--v-theme-on-surface), .58); display: flex; font-size: .72rem; gap: 8px; justify-content: space-between; }
.campaign-product-meta b { color: rgb(var(--v-theme-primary)); }
.campaign-product-name { display: -webkit-box; font-size: 1rem; font-weight: 700; line-height: 1.35; margin-top: 8px; min-height: 2.7em; overflow: hidden; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.campaign-product-footer { align-items: flex-end; border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: flex; gap: 12px; justify-content: space-between; margin-top: auto; padding-top: 13px; }
.campaign-price { color: rgb(var(--v-theme-primary)); font-size: 1.2rem; font-variant-numeric: tabular-nums; }
.original-price { color: rgba(var(--v-theme-on-surface), .52); font-size: .72rem; text-decoration: line-through; }
@media (max-width: 800px) { .campaign-catalog-bar { align-items: stretch; flex-direction: column; gap: 6px; padding: 12px; } .campaign-catalog-switch { width: 100%; } .campaign-catalog-switch :deep(.v-btn) { flex: 1; } .campaign-banner-copy { max-width: 76%; } }
@media (max-width: 600px) { .campaign-catalog-switch { flex-direction: column; } .campaign-catalog-switch :deep(.v-btn) { width: 100%; } .campaign-banner { aspect-ratio: auto; border-radius: 12px; min-height: 210px; padding: 12px; } .campaign-banner.image-only { aspect-ratio: 3 / 1; min-height: 0; } .campaign-banner-copy { max-width: 88%; padding: 15px; } .campaign-banner h2 { font-size: clamp(1.25rem, 7vw, 1.8rem); } .campaign-banner p { display: none; } .campaign-product-image { height: 235px; } }
</style>
