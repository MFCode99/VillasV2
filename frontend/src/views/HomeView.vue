<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const feedback = useFeedbackStore()
const campaigns = ref([])
const loading = ref(true)
const activeCatalog = ref('')
const selectedCampaignId = ref(null)

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
const selectedCampaign = computed(() => activeCampaigns.value.find(campaign => campaign.id === selectedCampaignId.value) || null)

const productRoute = product => `/catalogo/${product.catalogSlug === 'interpilhas' ? 'utilidades' : product.catalogSlug}/${product.ref}`
const money = product => `${Number(product.price || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2)} €`
const originalMoney = product => `${Number(product.originalPrice || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2)} €`
const shortDate = value => new Intl.DateTimeFormat('pt-PT', { day: '2-digit', month: 'short', year: 'numeric' }).format(new Date(value))
const campaignPeriod = campaign => {
  if (campaign.startsAt && campaign.endsAt) return `${shortDate(campaign.startsAt)} – ${shortDate(campaign.endsAt)}`
  if (campaign.endsAt) return `Até ${shortDate(campaign.endsAt)}`
  if (campaign.startsAt) return `Desde ${shortDate(campaign.startsAt)}`
  return 'Campanha ativa'
}

const syncCampaignFromRoute = () => {
  const requestedId = Number(route.query.campanha)
  if (!Number.isInteger(requestedId) || requestedId <= 0) {
    selectedCampaignId.value = null
    return
  }
  const catalog = campaignCatalogs.value.find(item => item.campaigns.some(campaign => campaign.id === requestedId))
  if (!catalog) {
    selectedCampaignId.value = null
    return
  }
  activeCatalog.value = catalog.slug
  selectedCampaignId.value = requestedId
}

const openCampaign = campaign => {
  router.push({ path: '/', query: { ...route.query, campanha: String(campaign.id) } })
}

const closeCampaign = () => {
  const query = { ...route.query }
  delete query.campanha
  router.push({ path: '/', query })
}

watch(() => route.query.campanha, syncCampaignFromRoute)

