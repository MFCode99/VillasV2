<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const router = useRouter()
const feedback = useFeedbackStore()
const now = new Date()
const filters = reactive({ year: now.getFullYear(), month: now.getMonth() + 1, catalog: 'all' })
const scope = ref('month')
const data = ref(null)
const catalogs = ref([])
const loading = ref(false)
const orderQ = ref('')
const orderStatus = ref('all')
const detailsTab = ref('catalogs')
let initialized = false

const money = value => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
const number = value => new Intl.NumberFormat('pt-PT').format(Number(value || 0))
const date = value => value ? new Intl.DateTimeFormat('pt-PT', { day: '2-digit', month: '2-digit', year: 'numeric' }).format(new Date(value)) : '—'
const capitalize = value => value ? value.charAt(0).toUpperCase() + value.slice(1) : ''
const periodLabel = (year, month, style = 'long') => capitalize(new Date(year, Number(month) - 1, 1).toLocaleDateString('pt-PT', { month: style, year: 'numeric' }))
const selectedLabel = computed(() => scope.value === 'year' ? `Ano ${filters.year}` : periodLabel(filters.year, filters.month))
const selectedPeriod = computed({
  get: () => `${filters.year}-${String(filters.month).padStart(2, '0')}`,
  set: value => { const [year, month] = String(value).split('-').map(Number); filters.year = year; filters.month = month },
})
const periodOptions = computed(() => Array.from({ length: 24 }, (_, index) => {
  const value = new Date(now.getFullYear(), now.getMonth() - index, 1)
  return { title: periodLabel(value.getFullYear(), value.getMonth() + 1), value: `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, '0')}` }
}))
const yearOptions = computed(() => Array.from({ length: 8 }, (_, index) => now.getFullYear() - index))
const catalogOptions = computed(() => [{ title: 'Todos os catálogos', value: 'all' }, ...catalogs.value.map(item => ({ title: item.active ? item.label : `${item.label} · Desativado`, value: item.slug }))])
const exportUrl = computed(() => `/admin/estatisticas/export.xlsx?scope=${scope.value}&year=${filters.year}&month=${filters.month}${filters.catalog === 'all' ? '' : `&catalog=${filters.catalog}`}`)
const isCurrentPeriod = computed(() => scope.value === 'year' ? filters.year >= now.getFullYear() : filters.year === now.getFullYear() && filters.month === now.getMonth() + 1)
const visibleSeries = computed(() => (data.value?.series || []).slice(-12))
const seriesMax = computed(() => Math.max(1, ...visibleSeries.value.map(row => Number(row.confirmed_revenue || 0))))
const chartRows = computed(() => scope.value === 'year' ? (data.value?.detail?.months || []) : (data.value?.detail?.daily || []))
const chartMax = computed(() => Math.max(1, ...chartRows.value.map(row => Number(row.revenue || 0))))
const previousMonth = computed(() => {
  const rows = data.value?.series || []
  const index = rows.findIndex(row => Number(row.year) === Number(filters.year) && Number(row.month) === Number(filters.month))
  return index > 0 ? rows[index - 1] : null
})
const revenueDelta = computed(() => {
  if (!data.value) return null
  const current = Number(data.value.detail.confirmed_revenue || 0)
  if (scope.value === 'year') {
    const previous = (data.value?.series || []).filter(row => Number(row.year) === filters.year - 1).reduce((sum, row) => sum + Number(row.confirmed_revenue || 0), 0)
    if (!previous) return current ? 100 : 0
    return ((current - previous) / previous) * 100
  }
  if (!previousMonth.value || !data.value) return null
  const previous = Number(previousMonth.value.confirmed_revenue || 0)
  if (!previous) return current ? 100 : 0
  return ((current - previous) / previous) * 100
})
const filteredOrders = computed(() => (data.value?.detail?.orders || []).filter(order => {
  const matchesStatus = orderStatus.value === 'all' || order.orderStatus === orderStatus.value
  const haystack = `${order.publicNumber} ${order.customerName} ${order.customerCompany} ${order.customerNif} ${order.catalogLabel}`.toLowerCase()
  return matchesStatus && (!orderQ.value || haystack.includes(orderQ.value.toLowerCase()))
}))

