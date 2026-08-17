<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
const auth = useAuthStore(); const feedback = useFeedbackStore(); const route = useRoute(); const router = useRouter(); const orders = ref([]); const loading = ref(true); const q = ref(''); const status = ref(null)
const filtered = computed(() => orders.value.filter(o => (!q.value || `${o.publicNumber} ${o.customerName} ${o.customerCompany}`.toLowerCase().includes(q.value.toLowerCase())) && (!status.value || o.orderStatus === status.value)))
const money = v => `${Number(v || 0).toFixed(2)} €`; const open = o => router.push(`${auth.isAdmin ? '/admin' : ''}/encomendas/${o.publicNumber}`)
async function load(){loading.value=true;try{orders.value=(await api.get('/orders')).data.orders}catch(e){feedback.show(errorMessage(e),'error')}finally{loading.value=false}}
async function remove(order){if(!await feedback.confirm(`Eliminar definitivamente a encomenda ${order.publicNumber}?`, 'Eliminar encomenda'))return;try{await api.delete(`/admin/orders/${order.publicNumber}`);orders.value=orders.value.filter(item=>item.id!==order.id);feedback.show('Encomenda eliminada.')}catch(e){feedback.show(errorMessage(e),'error')}}
onMounted(load)
</script>
<template><div class="page"><div class="page-head"><div><h1>Encomendas</h1><p>{{ filtered.length }} resultados.</p></div><v-btn v-if="auth.isAdmin" to="/admin/encomendas/nova" color="primary" prepend-icon="mdi-plus">Nova encomenda</v-btn></div>
  <v-card class="soft-card pa-4 mb-5"><v-row dense><v-col cols="12" md="8"><v-text-field v-model="q" hide-details clearable prepend-inner-icon="mdi-magnify" label="Pesquisar encomenda ou cliente" /></v-col><v-col cols="12" md="4"><v-select v-model="status" hide-details clearable label="Estado" :items="[{title:'Pendente',value:'pending'},{title:'Confirmada',value:'confirmed'},{title:'Enviada',value:'shipped'}]" /></v-col></v-row></v-card>
  <v-card class="soft-card table-wrap"><v-progress-linear v-if="loading" indeterminate /><v-table v-else><thead><tr><th>Número</th><th v-if="auth.isAdmin">Cliente</th><th>Data</th><th>Estado</th><th>Unidades</th><th class="text-right">Total</th><th></th></tr></thead><tbody><tr v-for="order in filtered" :key="order.id" class="clickable" @click="open(order)"><td class="font-weight-bold">{{ order.publicNumber }}</td><td v-if="auth.isAdmin"><div>{{ order.customerName }}</div><small class="text-medium-emphasis">{{ order.customerCompany }}</small></td><td>{{ new Date(order.createdAt).toLocaleDateString('pt-PT') }}</td><td><v-chip class="status-chip" size="small" :color="order.orderStatus === 'pending' ? 'warning' : order.orderStatus === 'confirmed' ? 'success' : 'info'">{{ order.orderStatusLabel }}</v-chip></td><td>{{ order.units }}</td><td class="text-right font-weight-bold">{{ money(order.total) }}</td><td class="text-no-wrap"><v-btn v-if="auth.isAdmin" icon="mdi-delete-outline" variant="text" color="error" @click.stop="remove(order)" /><v-icon>mdi-chevron-right</v-icon></td></tr></tbody></v-table><div v-if="!loading && !filtered.length" class="empty-state">Nenhuma encomenda encontrada.</div></v-card>
</div></template>
