<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  activity: { type: Object, default: () => ({ summary: {}, customers: [] }) },
  loading: { type: Boolean, default: false },
})
defineEmits(['refresh'])

const search = ref('')
const catalog = ref('all')
const money = value => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
const number = value => new Intl.NumberFormat('pt-PT').format(Number(value || 0))
const dateTime = value => value ? new Intl.DateTimeFormat('pt-PT', { dateStyle: 'short', timeStyle: 'short' }).format(new Date(value)) : '—'
const customers = computed(() => props.activity?.customers || [])
const summary = computed(() => props.activity?.summary || {})
const catalogOptions = computed(() => {
  const values = new Map()
  for (const customer of customers.value) for (const item of customer.catalogs || []) values.set(item.catalogSlug, item.catalogLabel)
  return [{ title: 'Todos os catálogos', value: 'all' }, ...Array.from(values, ([value, title]) => ({ title, value }))]
})
const filteredCustomers = computed(() => {
  const query = search.value.trim().toLocaleLowerCase('pt-PT')
  return customers.value.filter(customer => {
    const matchesCatalog = catalog.value === 'all' || customer.catalogs.some(item => item.catalogSlug === catalog.value)
    const text = `${customer.name} ${customer.username} ${customer.company || ''}`.toLocaleLowerCase('pt-PT')
    return matchesCatalog && (!query || text.includes(query))
  })
})

function relativeTime(value) {
  if (!value) return 'Sem data'
  const minutes = Math.floor(Math.max(0, Date.now() - new Date(value).getTime()) / 60000)
  if (minutes < 1) return 'Agora'
  if (minutes < 60) return `Há ${minutes} min`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `Há ${hours} h`
  const days = Math.floor(hours / 24)
  return days < 30 ? `Há ${days} ${days === 1 ? 'dia' : 'dias'}` : dateTime(value)
}
</script>

<template>
  <v-card class="soft-card pending-card mt-6 overflow-hidden">
    <div class="pending-head">
      <div class="pending-title"><div class="pending-icon"><v-icon aria-hidden="true">mdi-cart-outline</v-icon></div><div><h2>Carrinhos pendentes</h2><p>Clientes que adicionaram produtos e ainda não concluíram a encomenda.</p></div></div>
      <v-btn icon="mdi-refresh" variant="text" :loading="loading" aria-label="Atualizar carrinhos pendentes" @click="$emit('refresh')" />
    </div>

    <div class="pending-summary" aria-live="polite">
      <div><span>Clientes</span><strong>{{ number(summary.customers) }}</strong></div>
      <div><span>Carrinhos</span><strong>{{ number(summary.carts) }}</strong></div>
      <div><span>Unidades</span><strong>{{ number(summary.units) }}</strong></div>
      <div class="value"><span>Valor potencial</span><strong>{{ money(summary.value) }}</strong></div>
    </div>

    <div v-if="customers.length" class="pending-filters">
      <v-text-field v-model="search" label="Procurar cliente" prepend-inner-icon="mdi-magnify" clearable hide-details />
      <v-select v-model="catalog" :items="catalogOptions" label="Catálogo" prepend-inner-icon="mdi-bookshelf" hide-details />
      <v-chip color="primary" variant="tonal">{{ filteredCustomers.length }} {{ filteredCustomers.length === 1 ? 'cliente' : 'clientes' }}</v-chip>
    </div>

    <v-table v-if="filteredCustomers.length" class="pending-table d-none d-md-table">
      <thead><tr><th>Cliente</th><th>Catálogos</th><th>Última alteração</th><th class="text-right">Artigos</th><th class="text-right">Unidades</th><th class="text-right">Valor</th><th><span class="sr-only">Ações</span></th></tr></thead>
      <tbody><tr v-for="customer in filteredCustomers" :key="customer.userId" class="clickable" @click="$router.push(`/admin/utilizadores/${customer.userId}`)">
        <td><b>{{ customer.name }}</b><div class="customer-meta">{{ customer.company || customer.username }}<v-chip v-if="!customer.active" size="x-small" color="grey" variant="tonal">Inativo</v-chip></div></td>
        <td><div class="catalogs"><v-chip v-for="item in customer.catalogs" :key="item.catalogSlug" size="small" variant="tonal" :prepend-icon="item.catalogIcon"><span>{{ item.catalogLabel }}</span><b>{{ money(item.total) }}</b></v-chip></div></td>
        <td><span :title="dateTime(customer.updatedAt)">{{ relativeTime(customer.updatedAt) }}</span></td>
        <td class="text-right">{{ number(customer.lines) }}</td><td class="text-right">{{ number(customer.units) }}</td><td class="text-right total">{{ money(customer.total) }}</td>
        <td><v-icon aria-hidden="true">mdi-chevron-right</v-icon></td>
      </tr></tbody>
    </v-table>

    <div v-if="filteredCustomers.length" class="mobile-list d-md-none"><v-card v-for="customer in filteredCustomers" :key="customer.userId" :to="`/admin/utilizadores/${customer.userId}`" variant="outlined" class="mobile-card">
      <div class="d-flex align-start justify-space-between ga-3"><div class="min-width-0"><b>{{ customer.name }}</b><div class="customer-meta text-truncate">{{ customer.company || customer.username }}</div></div><strong class="total">{{ money(customer.total) }}</strong></div>
      <div class="catalogs my-3"><v-chip v-for="item in customer.catalogs" :key="item.catalogSlug" size="small" variant="tonal" :prepend-icon="item.catalogIcon">{{ item.catalogLabel }}</v-chip></div>
      <div class="mobile-stats"><span><v-icon size="17" aria-hidden="true">mdi-package-variant</v-icon>{{ number(customer.lines) }} artigos</span><span><v-icon size="17" aria-hidden="true">mdi-counter</v-icon>{{ number(customer.units) }} un.</span><span :title="dateTime(customer.updatedAt)"><v-icon size="17" aria-hidden="true">mdi-clock-outline</v-icon>{{ relativeTime(customer.updatedAt) }}</span></div>
    </v-card></div>

    <div v-if="!customers.length" class="empty-state"><v-icon size="42" color="success" aria-hidden="true">mdi-cart-check</v-icon><h3>Sem carrinhos pendentes</h3><p>Não existem clientes com produtos guardados no carrinho.</p></div>
    <div v-else-if="!filteredCustomers.length" class="empty-state"><v-icon size="38" color="grey" aria-hidden="true">mdi-magnify-close</v-icon><h3>Nenhum resultado</h3><p>Altere a pesquisa ou o catálogo selecionado.</p></div>
  </v-card>