onMounted(async () => {
  try {
    campaigns.value = (await api.get('/campaigns/active')).data.campaigns || []
    if (!campaigns.value.length) await router.replace(auth.isAdmin ? '/admin' : '/encomendas')
    else {
      activeCatalog.value = campaignCatalogs.value[0]?.slug || ''
      syncCampaignFromRoute()
    }
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
      <template v-if="!selectedCampaign">
        <div class="page-head campaign-home-head">
          <div>
            <h1>Campanhas</h1>
            <p>Descubra as campanhas disponíveis e toque numa delas para ver os produtos.</p>
          </div>
          <v-chip color="primary" variant="tonal" prepend-icon="mdi-sale-outline">
            {{ activeCampaigns.length }} {{ activeCampaigns.length === 1 ? 'campanha' : 'campanhas' }}
          </v-chip>
        </div>

        <v-card v-if="campaignCatalogs.length > 1" class="soft-card campaign-catalog-bar">
          <span>Catálogo</span>
          <v-btn-toggle v-model="activeCatalog" mandatory color="primary" class="campaign-catalog-switch" aria-label="Filtrar campanhas por catálogo">
            <v-btn v-for="catalog in campaignCatalogs" :key="catalog.slug" :value="catalog.slug" :prepend-icon="catalog.slug === 'interpilhas' ? 'mdi-battery-medium' : 'mdi-shopping-outline'">{{ catalog.label }}</v-btn>
          </v-btn-toggle>
        </v-card>

        <section class="campaign-list soft-card" aria-label="Campanhas disponíveis">
          <button
            v-for="campaign in activeCampaigns"
            :key="campaign.id"
            type="button"
            class="campaign-list-item"
            :aria-label="`Abrir campanha ${campaign.title}, ${campaign.products.length} produtos`"
            @click="openCampaign(campaign)"
          >
            <span class="campaign-list-media">
              <img v-if="campaign.imageUrl" :src="campaign.imageUrl" :alt="`Imagem da campanha ${campaign.title}`" loading="lazy" />
              <v-icon v-else size="42" color="primary" aria-hidden="true">mdi-sale-outline</v-icon>
            </span>

            <span class="campaign-list-content">
              <span class="campaign-list-title-row">
                <strong>{{ campaign.title }}</strong>
                <span class="campaign-active-badge">Em destaque</span>
              </span>
              <span v-if="campaign.showText !== false && campaign.description" class="campaign-list-description">{{ campaign.description }}</span>
              <span class="campaign-list-meta">
                <span><v-icon size="16" aria-hidden="true">mdi-calendar-blank-outline</v-icon>{{ campaignPeriod(campaign) }}</span>
                <span><v-icon size="16" aria-hidden="true">mdi-package-variant-closed</v-icon>{{ campaign.products.length }} {{ campaign.products.length === 1 ? 'produto' : 'produtos' }}</span>
                <span><v-icon size="16" aria-hidden="true">mdi-tag-outline</v-icon>{{ activeCatalogLabel }}</span>
              </span>
              <span class="campaign-reference-list" aria-hidden="true">
                <span v-for="product in campaign.products.slice(0, 6)" :key="product.ref">{{ product.ref }}</span>
                <span v-if="campaign.products.length > 6">+{{ campaign.products.length - 6 }}</span>
              </span>
            </span>

            <span class="campaign-list-open">
              <span>Ver produtos</span>
              <v-icon size="24" aria-hidden="true">mdi-chevron-right</v-icon>
            </span>
          </button>
        </section>
      </template>

      <template v-else>
        <div class="campaign-detail-nav">
          <v-btn variant="text" prepend-icon="mdi-arrow-left" class="campaign-back" @click="closeCampaign">Todas as campanhas</v-btn>
          <v-chip color="primary" variant="tonal">{{ selectedCampaign.products.length }} {{ selectedCampaign.products.length === 1 ? 'produto' : 'produtos' }}</v-chip>
        </div>

        <section class="campaign-detail-head">
          <div
            class="campaign-banner"
            :class="{ 'has-image': selectedCampaign.imageUrl, 'image-only': selectedCampaign.imageUrl && selectedCampaign.showText === false }"
          >
            <img v-if="selectedCampaign.imageUrl" :src="selectedCampaign.imageUrl" :alt="`Imagem da campanha ${selectedCampaign.title}`" class="campaign-banner-image" />
            <div v-if="selectedCampaign.showText !== false" class="campaign-banner-copy">
              <span>Campanha · {{ activeCatalogLabel }}</span>
              <h1>{{ selectedCampaign.title }}</h1>
              <p v-if="selectedCampaign.description">{{ selectedCampaign.description }}</p>
              <small><v-icon size="16" aria-hidden="true">mdi-calendar-blank-outline</v-icon>{{ campaignPeriod(selectedCampaign) }}</small>
            </div>
            <h1 v-else class="sr-only">{{ selectedCampaign.title }}</h1>
          </div>
        </section>

        <div class="campaign-products-head">
          <div>
            <span>Produtos em campanha</span>
            <h2>{{ selectedCampaign.title }}</h2>
          </div>
          <span>{{ selectedCampaign.products.length }} disponíveis</span>
        </div>

        <v-row class="campaign-products-grid">
          <v-col v-for="product in selectedCampaign.products" :key="product.ref" cols="12" sm="6" md="4" lg="3">
            <v-card :to="productRoute(product)" class="soft-card campaign-product h-100">
              <div class="campaign-product-image">
                <v-img v-if="product.imageUrl" :src="product.imageUrl" :alt="product.name" contain :style="{ '--campaign-product-zoom': product.imageZoom || 1 }" />
                <v-icon v-else size="52" color="secondary">mdi-package-variant-closed</v-icon>
                <v-chip v-if="product.promotion" class="campaign-discount" size="small" color="error" variant="flat">{{ product.promotion.label }}</v-chip>
              </div>
              <v-card-text class="campaign-product-body">
                <div class="campaign-product-meta"><span>{{ publicCatalogLabel(product) }}</span><b>{{ product.ref }}</b></div>
                <div class="campaign-product-name">{{ product.name }}</div>
                <div class="campaign-product-footer">
                  <div>
                    <div v-if="product.promotion" class="original-price">Antes {{ originalMoney(product) }}</div>
                    <b class="campaign-price">{{ money(product) }}</b>
                  </div>
                  <v-icon color="primary" size="22" aria-hidden="true">mdi-chevron-right</v-icon>
                </div>
              </v-card-text>
            </v-card>
          </v-col>
        </v-row>
      </template>
    </template>
  </div>
</template>

<style scoped>
.campaign-home { max-width: 1440px; }
.campaign-home-head { align-items: flex-end; margin-bottom: 20px; }
.campaign-catalog-bar { align-items: center; display: flex; gap: 18px; margin-bottom: 20px; padding: 10px 12px 10px 18px; }
.campaign-catalog-bar > span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; font-weight: 700; }
.campaign-catalog-switch { display: flex; flex-wrap: wrap; gap: 4px; height: auto; }
.campaign-catalog-switch :deep(.v-btn) { min-height: 42px; text-transform: none; }
.campaign-list { overflow: hidden; padding: 0; }
.campaign-list-item { align-items: center; background: rgb(var(--v-theme-surface)); border: 0; border-bottom: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: grid; font: inherit; gap: 18px; grid-template-columns: 150px minmax(0, 1fr) auto; min-height: 154px; padding: 18px 20px; text-align: left; touch-action: manipulation; transition: background-color .16s ease, transform .12s ease; width: 100%; }
.campaign-list-item:last-child { border-bottom: 0; }
.campaign-list-item:hover { background: rgba(var(--v-theme-primary), .035); }
.campaign-list-item:active { transform: scale(.997); }
.campaign-list-item:focus-visible { box-shadow: inset 0 0 0 3px rgba(var(--v-theme-primary), .34); outline: 0; position: relative; z-index: 1; }
.campaign-list-media { align-items: center; aspect-ratio: 3 / 2; background: rgba(var(--v-theme-primary), .045); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 10px; display: flex; justify-content: center; overflow: hidden; width: 150px; }
.campaign-list-media img { height: 100%; object-fit: cover; width: 100%; }
.campaign-list-content { display: flex; min-width: 0; flex-direction: column; gap: 8px; }
.campaign-list-title-row { align-items: center; display: flex; flex-wrap: wrap; gap: 9px; }
.campaign-list-title-row strong { font-size: 1rem; line-height: 1.3; }
.campaign-active-badge { background: rgba(var(--v-theme-secondary), .11); border-radius: 999px; color: rgb(var(--v-theme-secondary)); font-size: .7rem; font-weight: 700; padding: 5px 9px; }
.campaign-list-description { color: rgba(var(--v-theme-on-surface), .67); display: -webkit-box; font-size: .84rem; line-height: 1.45; overflow: hidden; white-space: pre-line; -webkit-box-orient: vertical; -webkit-line-clamp: 2; }
.campaign-list-meta { align-items: center; color: rgba(var(--v-theme-on-surface), .58); display: flex; flex-wrap: wrap; font-size: .74rem; gap: 8px 18px; }
.campaign-list-meta > span { align-items: center; display: inline-flex; gap: 5px; }
.campaign-reference-list { display: flex; flex-wrap: wrap; gap: 5px; }
.campaign-reference-list > span { background: rgba(var(--v-theme-on-surface), .055); border-radius: 5px; color: rgba(var(--v-theme-on-surface), .67); font-size: .68rem; font-weight: 700; padding: 4px 7px; }
.campaign-list-open { align-items: center; color: rgb(var(--v-theme-primary)); display: inline-flex; font-size: .78rem; font-weight: 700; gap: 4px; white-space: nowrap; }
.campaign-detail-nav { align-items: center; display: flex; justify-content: space-between; margin: -6px 0 14px; }
.campaign-back { margin-left: -12px; text-transform: none; }
.campaign-detail-head { margin-bottom: 24px; }
.campaign-banner { align-items: center; aspect-ratio: 3 / 1; background: rgb(var(--v-theme-primary)); border-radius: 14px; color: white; display: flex; min-height: 230px; overflow: hidden; padding: clamp(16px, 3vw, 40px); position: relative; width: 100%; }
.campaign-banner-image { height: 100%; inset: 0; object-fit: contain; position: absolute; width: 100%; }
.campaign-banner-copy { background: rgba(var(--v-theme-primary), .92); border-radius: 10px; max-width: min(560px, 66%); padding: clamp(16px, 2.5vw, 30px); position: relative; z-index: 1; }
.campaign-banner:not(.has-image) .campaign-banner-copy { background: transparent; padding-left: 0; }
.campaign-banner-copy > span { font-size: .75rem; font-weight: 700; }
.campaign-banner h1 { font-size: clamp(1.5rem, 3vw, 2.35rem); line-height: 1.12; margin: 5px 0 0; }
.campaign-banner p { font-size: .92rem; margin: 8px 0 0; opacity: .85; white-space: pre-line; }
.campaign-banner-copy small { align-items: center; display: inline-flex; font-size: .74rem; font-weight: 700; gap: 5px; margin-top: 16px; }
.campaign-banner.image-only { background: rgb(var(--v-theme-surface)); padding: 0; }
.campaign-banner.image-only .campaign-banner-image { object-fit: cover; }
.campaign-products-head { align-items: flex-end; display: flex; justify-content: space-between; margin: 0 2px 10px; }
.campaign-products-head > div > span { color: rgb(var(--v-theme-secondary)); font-size: .74rem; font-weight: 700; }
.campaign-products-head h2 { font-size: 1.25rem; line-height: 1.3; margin: 2px 0 0; }
.campaign-products-head > span { color: rgba(var(--v-theme-on-surface), .58); font-size: .78rem; }
.campaign-products-grid { margin-top: 0; }
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
.sr-only { height: 1px; margin: -1px; overflow: hidden; padding: 0; position: absolute; width: 1px; clip: rect(0, 0, 0, 0); white-space: nowrap; }
@media (max-width: 900px) {
  .campaign-list-item { grid-template-columns: 124px minmax(0, 1fr) auto; padding: 16px; }
  .campaign-list-media { width: 124px; }
  .campaign-list-open > span { display: none; }
}
@media (max-width: 800px) {
  .campaign-catalog-bar { align-items: stretch; flex-direction: column; gap: 6px; padding: 12px; }
  .campaign-catalog-switch { width: 100%; }
  .campaign-catalog-switch :deep(.v-btn) { flex: 1; }
  .campaign-banner-copy { max-width: 76%; }
}
@media (max-width: 600px) {
  .campaign-home-head { align-items: flex-start; gap: 12px; }
  .campaign-catalog-switch { flex-direction: column; }
  .campaign-catalog-switch :deep(.v-btn) { width: 100%; }
  .campaign-list-item { align-items: start; gap: 12px; grid-template-columns: 92px minmax(0, 1fr) 24px; min-height: 126px; padding: 14px 12px; }
  .campaign-list-media { width: 92px; }
  .campaign-list-title-row { gap: 6px; }
  .campaign-list-title-row strong { font-size: .94rem; }
  .campaign-active-badge { display: none; }
  .campaign-list-description { font-size: .78rem; -webkit-line-clamp: 1; }
  .campaign-list-meta { gap: 4px 10px; }
  .campaign-list-meta > span:nth-child(3) { display: none; }
  .campaign-reference-list > span:nth-child(n+4) { display: none; }
  .campaign-list-open { align-self: center; }
  .campaign-detail-nav { margin-top: -10px; }
  .campaign-banner { aspect-ratio: auto; border-radius: 12px; min-height: 210px; padding: 12px; }
  .campaign-banner.image-only { aspect-ratio: 3 / 1; min-height: 0; }
  .campaign-banner-copy { max-width: 88%; padding: 15px; }
  .campaign-banner h1 { font-size: clamp(1.25rem, 7vw, 1.8rem); }
  .campaign-banner p { display: none; }
  .campaign-products-head { align-items: flex-start; flex-direction: column; gap: 4px; }
  .campaign-product-image { height: 235px; }
}
</style>
