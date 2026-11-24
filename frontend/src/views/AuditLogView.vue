<script setup>
import { onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const loading = ref(false)
const data = ref({ items: [], total: 0, page: 1, pages: 1 })
const filters = reactive({ q: '', action: null, entity_type: null, page: 1 })
let timer
const actions = [{ title: 'Todas as ações', value: null }, { title: 'Criar', value: 'post' }, { title: 'Alterar', value: 'put' }, { title: 'Atualizar', value: 'patch' }, { title: 'Eliminar', value: 'delete' }]
const entities = [{ title: 'Todas as áreas', value: null }, { title: 'Produtos', value: 'products' }, { title: 'Importações', value: 'import' }, { title: 'Utilizadores', value: 'users' }, { title: 'Encomendas', value: 'orders' }, { title: 'Categorias', value: 'categories' }]
const actionMeta = { post: ['Criou', 'success', 'mdi-plus-circle-outline'], put: ['Alterou', 'info', 'mdi-pencil-outline'], patch: ['Atualizou', 'warning', 'mdi-refresh'], delete: ['Eliminou', 'error', 'mdi-delete-outline'] }
const areaLabels = { products: 'Produto', import: 'Importação', users: 'Utilizador', orders: 'Encomenda', categories: 'Categoria', clients: 'Clientes', warnings: 'Avisos', 'order-draft': 'Rascunho de encomenda', 'pdf-layout': 'Modelo PDF' }
const dateTime = value => value ? new Date(value).toLocaleString('pt-PT') : '—'

async function load() {
  loading.value = true
  try { data.value = (await api.get('/admin/audit-log', { params: filters })).data }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
function meta(action) { return actionMeta[action] || [action, 'grey', 'mdi-circle-outline'] }
watch(() => [filters.q, filters.action, filters.entity_type], () => { filters.page = 1; clearTimeout(timer); timer = setTimeout(load, 300) })
watch(() => filters.page, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head"><div><h1>Histórico administrativo</h1><p>Alterações realizadas pelos administradores, sem expor dados sensíveis.</p></div><v-chip prepend-icon="mdi-history" color="primary" variant="tonal">{{ data.total }} ações</v-chip></div>
    <v-card class="soft-card pa-4 mb-6"><v-row density="compact"><v-col cols="12" md="6"><v-text-field v-model="filters.q" clearable hide-details label="Pesquisar utilizador, referência ou rota" prepend-inner-icon="mdi-magnify" /></v-col><v-col cols="6" md="3"><v-select v-model="filters.action" hide-details label="Ação" :items="actions" /></v-col><v-col cols="6" md="3"><v-select v-model="filters.entity_type" hide-details label="Área" :items="entities" /></v-col></v-row></v-card>
    <v-progress-linear v-if="loading" indeterminate color="secondary" />
    <v-card v-else class="soft-card overflow-hidden">
      <v-table density="comfortable"><thead><tr><th>Data</th><th>Administrador</th><th>Ação</th><th>Área</th><th>Identificador</th><th>Pedido</th></tr></thead><tbody><tr v-for="item in data.items" :key="item.id"><td class="text-no-wrap">{{ dateTime(item.createdAt) }}</td><td class="font-weight-bold">{{ item.actor }}</td><td><v-chip size="small" variant="tonal" :color="meta(item.action)[1]" :prepend-icon="meta(item.action)[2]">{{ meta(item.action)[0] }}</v-chip></td><td>{{ areaLabels[item.entityType] || item.entityType }}</td><td class="audit-id">{{ item.entityId || '—' }}</td><td><v-tooltip :text="item.requestId || 'Sem identificador'"><template #activator="{ props }"><span v-bind="props" class="request-id">{{ item.requestId?.slice(0, 8) || '—' }}</span></template></v-tooltip></td></tr></tbody></v-table>
      <div v-if="!data.items.length" class="empty-state"><v-icon size="56">mdi-history</v-icon><div class="text-h6 mt-3">Ainda não existem ações registadas</div></div>
    </v-card>
    <v-pagination v-if="data.pages > 1" v-model="filters.page" :length="data.pages" class="mt-6" />
  </div>
</template>

<style scoped>
.audit-id { max-width: 260px; overflow-wrap: anywhere; }
.request-id { cursor: help; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
@media (max-width: 760px) { .audit-id { max-width: 150px; } }
</style>