</template>

<style scoped>
.pending-head { align-items: center; display: flex; gap: 16px; justify-content: space-between; padding: 20px 22px 14px; }
.pending-title { align-items: center; display: flex; gap: 14px; min-width: 0; }
.pending-icon { align-items: center; background: rgba(var(--v-theme-warning), .12); border-radius: 12px; color: rgb(var(--v-theme-warning)); display: flex; flex: 0 0 44px; height: 44px; justify-content: center; }
.pending-title h2 { font-size: 1.2rem; font-weight: 800; line-height: 1.25; margin: 0; }
.pending-title p { color: rgba(var(--v-theme-on-surface), .64); font-size: .875rem; margin: 3px 0 0; }
.pending-summary { background: rgba(var(--v-theme-primary), .035); border-block: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: grid; grid-template-columns: repeat(3, minmax(110px, 1fr)) minmax(160px, 1.35fr); padding: 12px 22px; }
.pending-summary > div { display: flex; flex-direction: column; padding: 5px 18px; }
.pending-summary > div + div { border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.pending-summary span { color: rgba(var(--v-theme-on-surface), .62); font-size: .72rem; font-weight: 750; letter-spacing: .04em; text-transform: uppercase; }
.pending-summary strong { font-size: 1.3rem; font-variant-numeric: tabular-nums; }
.pending-summary .value strong { color: rgb(var(--v-theme-primary)); }
.pending-filters { align-items: center; display: grid; gap: 12px; grid-template-columns: minmax(220px, 1.4fr) minmax(190px, 1fr) auto; padding: 16px 22px; }
.pending-table { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.pending-table td { padding-block: 14px !important; }
.customer-meta { align-items: center; color: rgba(var(--v-theme-on-surface), .62); display: flex; font-size: .78rem; gap: 6px; margin-top: 2px; }
.catalogs { display: flex; flex-wrap: wrap; gap: 6px; }
.catalogs .v-chip b { border-left: 1px solid rgba(var(--v-theme-on-surface), .16); font-variant-numeric: tabular-nums; margin-left: 7px; padding-left: 7px; }
.total { font-variant-numeric: tabular-nums; font-weight: 800; white-space: nowrap; }
.mobile-list { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); padding: 14px; }
.mobile-card { display: block; padding: 16px; text-decoration: none; }
.mobile-card + .mobile-card { margin-top: 12px; }
.mobile-stats { color: rgba(var(--v-theme-on-surface), .7); display: flex; flex-wrap: wrap; font-size: .78rem; gap: 10px 16px; }
.mobile-stats span { align-items: center; display: inline-flex; gap: 5px; }
.empty-state { align-items: center; display: flex; flex-direction: column; padding: 40px 20px 44px; text-align: center; }
.empty-state h3 { font-size: 1rem; margin: 10px 0 2px; }.empty-state p { color: rgba(var(--v-theme-on-surface), .62); margin: 0; }
.min-width-0 { min-width: 0; }.sr-only { clip: rect(0, 0, 0, 0); height: 1px; margin: -1px; overflow: hidden; padding: 0; position: absolute; white-space: nowrap; width: 1px; }
@media (max-width: 760px) {
  .pending-head { align-items: flex-start; padding: 18px 16px 12px; }.pending-icon { flex-basis: 40px; height: 40px; }.pending-title p { font-size: .82rem; }
  .pending-summary { grid-template-columns: repeat(2, 1fr); padding: 8px; }.pending-summary > div { min-height: 62px; padding: 8px 10px; }.pending-summary > div + div { border-left: 0; }.pending-summary > div:nth-child(even) { border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }.pending-summary > div:nth-child(n+3) { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }.pending-summary strong { font-size: 1.12rem; }
  .pending-filters { grid-template-columns: 1fr; padding: 14px; }.pending-filters .v-chip { justify-self: start; }
}
</style>
