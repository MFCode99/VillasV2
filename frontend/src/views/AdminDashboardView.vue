<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const data = ref(null)
const loading = ref(true)
const refreshing = ref(false)
const cartSearch = ref('')
const cartCatalog = ref('all')
let refreshTimer = null

const money = value => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
const number = value => new Intl.NumberFormat('pt-PT').format(Number(value || 0))
const dateTime = value => value ? new Intl.DateTimeFormat('pt-PT', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—'

const cartActivity = computed(() => data.value?.pendingCartActivity || { summary: {}, customers: [] })
const catalogOptions = computed(() => {
  const catalogs = new Map()
  for (const customer of cartActivity.value.customers || []) {
    for (const catalog of customer.catalogs || []) catalogs.set(catalog.catalogSlug, catalog.catalogLabel)
  }
  return [{ title: 'Todos os catálogos', value: 'all' }, ...Array.from(catalogs, ([value, title]) => ({ title, value }))]
})
const filteredCartCustomers = computed(() => {
  const query = cartSearch.value.trim().toLocaleLowerCase('pt-PT')
  return (cartActivity.value.customers || []).filter(customer => {
    const matchesCatalog = cartCatalog.value === 'all' || customer.catalogs.some(catalog => catalog.catalogSlug === cartCatalog.value)
    const haystack = `${customer.name} ${customer.username} ${customer.company || ''}`.toLocaleLowerCase('pt-PT')
    return matchesCatalog && (!query || haystack.includes(query))
  })
})

function relativeTime(value) {
  if (!value) return 'Sem data'
  const elapsed = Math.max(0, Date.now() - new Date(value).getTime())
  const minutes = Math.floor(elapsed / 60000)
  if (minutes < 1) return 'Agora'
  if (minutes < 60) return `Há ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Há ${hours} h`
  const days = Math.floor(hours / 24)
  if (days < 30) return `Há ${days} ${days === 1 ? 'dia' : 'dias'}`
  return dateTime(value)
}

async function load({ silent = false } = {}) {
  if (silent) refreshing.value = true
  else loading.value = true
  try {
    data.value = (await api.get('/admin/dashboard')).data
  } catch (error) {
    if (!silent) feedback.show(errorMessage(error), 'error')
  } finally {
    loading.value = false
    refreshing.value = false
  }
}

onMounted(async () => {
  await load()
  refreshTimer = window.setInterval(() => load({ silent: true }), 30000)
})
onBeforeUnmount(() => window.clearInterval(refreshTimer))
</script>

<template>
  <div class="page dashboard-page">
    <div class="page-head">
      <div><h1>Visão geral</h1><p>O estado do negócio num só lugar.</p></div>
      <v-btn to="/admin/encomendas/nova" color="primary" prepend-icon="mdi-plus">Nova encomenda</v-btn>
    </div>

    <v-skeleton-loader v-if="loading" type="article, article, table" />
    <template v-else-if="data">
      <v-row>
        <v-col v-for="metric in [
          ['Encomendas pendentes', data.metrics.pending_orders, 'mdi-clock-outline', 'warning'],
          ['Confirmadas', data.metrics.confirmed_orders, 'mdi-check-circle-outline', 'success'],
          ['Clientes', data.metrics.total_clients, 'mdi-account-group-outline', 'info'],
          ['Vendas este mês', money(data.metrics.month_confirmed_revenue), 'mdi-currency-eur', 'secondary']
        ]" :key="metric[0]" cols="12" sm="6" lg="3">
          <v-card class="metric soft-card">
            <div class="d-flex justify-space-between"><div class="metric-label">{{ metric[0] }}</div><v-icon :color="metric[3]">{{ metric[2] }}</v-icon></div>
            <div class="metric-value">{{ metric[1] }}</div>
          </v-card>
        </v-col>
      </v-row>

      <v-card class="soft-card pending-carts-card mt-5 overflow-hidden">
        <div class="pending-carts-head">
          <div class="section-title">
            <div class="section-icon"><v-icon aria-hidden="true">mdi-cart-outline</v-icon></div>
            <div><h2>Carrinhos pendentes</h2><p>Clientes que adicionaram produtos e ainda não concluíram a encomenda.</p></div>
          </div>
          <v-btn icon="mdi-refresh" variant="text" :loading="refreshing" aria-label="Atualizar carrinhos pendentes" @click="load({ silent: true })" />
        </div>

        <div class="cart-summary" aria-live="polite">
          <div><span>Clientes</span><strong>{{ number(cartActivity.summary.customers) }}</strong></div>
          <div><span>Carrinhos</span><strong>{{ number(cartActivity.summary.carts) }}</strong></div>
          <div><span>Unidades</span><strong>{{ number(cartActivity.summary.units) }}</strong></div>
          <div class="cart-summary-value"><span>Valor potencial</span><strong>{{ money(cartActivity.summary.value) }}</strong></div>
        </div>

        <div v-if="cartActivity.customers.length" class="cart-filters">
          <v-text-field v-model="cartSearch" label="Procurar cliente" prepend-inner-icon="mdi-magnify" clearable hide-details />
          <v-select v-model="cartCatalog" :items="catalogOptions" label="Catálogo" prepend-inner-icon="mdi-bookshelf" hide-details />
          <v-chip variant="tonal" color="primary">{{ filteredCartCustomers.length }} {{ filteredCartCustomers.length === 1 ? 'cliente' : 'clientes' }}</v-chip>
        </div>

        <v-table v-if="filteredCartCustomers.length" class="cart-table d-none d-md-table">
          <thead><tr><th>Cliente</th><th>Catálogos</th><th>Última alteração</th><th class="text-right">Artigos</th><th class="text-right">Unidades</th><th class="text-right">Valor</th><th><span class="sr-only">Ações</span></th></tr></thead>
          <tbody>
            <tr v-for="customer in filteredCartCustomers" :key="customer.userId" class="clickable" @click="$router.push(`/admin/utilizadores/${customer.userId}`)">
              <td><div class="customer-name">{{ customer.name }}</div><div class="customer-meta">{{ customer.company || customer.username }} <v-chip v-if="!customer.active" size="x-small" color="grey" variant="tonal">Inativo</v-chip></div></td>
              <td><div class="catalog-chips"><v-chip v-for="catalog in customer.catalogs" :key="catalog.catalogSlug" size="small" variant="tonal" :prepend-icon="catalog.catalogIcon"><span>{{ catalog.catalogLabel }}</span><b>{{ money(catalog.total) }}</b></v-chip></div></td>
              <td><span :title="dateTime(customer.updatedAt)">{{ relativeTime(customer.updatedAt) }}</span></td>
              <td class="text-right">{{ number(customer.lines) }}</td>
              <td class="text-right">{{ number(customer.units) }}</td>
              <td class="text-right cart-total">{{ money(customer.total) }}</td>
              <td class="text-right"><v-btn icon="mdi-chevron-right" variant="text" size="small" :aria-label="`Abrir ficha de ${customer.name}`" /></td>
            </tr>
          </tbody>
        </v-table>

        <div v-if="filteredCartCustomers.length" class="cart-mobile-list d-md-none">
          <v-card v-for="customer in filteredCartCustomers" :key="customer.userId" variant="outlined" class="cart-mobile-card" :to="`/admin/utilizadores/${customer.userId}`">
            <div class="d-flex align-start justify-space-between ga-3"><div class="min-width-0"><div class="customer-name">{{ customer.name }}</div><div class="customer-meta text-truncate">{{ customer.company || customer.username }}</div></div><strong class="cart-total">{{ money(customer.total) }}</strong></div>
            <div class="catalog-chips my-3"><v-chip v-for="catalog in customer.catalogs" :key="catalog.catalogSlug" size="small" variant="tonal" :prepend-icon="catalog.catalogIcon">{{ catalog.catalogLabel }}</v-chip></div>
            <div class="mobile-cart-stats"><span><v-icon size="17" aria-hidden="true">mdi-package-variant</v-icon>{{ number(customer.lines) }} artigos</span><span><v-icon size="17" aria-hidden="true">mdi-counter</v-icon>{{ number(customer.units) }} un.</span><span :title="dateTime(customer.updatedAt)"><v-icon size="17" aria-hidden="true">mdi-clock-outline</v-icon>{{ relativeTime(customer.updatedAt) }}</span></div>
          </v-card>
        </div>

        <div v-if="!cartActivity.customers.length" class="empty-cart-state"><v-icon size="42" color="success" aria-hidden="true">mdi-cart-check</v-icon><h3>Sem carrinhos pendentes</h3><p>Não existem clientes com produtos guardados no carrinho.</p></div>
        <div v-else-if="!filteredCartCustomers.length" class="empty-cart-state"><v-icon size="38" color="grey" aria-hidden="true">mdi-magnify-close</v-icon><h3>Nenhum resultado</h3><p>Altere a pesquisa ou o catálogo selecionado.</p></div>
      </v-card>

      <v-row class="mt-2">
        <v-col cols="12" lg="8"><v-card class="soft-card"><v-card-title class="pa-5">Encomendas recentes</v-card-title><v-table><thead><tr><th>Número</th><th>Cliente</th><th>Estado</th><th class="text-right">Total</th></tr></thead><tbody><tr v-for="order in data.recentOrders" :key="order.id" class="clickable" @click="$router.push(`/admin/encomendas/${order.publicNumber}`)"><td class="font-weight-bold">{{ order.publicNumber }}</td><td>{{ order.customerName }}</td><td><v-chip size="small" :color="order.orderStatus === 'pending' ? 'warning' : order.orderStatus === 'confirmed' ? 'success' : 'info'">{{ order.orderStatusLabel }}</v-chip></td><td class="text-right">{{ money(order.total) }}</td></tr></tbody></v-table></v-card></v-col>
        <v-col cols="12" lg="4"><v-card class="soft-card pa-5"><div class="text-h6 font-weight-bold mb-4">Ações rápidas</div><v-btn block to="/admin/utilizadores" variant="tonal" class="mb-3" prepend-icon="mdi-account-plus">Gerir utilizadores</v-btn><v-btn block to="/admin/produtos" variant="tonal" class="mb-3" prepend-icon="mdi-package-variant">Gerir produtos</v-btn><v-btn block to="/admin/avisos" :color="data.metrics.warning_count ? 'warning' : 'success'" variant="tonal" prepend-icon="mdi-alert-outline">{{ data.metrics.warning_count }} avisos</v-btn></v-card></v-col>
      </v-row>
    </template>
  </div>
