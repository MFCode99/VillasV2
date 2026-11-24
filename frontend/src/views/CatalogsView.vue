<script setup>
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
import IconPicker from '../components/IconPicker.vue'

const router = useRouter()
const feedback = useFeedbackStore()
const auth = useAuthStore()
const catalogs = ref([])
const loading = ref(false)
const saving = ref(false)
const dialog = ref(false)
const editing = ref(null)
const blank = () => ({ label: '', slug: '', description: '', icon: 'mdi-bookshelf', minimum_total: '0.00', sort_order: 20, active: true })
const form = reactive(blank())

async function load() {
  loading.value = true
  try { catalogs.value = (await api.get('/admin/catalogs')).data.catalogs || [] }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
function openCreate() { editing.value = null; Object.assign(form, blank()); dialog.value = true }
function openEdit(catalog) {
  editing.value = catalog.slug
  Object.assign(form, { label: catalog.label, slug: catalog.slug, description: catalog.description, icon: catalog.icon, minimum_total: catalog.minimumTotal, sort_order: catalog.sortOrder, active: catalog.active })
  dialog.value = true
}
function slugFromLabel() {
  if (editing.value || form.slug) return
  form.slug = form.label.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '')
}
async function save() {
  if (!form.label.trim()) return feedback.show('Indique o nome do catálogo.', 'warning')
  saving.value = true
  try {
    if (editing.value) await api.put(`/admin/catalogs/${editing.value}`, form)
    else await api.post('/admin/catalogs', form)
    dialog.value = false
    await load()
    await auth.restore()
    feedback.show(editing.value ? 'Catálogo atualizado.' : 'Catálogo criado. Já pode importar os produtos.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
function importProducts(catalog) { router.push({ path: '/admin/importacao', query: { catalog: catalog.slug } }) }
async function remove(catalog) {
  if (!await feedback.confirm(`Eliminar o catálogo “${catalog.label}”? Só será eliminado se não tiver produtos. As categorias vazias serão removidas.`, 'Eliminar catálogo')) return
  try {
    await api.delete(`/admin/catalogs/${encodeURIComponent(catalog.slug)}`)
    await load()
    await auth.restore()
    feedback.show('Catálogo eliminado.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><h1>Catálogos</h1><p>Crie áreas de produtos independentes e carregue todo o conteúdo por Excel.</p></div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="openCreate">Adicionar novo catálogo</v-btn>
    </div>
    <v-alert type="info" variant="tonal" class="mb-5" icon="mdi-file-excel-outline">
      O modelo Excel inclui produtos, preços, categorias, subcategorias, múltiplos e atalhos de quantidade. As categorias em falta são criadas durante a importação.
      <template #append><v-btn href="/api/v1/admin/import/products/template.xlsx" variant="text" prepend-icon="mdi-download">Modelo Excel</v-btn></template>
    </v-alert>
    <v-progress-linear v-if="loading" indeterminate />
    <v-row v-else>
      <v-col v-for="catalog in catalogs" :key="catalog.slug" cols="12" md="6" xl="4">
        <v-card class="soft-card catalog-card pa-5">
          <div class="d-flex align-start ga-4"><v-avatar color="primary" variant="tonal" size="52"><v-icon size="28">{{ catalog.icon }}</v-icon></v-avatar><div class="flex-grow-1 min-width-0"><div class="d-flex align-center flex-wrap ga-2"><h2 class="text-h6 font-weight-bold">{{ catalog.label }}</h2><v-chip size="x-small" :color="catalog.active ? 'success' : 'grey'" variant="tonal">{{ catalog.active ? 'Ativo' : 'Inativo' }}</v-chip></div><div class="text-caption text-medium-emphasis">{{ catalog.slug }}</div></div><v-btn icon="mdi-pencil-outline" variant="text" aria-label="Editar catálogo" @click="openEdit(catalog)" /></div>
          <p class="text-body-2 text-medium-emphasis my-4 catalog-description">{{ catalog.description || 'Sem descrição.' }}</p>
          <div class="catalog-metrics"><div><strong>{{ catalog.productCount }}</strong><span>produtos</span></div><div><strong>{{ catalog.categoryCount }}</strong><span>categorias</span></div><div><strong>{{ Number(catalog.minimumTotal).toFixed(2) }} €</strong><span>mínimo</span></div></div>
          <div class="d-flex flex-wrap ga-2 mt-5"><v-btn color="primary" variant="tonal" prepend-icon="mdi-database-import-outline" @click="importProducts(catalog)">Importar Excel</v-btn><v-btn :to="`/catalogo/${catalog.slug === 'interpilhas' ? 'utilidades' : catalog.slug}`" variant="text" prepend-icon="mdi-open-in-new">Abrir</v-btn><v-btn v-if="!['villas', 'interpilhas'].includes(catalog.slug)" color="error" variant="text" prepend-icon="mdi-delete-outline" @click="remove(catalog)">Eliminar</v-btn></div>
        </v-card>
      </v-col>
    </v-row>

    <v-dialog v-model="dialog" max-width="680">
      <v-card><v-card-title class="pa-6 pb-2">{{ editing ? 'Editar catálogo' : 'Novo catálogo' }}</v-card-title><v-card-subtitle class="px-6">Cada catálogo mantém produtos, categorias, permissões e carrinho separados.</v-card-subtitle><v-card-text class="pa-6"><v-row density="compact"><v-col cols="12" md="7"><v-text-field v-model="form.label" label="Nome do catálogo" autofocus @blur="slugFromLabel" /></v-col><v-col cols="12" md="5"><v-text-field v-model="form.slug" label="Identificador" :disabled="Boolean(editing)" hint="Sem espaços; usado nos endereços" persistent-hint /></v-col><v-col cols="12"><v-textarea v-model="form.description" label="Descrição" rows="2" /></v-col><v-col cols="12" md="7"><IconPicker v-model="form.icon" label="Ícone do catálogo" /></v-col><v-col cols="12" md="5"><v-text-field v-model="form.minimum_total" type="number" min="0" step="0.01" suffix="€" label="Mínimo da encomenda" /></v-col><v-col cols="12" md="6"><v-text-field v-model.number="form.sort_order" type="number" label="Ordem na navegação" /></v-col><v-col cols="12" md="6"><v-switch v-model="form.active" color="success" label="Catálogo ativo" /></v-col></v-row></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer/><v-btn variant="text" @click="dialog=false">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="save">{{ editing ? 'Guardar' : 'Criar catálogo' }}</v-btn></v-card-actions></v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.catalog-card { height: 100%; }
.catalog-description { min-height: 40px; }
.catalog-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
.catalog-metrics div { background: rgba(var(--v-theme-primary), .055); border-radius: 12px; padding: 12px; }
.catalog-metrics strong, .catalog-metrics span { display: block; }
.catalog-metrics strong { font-size: 1.05rem; }
.catalog-metrics span { color: rgba(var(--v-theme-on-surface), .6); font-size: .72rem; }
.min-width-0 { min-width: 0; }
@media (max-width: 480px) { .catalog-metrics { grid-template-columns: 1fr; } .catalog-description { min-height: 0; } }
</style>