function statusColor(status) { return { pending: 'warning', confirmed: 'success', shipped: 'info' }[status] || 'grey' }
function shiftPeriod(amount) {
  if (scope.value === 'year') { filters.year += amount; return }
  const value = new Date(filters.year, filters.month - 1 + amount, 1)
  filters.year = value.getFullYear(); filters.month = value.getMonth() + 1
}
function selectMonth(row) { scope.value = 'month'; filters.year = Number(row.year); filters.month = Number(row.month) }
function selectAnnualMonth(row) { scope.value = 'month'; filters.month = Number(row.month) }
function resetPeriod() { filters.year = now.getFullYear(); filters.month = now.getMonth() + 1 }
async function load() {
  loading.value = true
  try {
    const params = { scope: scope.value, year: filters.year, month: filters.month }
    if (filters.catalog !== 'all') params.catalog = filters.catalog
    data.value = (await api.get('/admin/statistics', { params })).data
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
watch(() => [scope.value, filters.year, filters.month, filters.catalog], () => { if (initialized) load() })
onMounted(async () => {
  try { catalogs.value = (await api.get('/admin/catalogs')).data.catalogs || [] }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  initialized = true
  await load()
})
</script>

<template>
  <div class="page billing-page">
    <div class="page-head billing-head">
      <div><div class="text-overline text-secondary font-weight-bold">Gestão comercial</div><h1>Faturação</h1><p>Valores das encomendas confirmadas e enviadas, organizados pela data em que foram criadas.</p></div>
      <v-btn :href="exportUrl" color="success" prepend-icon="mdi-microsoft-excel">Exportar {{ scope === 'year' ? 'ano' : 'mês' }}</v-btn>
    </div>

    <v-card class="soft-card period-toolbar pa-3 mb-6">
      <v-btn-toggle v-model="scope" mandatory color="primary" variant="tonal" divided class="scope-toggle" aria-label="Período da faturação"><v-btn value="month">Mensal</v-btn><v-btn value="year">Anual</v-btn></v-btn-toggle>
      <v-divider vertical class="mx-1 d-none d-md-block" />
      <v-btn icon="mdi-chevron-left" variant="text" size="large" :aria-label="scope === 'year' ? 'Ano anterior' : 'Mês anterior'" @click="shiftPeriod(-1)" />
      <v-select v-if="scope === 'month'" v-model="selectedPeriod" :items="periodOptions" label="Mês de faturação" hide-details prepend-inner-icon="mdi-calendar-month-outline" class="period-select" />
      <v-select v-else v-model="filters.year" :items="yearOptions" label="Ano de faturação" hide-details prepend-inner-icon="mdi-calendar-range" class="period-select" />
      <v-btn icon="mdi-chevron-right" variant="text" size="large" :aria-label="scope === 'year' ? 'Ano seguinte' : 'Mês seguinte'" :disabled="isCurrentPeriod" @click="shiftPeriod(1)" />
      <v-divider vertical class="mx-2 d-none d-md-block" />
      <v-select v-model="filters.catalog" :items="catalogOptions" label="Catálogo" hide-details prepend-inner-icon="mdi-bookshelf" class="catalog-select" />
      <v-btn variant="tonal" prepend-icon="mdi-calendar-today" :disabled="isCurrentPeriod" @click="resetPeriod">Atual</v-btn>
    </v-card>

    <v-progress-linear v-if="loading" indeterminate color="secondary" class="mb-4" />
    <v-skeleton-loader v-if="loading && !data" type="article, article, table" />
    <template v-else-if="data">
      <div class="section-heading"><div><h2>{{ selectedLabel }}</h2><p>Resumo financeiro do período selecionado</p></div><v-chip variant="tonal" color="primary">{{ filters.catalog === 'all' ? 'Todos os catálogos' : catalogs.find(item => item.slug === filters.catalog)?.label }}</v-chip></div>

      <div class="billing-metrics">
        <v-card class="billing-metric primary-metric soft-card"><div class="metric-icon"><v-icon>mdi-currency-eur</v-icon></div><div><span>Faturação confirmada</span><strong>{{ money(data.detail.confirmed_revenue) }}</strong><small v-if="revenueDelta !== null" :class="revenueDelta >= 0 ? 'text-success' : 'text-error'"><v-icon size="15">{{ revenueDelta >= 0 ? 'mdi-trending-up' : 'mdi-trending-down' }}</v-icon> {{ Math.abs(revenueDelta).toFixed(1) }}% face ao {{ scope === 'year' ? 'ano' : 'mês' }} anterior</small><small v-else>Sem comparação disponível</small></div></v-card>
        <v-card class="billing-metric soft-card"><div class="metric-icon warning"><v-icon>mdi-clock-outline</v-icon></div><div><span>Valor pendente</span><strong>{{ money(data.detail.pending_value) }}</strong><small>{{ number(data.report.pending_orders) }} encomendas por confirmar</small></div></v-card>
        <v-card class="billing-metric soft-card"><div class="metric-icon success"><v-icon>mdi-receipt-text-check-outline</v-icon></div><div><span>Encomendas confirmadas</span><strong>{{ number(data.detail.confirmed_orders) }}</strong><small>de {{ number(data.detail.orders_total) }} criadas no {{ scope === 'year' ? 'ano' : 'mês' }}</small></div></v-card>
        <v-card class="billing-metric soft-card"><div class="metric-icon"><v-icon>mdi-chart-box-outline</v-icon></div><div><span>Valor médio</span><strong>{{ money(data.detail.average_order_value) }}</strong><small>por encomenda confirmada</small></div></v-card>
      </div>
      <v-card class="summary-strip soft-card mt-3"><div><v-icon>mdi-package-variant-closed</v-icon><span>Unidades</span><b>{{ number(data.detail.confirmed_units) }}</b></div><v-divider vertical /><div><v-icon>mdi-account-multiple-outline</v-icon><span>Clientes com compras</span><b>{{ number(data.detail.unique_customers) }}</b></div><v-divider vertical /><div><v-icon>mdi-text-box-check-outline</v-icon><span>Encomendas criadas</span><b>{{ number(data.detail.orders_total) }}</b></div></v-card>

      <v-row class="mt-3">
        <v-col cols="12" lg="8"><v-card class="soft-card pa-5 h-100"><div class="section-heading compact"><div><h2>Faturação {{ scope === 'year' ? 'mensal' : 'diária' }}</h2><p>{{ selectedLabel }} · valores confirmados</p></div><div class="chart-legend"><span class="legend-dot" /> Valor confirmado</div></div><div class="chart-scroll"><div class="daily-chart" :class="{ annual: scope === 'year' }" role="img" :aria-label="`Faturação de ${selectedLabel}`"><button v-for="row in chartRows" :key="scope === 'year' ? row.month : row.day" type="button" class="day-column" :class="{ interactive: scope === 'year' }" :title="`${scope === 'year' ? periodLabel(filters.year, row.month, 'short') : `Dia ${row.day}`}: ${money(row.revenue)}`" @click="scope === 'year' && selectAnnualMonth(row)"><div class="day-value">{{ Number(row.revenue) ? money(row.revenue) : '' }}</div><div class="day-track"><div class="day-bar" :style="{ height: `${Number(row.revenue) ? Math.max(6, Number(row.revenue) / chartMax * 100) : 0}%` }" /></div><span>{{ scope === 'year' ? periodLabel(filters.year, row.month, 'short').replace(` de ${filters.year}`, '') : row.day }}</span></button></div></div></v-card></v-col>
        <v-col cols="12" lg="4"><v-card class="soft-card pa-5 h-100"><div class="section-heading compact"><div><h2>Estados</h2><p>Quantidade e valor no período</p></div></div><div v-for="item in data.detail.status_breakdown" :key="item.status" class="status-detail"><div class="d-flex align-center justify-space-between ga-3"><div class="d-flex align-center ga-2"><v-icon :color="statusColor(item.status)">mdi-circle-medium</v-icon><b>{{ item.label }}</b></div><b>{{ number(item.orders) }}</b></div><div class="d-flex justify-space-between text-body-2 text-medium-emphasis mt-1"><span>{{ item.orders === 1 ? 'encomenda' : 'encomendas' }}</span><span>{{ money(item.value) }}</span></div></div></v-card></v-col>
      </v-row>

      <v-expansion-panels v-if="scope === 'month'" class="mt-6"><v-expansion-panel class="soft-card"><v-expansion-panel-title><div><b>Histórico dos últimos 12 meses</b><div class="text-caption text-medium-emphasis">Comparar e abrir outro mês</div></div></v-expansion-panel-title><v-expansion-panel-text><div class="month-grid"><button v-for="row in visibleSeries" :key="`${row.year}-${row.month}`" type="button" class="month-column" :class="{ selected: row.year === filters.year && row.month === filters.month }" :aria-label="`${periodLabel(row.year, row.month)}: ${money(row.confirmed_revenue)}`" @click="selectMonth(row)"><span class="month-amount">{{ money(row.confirmed_revenue) }}</span><div class="month-track"><div class="month-bar" :style="{ height: `${Number(row.confirmed_revenue) ? Math.max(5, Number(row.confirmed_revenue) / seriesMax * 100) : 0}%` }" /></div><b>{{ periodLabel(row.year, row.month, 'short').replace(` de ${row.year}`, '') }}</b><small>{{ row.confirmed_orders }} enc.</small></button></div></v-expansion-panel-text></v-expansion-panel></v-expansion-panels>

      <v-card class="soft-card mt-6 overflow-hidden">
        <div class="orders-head pa-5"><div><h2 class="text-h6 font-weight-bold">Encomendas · {{ selectedLabel }}</h2><p class="text-body-2 text-medium-emphasis mb-0">Origem dos valores apresentados no resumo.</p></div><div class="orders-filters"><v-text-field v-model="orderQ" label="Procurar" hide-details clearable prepend-inner-icon="mdi-magnify" /><v-select v-model="orderStatus" label="Estado" hide-details :items="[{title:'Todos',value:'all'},{title:'Pendentes',value:'pending'},{title:'Confirmadas',value:'confirmed'},{title:'Enviadas',value:'shipped'}]" /></div></div>
        <v-table class="orders-table d-none d-md-table"><thead><tr><th>Data</th><th>Encomenda</th><th>Cliente</th><th>Catálogo</th><th>Estado</th><th class="text-right">Unidades</th><th class="text-right">Total</th><th></th></tr></thead><tbody><tr v-for="order in filteredOrders" :key="order.id" class="clickable" @click="router.push(`/admin/encomendas/${order.publicNumber}`)"><td>{{ date(order.createdAt) }}</td><td class="font-weight-bold">{{ order.publicNumber }}</td><td><b>{{ order.customerName }}</b><div class="text-caption text-medium-emphasis">{{ order.customerCompany || order.customerNif || '—' }}</div></td><td>{{ order.catalogLabel }}</td><td><v-chip size="small" variant="tonal" :color="statusColor(order.orderStatus)">{{ order.orderStatusLabel }}</v-chip></td><td class="text-right">{{ number(order.units) }}</td><td class="text-right font-weight-bold">{{ money(order.total) }}</td><td><v-icon>mdi-chevron-right</v-icon></td></tr></tbody></v-table>
        <div class="d-md-none pa-3"><v-card v-for="order in filteredOrders" :key="order.id" variant="outlined" class="order-mobile-card mb-3" @click="router.push(`/admin/encomendas/${order.publicNumber}`)"><div class="d-flex justify-space-between ga-3"><div><b>{{ order.publicNumber }}</b><div class="text-caption">{{ date(order.createdAt) }} · {{ order.catalogLabel }}</div></div><v-chip size="small" variant="tonal" :color="statusColor(order.orderStatus)">{{ order.orderStatusLabel }}</v-chip></div><div class="my-3"><b>{{ order.customerName }}</b><div class="text-caption text-medium-emphasis">{{ order.customerCompany || 'Sem empresa' }}</div></div><div class="d-flex justify-space-between"><span>{{ number(order.units) }} unidades</span><strong>{{ money(order.total) }}</strong></div></v-card></div><div v-if="!filteredOrders.length" class="empty-state">Nenhuma encomenda corresponde aos filtros.</div>
      </v-card>

      <v-card class="soft-card mt-6 overflow-hidden"><v-tabs v-model="detailsTab" color="primary" show-arrows><v-tab value="catalogs">Catálogos</v-tab><v-tab value="products">Produtos mais vendidos</v-tab><v-tab value="customers">Principais clientes</v-tab></v-tabs><v-divider /><v-window v-model="detailsTab"><v-window-item value="catalogs"><v-list><v-list-item v-for="item in data.detail.catalog_breakdown" :key="item.slug" :subtitle="`${number(item.orders)} encomendas · ${number(item.units)} unidades`"><template #title><div class="d-flex align-center ga-2"><span>{{ item.label }}</span><v-chip v-if="!item.active" size="x-small" color="grey" variant="tonal">Desativado</v-chip></div></template><template #append><b>{{ money(item.revenue) }}</b></template></v-list-item></v-list></v-window-item><v-window-item value="products"><v-list><v-list-item v-for="product in data.insights.top_products" :key="product.ref" :title="product.name" :subtitle="`${product.ref} · ${number(product.units)} unidades`"><template #append><b>{{ money(product.revenue) }}</b></template></v-list-item></v-list><div v-if="!data.insights.top_products.length" class="empty-state">Sem produtos faturados.</div></v-window-item><v-window-item value="customers"><v-list><v-list-item v-for="customer in data.insights.top_customers" :key="customer.id" :title="customer.name" :subtitle="`${customer.company || 'Sem empresa'} · ${number(customer.orders)} encomendas`"><template #append><b>{{ money(customer.revenue) }}</b></template></v-list-item></v-list><div v-if="!data.insights.top_customers.length" class="empty-state">Sem clientes faturados.</div></v-window-item></v-window></v-card>
    </template>
  </div>
</template>

<style scoped>
.billing-head p { max-width: 760px; }
.period-toolbar { align-items: center; display: flex; gap: 8px; }
.scope-toggle { flex: 0 0 auto; }
.period-select { flex: 0 1 260px; }
.catalog-select { flex: 1 1 260px; }
.section-heading { align-items: center; display: flex; gap: 16px; justify-content: space-between; margin-bottom: 18px; }
.section-heading h2 { font-size: 1.25rem; font-weight: 800; margin: 0; }
.section-heading p { color: rgba(var(--v-theme-on-surface), .62); font-size: .875rem; margin: 2px 0 0; }
.section-heading.compact { margin-bottom: 24px; }
.billing-metrics { display: grid; gap: 14px; grid-template-columns: repeat(4, minmax(0, 1fr)); }
.billing-metric { align-items: flex-start; display: flex; gap: 14px; min-height: 128px; padding: 20px; }
.billing-metric span, .billing-metric strong, .billing-metric small { display: block; }
.billing-metric span { color: rgba(var(--v-theme-on-surface), .62); font-size: .76rem; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }
.billing-metric strong { font-size: clamp(1.35rem, 2vw, 2rem); font-variant-numeric: tabular-nums; line-height: 1.25; margin: 6px 0; }
.billing-metric small { color: rgba(var(--v-theme-on-surface), .68); }
.metric-icon { align-items: center; background: rgba(var(--v-theme-primary), .09); border-radius: 12px; color: rgb(var(--v-theme-primary)); display: flex; flex: 0 0 44px; height: 44px; justify-content: center; }
.metric-icon.warning { background: rgba(var(--v-theme-warning), .12); color: rgb(var(--v-theme-warning)); }
.metric-icon.success { background: rgba(var(--v-theme-success), .12); color: rgb(var(--v-theme-success)); }
.primary-metric { border-color: rgba(var(--v-theme-primary), .32); }
.summary-strip { align-items: stretch; display: flex; min-height: 68px; padding: 10px 18px; }
.summary-strip > div { align-items: center; display: grid; flex: 1 1 0; gap: 2px 10px; grid-template-columns: auto 1fr auto; padding: 6px 18px; }
.summary-strip .v-icon { color: rgb(var(--v-theme-primary)); grid-row: 1 / span 2; }
.summary-strip span { color: rgba(var(--v-theme-on-surface), .62); font-size: .76rem; font-weight: 700; text-transform: uppercase; }
.summary-strip b { font-size: 1.05rem; font-variant-numeric: tabular-nums; grid-column: 3; grid-row: 1 / span 2; }
.chart-scroll { overflow-x: auto; }
.daily-chart { align-items: end; display: grid; gap: 3px; grid-template-columns: repeat(31, minmax(16px, 1fr)); min-height: 260px; min-width: 620px; }
.daily-chart.annual { gap: 8px; grid-template-columns: repeat(12, minmax(48px, 1fr)); min-width: 620px; }
.day-column { align-items: center; background: transparent; border: 0; color: inherit; display: grid; font: inherit; grid-template-rows: 34px 180px 22px; min-width: 0; padding: 0; text-align: center; }
.day-column.interactive { border-radius: 8px; cursor: pointer; }
.day-column.interactive:hover, .day-column.interactive:focus-visible { background: rgba(var(--v-theme-primary), .06); outline: 2px solid rgba(var(--v-theme-primary), .35); outline-offset: 1px; }
.day-track { align-items: end; display: flex; height: 180px; }
.day-bar { background: rgb(var(--v-theme-primary)); border-radius: 5px 5px 2px 2px; width: 100%; }
.day-column > span { color: rgba(var(--v-theme-on-surface), .58); font-size: .68rem; font-variant-numeric: tabular-nums; }
.day-value { font-size: .6rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; writing-mode: vertical-rl; }
.chart-legend { color: rgba(var(--v-theme-on-surface), .68); font-size: .78rem; white-space: nowrap; }
.legend-dot { background: rgb(var(--v-theme-primary)); border-radius: 50%; display: inline-block; height: 9px; margin-right: 6px; width: 9px; }
.status-detail { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 12px; padding: 14px; }
.status-detail + .status-detail { margin-top: 12px; }
.month-grid { display: grid; gap: 8px; grid-template-columns: repeat(12, minmax(60px, 1fr)); }
.month-column { background: transparent; border: 1px solid transparent; border-radius: 12px; color: inherit; cursor: pointer; display: grid; grid-template-rows: 28px 116px auto auto; min-height: 190px; padding: 8px; text-align: center; transition: background-color .18s ease, border-color .18s ease; }
.month-column:hover, .month-column:focus-visible { background: rgba(var(--v-theme-primary), .05); border-color: rgba(var(--v-theme-primary), .25); outline: none; }
.month-column.selected { background: rgba(var(--v-theme-primary), .08); border-color: rgb(var(--v-theme-primary)); }
.month-track { align-items: end; display: flex; height: 116px; }
.month-bar { background: rgb(var(--v-theme-secondary)); border-radius: 6px 6px 2px 2px; width: 100%; }
.month-amount { font-size: .66rem; font-variant-numeric: tabular-nums; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.month-column b { font-size: .72rem; text-transform: capitalize; }
.month-column small { color: rgba(var(--v-theme-on-surface), .58); }
.orders-head { align-items: center; display: flex; gap: 20px; justify-content: space-between; }
.orders-filters { display: grid; flex: 0 1 520px; gap: 10px; grid-template-columns: 1.4fr 1fr; }
.orders-table td, .orders-table th { white-space: nowrap; }
.order-mobile-card { cursor: pointer; padding: 16px; }
@media (max-width: 1200px) { .billing-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); } .period-toolbar { flex-wrap: wrap; } .month-grid { grid-template-columns: repeat(6, 1fr); } }
@media (max-width: 700px) {
  .period-toolbar { align-items: stretch; flex-wrap: wrap; }
  .scope-toggle { display: grid; flex: 1 1 100%; grid-template-columns: 1fr 1fr; width: 100%; }
  .scope-toggle .v-btn { width: 100%; }
  .period-select { flex: 1 1 calc(100% - 112px); }
  .catalog-select { flex: 1 1 100%; }
  .period-toolbar > .v-btn:last-child { flex: 1 1 100%; min-height: 48px; }
  .billing-metrics { grid-template-columns: 1fr; }
  .billing-metric { min-height: 112px; }
  .summary-strip { align-items: stretch; flex-direction: column; padding: 6px 12px; }
  .summary-strip > div { min-height: 54px; padding: 8px; }
  .summary-strip > .v-divider { display: none; }
  .section-heading { align-items: flex-start; flex-direction: column; }
  .month-grid { grid-template-columns: repeat(3, 1fr); }
  .month-column { grid-template-rows: 24px 76px auto auto; min-height: 150px; }
  .month-track { height: 76px; }
  .orders-head { align-items: stretch; flex-direction: column; }
  .orders-filters { flex: auto; grid-template-columns: 1fr; width: 100%; }
  .daily-chart { min-height: 210px; }
  .day-column { grid-template-rows: 20px 150px 20px; }
  .day-track { height: 150px; }
  .day-value { display: none; }
}
@media (prefers-reduced-motion: reduce) { .month-column { transition: none; } }
</style>
