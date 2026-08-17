<script setup>
import { onMounted, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'
const feedback = useFeedbackStore(); const data = ref(null); const loading = ref(true)
const money = value => new Intl.NumberFormat('pt-PT', { style: 'currency', currency: 'EUR' }).format(Number(value || 0))
onMounted(async () => { try { data.value = (await api.get('/admin/dashboard')).data } catch (e) { feedback.show(errorMessage(e), 'error') } finally { loading.value = false } })
</script>
<template><div class="page">
  <div class="page-head"><div><h1>Visão geral</h1><p>O estado do negócio num só lugar.</p></div><v-btn to="/admin/encomendas/nova" color="primary" prepend-icon="mdi-plus">Nova encomenda</v-btn></div>
  <v-skeleton-loader v-if="loading" type="article, article" />
  <template v-else-if="data">
    <v-row><v-col v-for="m in [
      ['Encomendas pendentes', data.metrics.pending_orders, 'mdi-clock-outline', 'warning'],
      ['Confirmadas', data.metrics.confirmed_orders, 'mdi-check-circle-outline', 'success'],
      ['Clientes', data.metrics.total_clients, 'mdi-account-group-outline', 'info'],
      ['Vendas este mês', money(data.metrics.month_confirmed_revenue), 'mdi-currency-eur', 'secondary']
    ]" :key="m[0]" cols="12" sm="6" lg="3"><v-card class="metric soft-card"><div class="d-flex justify-space-between"><div class="metric-label">{{ m[0] }}</div><v-icon :color="m[3]">{{ m[2] }}</v-icon></div><div class="metric-value">{{ m[1] }}</div></v-card></v-col></v-row>
    <v-row class="mt-2"><v-col cols="12" lg="8"><v-card class="soft-card"><v-card-title class="pa-5">Encomendas recentes</v-card-title><v-table><thead><tr><th>Número</th><th>Cliente</th><th>Estado</th><th class="text-right">Total</th></tr></thead><tbody><tr v-for="order in data.recentOrders" :key="order.id" class="clickable" @click="$router.push(`/admin/encomendas/${order.publicNumber}`)"><td class="font-weight-bold">{{ order.publicNumber }}</td><td>{{ order.customerName }}</td><td><v-chip size="small" :color="order.orderStatus === 'pending' ? 'warning' : order.orderStatus === 'confirmed' ? 'success' : 'info'">{{ order.orderStatusLabel }}</v-chip></td><td class="text-right">{{ money(order.total) }}</td></tr></tbody></v-table></v-card></v-col>
      <v-col cols="12" lg="4"><v-card class="soft-card pa-5"><div class="text-h6 font-weight-bold mb-4">Ações rápidas</div><v-btn block to="/admin/utilizadores" variant="tonal" class="mb-3" prepend-icon="mdi-account-plus">Gerir utilizadores</v-btn><v-btn block to="/admin/produtos" variant="tonal" class="mb-3" prepend-icon="mdi-package-variant">Gerir produtos</v-btn><v-btn block to="/admin/avisos" :color="data.metrics.warning_count ? 'warning' : 'success'" variant="tonal" prepend-icon="mdi-alert-outline">{{ data.metrics.warning_count }} avisos</v-btn></v-card></v-col></v-row>
  </template>
</div></template>
