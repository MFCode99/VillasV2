<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'
import IconPicker from '../components/IconPicker.vue'

const feedback = useFeedbackStore()
const catalogs = ref([])
const categories = ref([])
const selectedCatalog = ref('villas')
const dialog = ref(false)
const editing = ref(false)
const loading = ref(false)
const form = reactive({ slug: '', catalog_slug: 'villas', parent_slug: null, label: '', icon: 'mdi-shape-outline', sort_order: 0, active: true })

const currentCatalog = computed(() => catalogs.value.find(item => item.slug === selectedCatalog.value))
const topCategories = computed(() => categories.value.filter(item => !item.parentSlug))
const parentOptions = computed(() => topCategories.value.filter(item => item.slug !== form.slug).map(item => ({ title: item.active ? item.label : `${item.label} (desativada)`, value: item.slug })))
function childrenOf(slug) { return categories.value.filter(item => item.parentSlug === slug) }

async function load() {
  loading.value = true
  try {
    const { data } = await api.get('/admin/catalog', { params: { catalog: selectedCatalog.value } })
    catalogs.value = data.catalogs
    categories.value = data.categories
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}
function open(item = null, parent = null) {
  editing.value = Boolean(item)
  Object.assign(form, item ? {
    slug: item.slug,
    catalog_slug: item.catalogSlug,
    parent_slug: item.parentSlug,
    label: item.label,
    icon: item.icon,
    sort_order: item.sortOrder,
    active: item.active,
  } : {
    slug: '',
    catalog_slug: selectedCatalog.value,
    parent_slug: parent?.slug || null,
    label: '',
    icon: 'mdi-shape-outline',
    sort_order: categories.value.length + 1,
    active: true,
  })
  dialog.value = true
}
async function save() {
  try {
    await api.post('/admin/categories', form)
    dialog.value = false
    await load()
    feedback.show(form.parent_slug ? 'Subcategoria guardada.' : 'Categoria guardada.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  }
}
async function toggle(item) {
  try {
    await api.post('/admin/categories', {
      slug: item.slug,
      catalog_slug: item.catalogSlug,
      parent_slug: item.parentSlug,
      label: item.label,
      icon: item.icon,
      sort_order: item.sortOrder,
      active: !item.active,
    })
    await load()
    feedback.show('Categoria atualizada.')
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
  }
}

async function remove(item) {
  const kind = item.parentSlug ? 'subcategoria' : 'categoria'
  const message = item.parentSlug
    ? `Eliminar a subcategoria “${item.label}”? Os produtos associados ficam sem categoria, mas não serão apagados.`
    : `Eliminar a categoria “${item.label}” e todas as suas subcategorias? Os produtos associados ficam sem categoria, mas não serão apagados.`
  if (!await feedback.confirm(message, `Eliminar ${kind}`)) return
  try {
    const { data } = await api.delete(`/admin/categories/${encodeURIComponent(item.slug)}`)
    await load()
    const details = data.unassignedProducts ? ` ${data.unassignedProducts} produto(s) ficaram sem categoria.` : ''
    feedback.show(`${kind[0].toUpperCase()}${kind.slice(1)} eliminada.${details}`)
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}

watch(selectedCatalog, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><h1>Categorias</h1><p>Organize categorias e subcategorias sem misturar os catálogos.</p></div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="open()">Nova categoria</v-btn>
    </div>

    <v-card class="soft-card pa-3 mb-6">
      <v-btn-toggle v-model="selectedCatalog" mandatory color="primary" class="catalog-tabs" aria-label="Escolher catálogo">
        <v-btn v-for="catalog in catalogs" :key="catalog.slug" :value="catalog.slug" :prepend-icon="catalog.icon" min-height="48">{{ catalog.label }}</v-btn>
      </v-btn-toggle>
      <div v-if="currentCatalog" class="text-body-2 text-medium-emphasis px-2 pt-3">{{ currentCatalog.description }}</div>
    </v-card>

    <v-row v-if="loading"><v-col v-for="i in 3" :key="i" cols="12" md="6" lg="4"><v-skeleton-loader type="article, actions" /></v-col></v-row>
    <v-row v-else>
      <v-col v-for="item in topCategories" :key="item.slug" cols="12" lg="6">
        <v-card class="soft-card category-card h-100">
          <div class="pa-5 d-flex justify-space-between align-start ga-4">
            <div class="d-flex align-start ga-3 min-width-0">
              <v-avatar color="primary" variant="tonal" size="44"><v-icon>{{ item.icon || 'mdi-shape-outline' }}</v-icon></v-avatar>
              <div class="min-width-0">
                <div class="d-flex flex-wrap align-center ga-2"><div class="text-h6 font-weight-bold">{{ item.label }}</div><v-chip size="x-small" variant="tonal">Categoria</v-chip></div>
                <div class="text-caption text-medium-emphasis mt-1">{{ item.slug }} · ordem {{ item.sortOrder }}</div>
              </div>
            </div>
            <v-switch :model-value="item.active" :aria-label="`${item.active ? 'Desativar' : 'Ativar'} ${item.label}`" hide-details color="success" @update:model-value="toggle(item)" />
          </div>
          <v-divider />
          <div class="pa-4">
            <div class="d-flex align-center justify-space-between mb-3"><div class="text-subtitle-2 font-weight-bold">Subcategorias</div><v-btn size="small" variant="tonal" prepend-icon="mdi-plus" @click="open(null, item)">Adicionar</v-btn></div>
            <v-list v-if="childrenOf(item.slug).length" lines="two" class="category-children pa-0">
              <v-list-item v-for="child in childrenOf(item.slug)" :key="child.slug" rounded="lg" class="mb-2">
                <template #prepend><v-icon :icon="child.icon || 'mdi-subdirectory-arrow-right'" color="secondary" class="mr-3" /></template>
                <v-list-item-title class="font-weight-bold">{{ child.label }}</v-list-item-title>
                <v-list-item-subtitle>{{ child.slug }} · ordem {{ child.sortOrder }}</v-list-item-subtitle>
                <template #append>
                  <div class="d-flex align-center ga-1">
                    <v-switch :model-value="child.active" :aria-label="`${child.active ? 'Desativar' : 'Ativar'} ${child.label}`" hide-details color="success" density="compact" @update:model-value="toggle(child)" />
                    <v-btn icon="mdi-pencil-outline" variant="text" :aria-label="`Editar ${child.label}`" @click="open(child)" />
                    <v-btn icon="mdi-delete-outline" color="error" variant="text" :aria-label="`Eliminar ${child.label}`" @click="remove(child)" />
                  </div>
                </template>
              </v-list-item>
            </v-list>
            <div v-else class="text-body-2 text-medium-emphasis py-4">Ainda não existem subcategorias.</div>
          </div>
          <v-card-actions class="px-5 pb-5 ga-2"><v-btn class="flex-grow-1" variant="tonal" prepend-icon="mdi-pencil-outline" @click="open(item)">Editar categoria</v-btn><v-btn color="error" variant="tonal" prepend-icon="mdi-delete-outline" @click="remove(item)">Eliminar</v-btn></v-card-actions>
        </v-card>
      </v-col>
    </v-row>

    <div v-if="!loading && !topCategories.length" class="empty-state soft-card rounded-xl"><v-icon size="52">mdi-shape-plus-outline</v-icon><div class="text-h6 mt-3">Sem categorias neste catálogo</div><v-btn color="primary" class="mt-4" prepend-icon="mdi-plus" @click="open()">Criar primeira categoria</v-btn></div>

    <v-dialog v-model="dialog" max-width="600">
      <v-card>
        <v-card-title class="pa-6 pb-2">{{ editing ? 'Editar categoria' : form.parent_slug ? 'Nova subcategoria' : 'Nova categoria' }}</v-card-title>
        <v-card-text class="pa-6">
          <v-select v-model="form.catalog_slug" label="Catálogo" :items="catalogs" item-title="label" item-value="slug" :disabled="editing" />
          <v-select v-model="form.parent_slug" clearable label="Categoria principal" :items="parentOptions" hint="Deixe vazio para criar uma categoria principal." persistent-hint class="mb-3" />
          <v-text-field v-model="form.slug" label="Código" :disabled="editing" hint="Identificador interno, sem necessidade de acentos." persistent-hint />
          <v-text-field v-model="form.label" label="Nome" />
          <IconPicker v-model="form.icon" label="Ícone da categoria" class="mb-4" />
          <v-text-field v-model.number="form.sort_order" type="number" label="Ordem" />
          <v-switch v-model="form.active" color="success" label="Categoria ativa" />
        </v-card-text>
        <v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="dialog = false">Cancelar</v-btn><v-btn color="primary" @click="save">Guardar</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.catalog-tabs { display: flex; flex-wrap: wrap; height: auto; gap: 4px; }
.category-card { display: flex; flex-direction: column; }
.category-children { background: transparent; }
.category-children .v-list-item { background: rgba(var(--v-theme-primary), .035); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); min-height: 64px; }
.min-width-0 { min-width: 0; }
@media (max-width: 600px) { .catalog-tabs, .catalog-tabs :deep(.v-btn) { width: 100%; } }
</style>