</template>

<style scoped>
.pending-carts-head { align-items: center; display: flex; gap: 16px; justify-content: space-between; padding: 20px 22px 14px; }
.section-title { align-items: center; display: flex; gap: 14px; min-width: 0; }
.section-icon { align-items: center; background: rgba(var(--v-theme-warning), .12); border-radius: 12px; color: rgb(var(--v-theme-warning)); display: flex; flex: 0 0 44px; height: 44px; justify-content: center; }
.section-title h2 { font-size: 1.2rem; font-weight: 800; line-height: 1.25; margin: 0; }
.section-title p { color: rgba(var(--v-theme-on-surface), .64); font-size: .875rem; margin: 3px 0 0; }
.cart-summary { background: rgba(var(--v-theme-primary), .035); border-block: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: grid; grid-template-columns: repeat(3, minmax(110px, 1fr)) minmax(160px, 1.35fr); padding: 12px 22px; }
.cart-summary > div { display: flex; flex-direction: column; padding: 5px 18px; }
.cart-summary > div + div { border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.cart-summary span { color: rgba(var(--v-theme-on-surface), .62); font-size: .72rem; font-weight: 750; letter-spacing: .04em; text-transform: uppercase; }
.cart-summary strong { font-size: 1.3rem; font-variant-numeric: tabular-nums; }
.cart-summary-value strong { color: rgb(var(--v-theme-primary)); }
.cart-filters { align-items: center; display: grid; gap: 12px; grid-template-columns: minmax(220px, 1.4fr) minmax(190px, 1fr) auto; padding: 16px 22px; }
.cart-table { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.cart-table td { padding-block: 14px !important; }
.customer-name { font-weight: 800; line-height: 1.35; }
.customer-meta { align-items: center; color: rgba(var(--v-theme-on-surface), .62); display: flex; font-size: .78rem; gap: 6px; margin-top: 2px; }
.catalog-chips { display: flex; flex-wrap: wrap; gap: 6px; }
.catalog-chips .v-chip b { border-left: 1px solid rgba(var(--v-theme-on-surface), .16); font-variant-numeric: tabular-nums; margin-left: 7px; padding-left: 7px; }
.cart-total { font-variant-numeric: tabular-nums; font-weight: 800; white-space: nowrap; }
.empty-cart-state { align-items: center; display: flex; flex-direction: column; padding: 40px 20px 44px; text-align: center; }
.empty-cart-state h3 { font-size: 1rem; margin: 10px 0 2px; }
.empty-cart-state p { color: rgba(var(--v-theme-on-surface), .62); margin: 0; }
.cart-mobile-list { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); padding: 14px; }
.cart-mobile-card { display: block; padding: 16px; text-decoration: none; }
.cart-mobile-card + .cart-mobile-card { margin-top: 12px; }
.mobile-cart-stats { color: rgba(var(--v-theme-on-surface), .7); display: flex; flex-wrap: wrap; font-size: .78rem; gap: 10px 16px; }
.mobile-cart-stats span { align-items: center; display: inline-flex; gap: 5px; }
.min-width-0 { min-width: 0; }
.sr-only { clip: rect(0, 0, 0, 0); height: 1px; margin: -1px; overflow: hidden; padding: 0; position: absolute; white-space: nowrap; width: 1px; }
@media (max-width: 760px) {
  .pending-carts-head { align-items: flex-start; padding: 18px 16px 12px; }
  .section-icon { flex-basis: 40px; height: 40px; }
  .section-title p { font-size: .82rem; }
  .cart-summary { grid-template-columns: repeat(2, 1fr); padding: 8px; }
  .cart-summary > div { min-height: 62px; padding: 8px 10px; }
  .cart-summary > div + div { border-left: 0; }
  .cart-summary > div:nth-child(even) { border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
  .cart-summary > div:nth-child(n+3) { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
  .cart-summary strong { font-size: 1.12rem; }
  .cart-filters { grid-template-columns: 1fr; padding: 14px; }
  .cart-filters .v-chip { justify-self: start; }
}
</style>
