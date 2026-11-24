<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const campaigns = ref([]), products = ref([]), groups = ref([]), clients = ref([])
const loading = ref(true), saving = ref(false), dialog = ref(false), editingId = ref(null)
const section = ref('campaigns')
const productSearch = ref(''), currentImageUrl = ref(''), selectedImageUrl = ref('')
const form = reactive({ title: '', description: '', show_text: true, convert_to_png: false, active: false, starts_at: '', ends_at: '', sort_order: 0, product_refs: [], group_ids: [], discount_type: 'none', discount_value: '0', promotional_prices: {}, image: null, remove_image: false })
const groupDialog = ref(false), savingGroup = ref(false), editingGroupId = ref(null)
const groupForm = reactive({ name: '', description: '', active: true, user_ids: [] })

const selectedProducts = computed(() => form.product_refs.map(ref => products.value.find(product => product.ref === ref)).filter(Boolean))
const selectedProductRefs = computed(() => new Set(form.product_refs))
const matchingProducts = computed(() => {
  const query = productSearch.value.trim().toLowerCase()
  return products.value.filter(product => !query || `${product.ref} ${product.name} ${product.catalogLabel} ${product.categoryLabel}`.toLowerCase().includes(query))
})
const filteredProducts = computed(() => matchingProducts.value.slice(0, 120))
const groupOptions = computed(() => groups.value.filter(group => group.active).map(group => ({ title: `${group.name} (${group.memberCount})`, value: group.id })))
const clientOptions = computed(() => clients.value.map(client => ({ title: `${client.fullName}${client.companyName ? ` · ${client.companyName}` : ''}`, value: client.id })))
const selectedClientCount = computed(() => clients.value.filter(client => groupForm.user_ids.includes(client.id)).length)
const allClientsSelected = computed(() => clients.value.length > 0 && selectedClientCount.value === clients.value.length)
const previewImageUrl = computed(() => selectedImageUrl.value || (!form.remove_image ? currentImageUrl.value : ''))
const productPrice = product => `${Number(product.price || 0).toFixed(product.catalogSlug === 'interpilhas' ? 3 : 2)} €`

function localDate(value) { if (!value) return ''; const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16) }
function resetForm() { Object.assign(form, { title: '', description: '', show_text: true, convert_to_png: false, active: false, starts_at: '', ends_at: '', sort_order: 0, product_refs: [], group_ids: [], discount_type: 'none', discount_value: '0', promotional_prices: {}, image: null, remove_image: false }); editingId.value = null; currentImageUrl.value = ''; productSearch.value = '' }
function createCampaign() { resetForm(); dialog.value = true }
function editCampaign(campaign) {
  editingId.value = campaign.id
  Object.assign(form, { title: campaign.title, description: campaign.description, show_text: campaign.showText !== false, convert_to_png: false, active: campaign.active, starts_at: localDate(campaign.startsAt), ends_at: localDate(campaign.endsAt), sort_order: campaign.sortOrder, product_refs: [...campaign.productRefs], group_ids: [...(campaign.groupIds || [])], discount_type: campaign.discountType || 'none', discount_value: campaign.discountValue || '0', promotional_prices: { ...(campaign.promotionalPrices || {}) }, image: null, remove_image: false })
  currentImageUrl.value = campaign.imageUrl || ''; productSearch.value = ''; dialog.value = true
}
function toggleProduct(ref) { if (form.product_refs.includes(ref)) { form.product_refs = form.product_refs.filter(value => value !== ref); const prices = { ...form.promotional_prices }; delete prices[ref]; form.promotional_prices = prices } else form.product_refs = [...form.product_refs, ref] }
function selectedImageFile() { return Array.isArray(form.image) ? form.image[0] : form.image }

async function load() {
  loading.value = true
  try {
    const [campaignResult, catalogResult, groupResult, userResult] = await Promise.all([api.get('/admin/campaigns'), api.get('/admin/catalog'), api.get('/admin/customer-groups'), api.get('/admin/users', { params: { role: 'client', active: true } })])
    campaigns.value = campaignResult.data.campaigns || []
    products.value = (catalogResult.data.products || []).filter(product => product.active && product.manualActive)
    groups.value = groupResult.data.groups || []
    clients.value = userResult.data.users || []
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
async function save() {
  saving.value = true
  try {
    const payload = { title: form.title, description: form.description, show_text: previewImageUrl.value ? form.show_text : true, active: form.active, starts_at: form.starts_at || null, ends_at: form.ends_at || null, sort_order: form.sort_order, product_refs: form.product_refs, group_ids: form.group_ids, discount_type: form.discount_type, discount_value: form.discount_value || '0', promotional_prices: form.promotional_prices }
    const { data } = editingId.value ? await api.put(`/admin/campaigns/${editingId.value}`, payload) : await api.post('/admin/campaigns', payload)
    const image = selectedImageFile()
    if (image) { const upload = new FormData(); upload.append('image', image); upload.append('convert_to_png', form.convert_to_png ? 'true' : 'false'); await api.post(`/admin/campaigns/${data.campaign.id}/image`, upload) }
    else if (form.remove_image && currentImageUrl.value) await api.delete(`/admin/campaigns/${data.campaign.id}/image`)
    dialog.value = false; await load(); feedback.show(editingId.value ? 'Campanha atualizada.' : 'Campanha criada.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function remove(campaign) { if (!await feedback.confirm(`Eliminar a campanha “${campaign.title}”?`, 'Eliminar campanha')) return; try { await api.delete(`/admin/campaigns/${campaign.id}`); await load(); feedback.show('Campanha eliminada.') } catch (error) { feedback.show(errorMessage(error), 'error') } }
async function toggle(campaign, active) {
  const previous = campaign.active; campaign.active = active
  try { await api.put(`/admin/campaigns/${campaign.id}`, { title: campaign.title, description: campaign.description, show_text: campaign.showText !== false, active, starts_at: campaign.startsAt, ends_at: campaign.endsAt, sort_order: campaign.sortOrder, product_refs: campaign.productRefs, group_ids: campaign.groupIds || [], discount_type: campaign.discountType || 'none', discount_value: campaign.discountValue || '0', promotional_prices: campaign.promotionalPrices || {} }); await load(); feedback.show(active ? 'Campanha ativada.' : 'Campanha desativada.') }
  catch (error) { campaign.active = previous; feedback.show(errorMessage(error), 'error') }
}
function openGroup(group = null) { editingGroupId.value = group?.id || null; Object.assign(groupForm, group ? { name: group.name, description: group.description, active: group.active, user_ids: [...group.userIds] } : { name: '', description: '', active: true, user_ids: [] }); groupDialog.value = true }
function addAllClients() { groupForm.user_ids = clients.value.map(client => client.id) }
async function saveGroup() { savingGroup.value = true; try { if (editingGroupId.value) await api.put(`/admin/customer-groups/${editingGroupId.value}`, groupForm); else await api.post('/admin/customer-groups', groupForm); groupDialog.value = false; await load(); feedback.show(editingGroupId.value ? 'Grupo atualizado.' : 'Grupo criado.') } catch (error) { feedback.show(errorMessage(error), 'error') } finally { savingGroup.value = false } }
async function removeGroup(group) { if (!await feedback.confirm(`Eliminar o grupo “${group.name}”? As campanhas deixam de usar este grupo, mas nenhum cliente é eliminado.`, 'Eliminar grupo')) return; try { await api.delete(`/admin/customer-groups/${group.id}`); await load(); feedback.show('Grupo eliminado.') } catch (error) { feedback.show(errorMessage(error), 'error') } }
const period = campaign => campaign.startsAt || campaign.endsAt ? `${campaign.startsAt ? new Date(campaign.startsAt).toLocaleString('pt-PT') : 'Agora'} — ${campaign.endsAt ? new Date(campaign.endsAt).toLocaleString('pt-PT') : 'Sem fim'}` : 'Sem limite de datas'
watch(() => form.image, () => {
  if (selectedImageUrl.value) URL.revokeObjectURL(selectedImageUrl.value)
  const image = selectedImageFile()
  selectedImageUrl.value = image instanceof File ? URL.createObjectURL(image) : ''
  if (selectedImageUrl.value) form.remove_image = false
  else form.convert_to_png = false
})
onBeforeUnmount(() => { if (selectedImageUrl.value) URL.revokeObjectURL(selectedImageUrl.value) })
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><h1>Campanhas</h1><p>Defina os produtos, o período e os clientes de cada campanha.</p></div>
      <v-btn color="primary" prepend-icon="mdi-plus" @click="createCampaign">Nova campanha</v-btn>
    </div>
    <v-progress-linear v-if="loading" indeterminate color="secondary" />

    <v-card v-if="!loading" class="soft-card campaign-manager">
      <v-tabs v-model="section" color="primary" class="campaign-tabs">
        <v-tab value="campaigns" prepend-icon="mdi-bullhorn-outline">Campanhas <span class="tab-count">{{ campaigns.length }}</span></v-tab>
        <v-tab value="groups" prepend-icon="mdi-account-multiple-outline">Grupos de clientes <span class="tab-count">{{ groups.length }}</span></v-tab>
      </v-tabs>
      <v-divider />

      <v-window v-model="section">
        <v-window-item value="campaigns">
          <div v-if="campaigns.length" class="campaign-list">
            <article v-for="campaign in campaigns" :key="campaign.id" class="campaign-row">
              <div class="campaign-media">
                <v-img v-if="campaign.imageUrl" :src="campaign.imageUrl" :alt="`Imagem da campanha ${campaign.title}`" cover />
                <v-icon v-else size="28" color="grey-lighten-1" aria-hidden="true">mdi-image-outline</v-icon>
              </div>
              <div class="campaign-main">
                <div class="campaign-title-line">
                  <h2>{{ campaign.title }}</h2>
                  <v-chip size="small" :color="campaign.currentlyActive ? 'success' : campaign.active ? 'warning' : 'grey'" variant="tonal">{{ campaign.currentlyActive ? 'Em destaque' : campaign.active ? 'Agendada' : 'Inativa' }}</v-chip>
                  <v-chip v-if="campaign.discountType !== 'none'" size="small" color="error" variant="tonal">{{ campaign.discountType === 'percentage' ? `-${Number(campaign.discountValue)}%` : `-${Number(campaign.discountValue).toFixed(2)} €` }}</v-chip>
                </div>
                <p v-if="campaign.description" class="campaign-description">{{ campaign.description }}</p>
                <div class="campaign-meta">
                  <span><v-icon size="16" aria-hidden="true">mdi-calendar-range</v-icon>{{ period(campaign) }}</span>
                  <span><v-icon size="16" aria-hidden="true">mdi-package-variant-closed</v-icon>{{ campaign.products.length }} produtos</span>
                  <span><v-icon size="16" aria-hidden="true">mdi-account-multiple-outline</v-icon>{{ campaign.groups.length ? campaign.groups.map(group => group.name).join(', ') : 'Todos os clientes' }}</span>
                </div>
                <div v-if="campaign.products.length" class="campaign-refs"><span v-for="product in campaign.products.slice(0, 6)" :key="product.ref">{{ product.ref }}</span><span v-if="campaign.products.length > 6">+{{ campaign.products.length - 6 }}</span></div>
              </div>
              <div class="campaign-actions">
                <v-switch :model-value="campaign.active" color="success" hide-details :aria-label="`${campaign.active ? 'Desativar' : 'Ativar'} ${campaign.title}`" @update:model-value="toggle(campaign, $event)" />
                <v-btn icon="mdi-pencil-outline" variant="text" :aria-label="`Editar ${campaign.title}`" @click="editCampaign(campaign)" />
                <v-btn icon="mdi-delete-outline" color="error" variant="text" :aria-label="`Eliminar ${campaign.title}`" @click="remove(campaign)" />
              </div>
            </article>
          </div>
          <div v-else class="manager-empty"><v-icon size="44">mdi-bullhorn-outline</v-icon><div><b>Ainda não existem campanhas</b><span>Crie a primeira campanha e escolha os produtos a apresentar.</span></div><v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="createCampaign">Criar campanha</v-btn></div>
        </v-window-item>

        <v-window-item value="groups">
          <div class="group-toolbar"><div><b>Grupos de clientes</b><span>Use grupos para limitar campanhas a conjuntos específicos de clientes.</span></div><v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openGroup()">Novo grupo</v-btn></div>
          <div v-if="groups.length" class="group-list">
            <div v-for="group in groups" :key="group.id" class="group-row">
              <v-avatar color="primary" variant="tonal" size="44"><v-icon>mdi-account-multiple-outline</v-icon></v-avatar>
              <div class="group-copy"><div><b>{{ group.name }}</b><v-chip size="x-small" :color="group.active ? 'success' : 'grey'" variant="tonal">{{ group.active ? 'Ativo' : 'Inativo' }}</v-chip></div><span>{{ group.description || 'Sem descrição' }}</span></div>
              <div class="group-members"><b>{{ group.memberCount }}</b><span>clientes</span></div>
              <div class="group-actions"><v-btn icon="mdi-pencil-outline" variant="text" :aria-label="`Editar ${group.name}`" @click="openGroup(group)" /><v-btn icon="mdi-delete-outline" color="error" variant="text" :aria-label="`Eliminar ${group.name}`" @click="removeGroup(group)" /></div>
            </div>
          </div>
          <div v-else class="manager-empty"><v-icon size="44">mdi-account-multiple-outline</v-icon><div><b>Ainda não existem grupos</b><span>Sem grupos selecionados, as campanhas aparecem para todos os clientes.</span></div><v-btn color="primary" variant="tonal" prepend-icon="mdi-plus" @click="openGroup()">Criar grupo</v-btn></div>
        </v-window-item>
      </v-window>
    </v-card>

    <v-dialog v-model="dialog" max-width="980" :fullscreen="$vuetify.display.smAndDown">
      <v-card><v-card-title class="pa-6 pb-2">{{ editingId ? 'Editar campanha' : 'Nova campanha' }}</v-card-title><v-card-text class="pa-6"><v-row><v-col cols="12" md="8"><v-text-field v-model="form.title" label="Nome da campanha" maxlength="160" counter /></v-col><v-col cols="12" md="4"><v-text-field v-model.number="form.sort_order" type="number" label="Ordem" /></v-col><v-col cols="12"><v-textarea v-model="form.description" label="Texto de apresentação (opcional)" rows="2" maxlength="3000" counter /></v-col><v-col cols="12"><v-file-input v-model="form.image" accept="image/*" label="Imagem de destaque" prepend-icon="mdi-image-outline" hint="A imagem é ajustada automaticamente sem ser cortada; JPG, PNG ou WebP até 8 MB." persistent-hint /></v-col><v-col cols="12" md="6"><v-switch v-model="form.convert_to_png" color="primary" label="Converter imagem para PNG" hint="Converte o novo ficheiro ao guardar a campanha." persistent-hint :disabled="!selectedImageUrl" /></v-col><v-col cols="12" md="6"><v-switch v-model="form.show_text" color="primary" label="Mostrar texto no banner" hint="Desative para apresentar apenas a imagem." persistent-hint :disabled="!previewImageUrl" /></v-col><v-col cols="12"><div class="campaign-preview-label"><span>Pré-visualização</span><small>Adapta-se automaticamente ao formato da imagem</small></div><div class="campaign-preview" :class="{ 'image-only': !form.show_text && previewImageUrl }"><img v-if="previewImageUrl" :src="previewImageUrl" alt="Pré-visualização da imagem da campanha" class="campaign-preview-image" /><div v-if="form.show_text || !previewImageUrl" class="campaign-preview-copy"><span>Campanha</span><h3>{{ form.title || 'Nome da campanha' }}</h3><p v-if="form.description">{{ form.description }}</p></div></div><div v-if="currentImageUrl && !form.remove_image" class="d-flex justify-end mt-2"><v-btn size="small" color="error" variant="text" prepend-icon="mdi-delete-outline" @click="form.remove_image = true; form.image = null">Remover imagem atual</v-btn></div><v-alert v-else-if="form.remove_image" type="warning" variant="tonal" density="compact" class="mt-2">A imagem atual será removida ao guardar; o texto continuará visível.</v-alert></v-col><v-col cols="12" md="6"><v-text-field v-model="form.starts_at" type="datetime-local" label="Início (opcional)" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.ends_at" type="datetime-local" label="Fim (opcional)" /></v-col><v-col cols="12"><v-select v-model="form.group_ids" :items="groupOptions" multiple chips closable-chips clearable label="Grupos que podem ver a campanha" prepend-inner-icon="mdi-account-multiple-outline" hint="Sem grupos selecionados: visível para todos os clientes." persistent-hint /></v-col><v-col cols="12" md="7"><v-select v-model="form.discount_type" :items="[{title:'Sem desconto geral',value:'none'},{title:'Desconto percentual',value:'percentage'},{title:'Redução fixa em euros',value:'fixed_amount'}]" label="Regra geral de desconto" prepend-inner-icon="mdi-sale-outline" /></v-col><v-col cols="12" md="5"><v-text-field v-if="form.discount_type !== 'none'" v-model="form.discount_value" type="number" min="0" :max="form.discount_type === 'percentage' ? 100 : undefined" step="0.01" :suffix="form.discount_type === 'percentage' ? '%' : '€'" label="Valor do desconto" /></v-col>
      <v-col cols="12"><div class="product-picker"><div class="product-picker-head"><div class="product-search"><v-text-field v-model="productSearch" hide-details clearable label="Pesquisar produtos por referência, nome ou categoria" prepend-inner-icon="mdi-magnify" /><small>A mostrar {{ filteredProducts.length }} de {{ matchingProducts.length }} produtos</small></div><div class="selected-count"><b>{{ form.product_refs.length }}</b><span>selecionados</span></div></div><div class="product-options"><button v-for="product in filteredProducts" :key="product.ref" type="button" class="product-option" :class="{ selected: selectedProductRefs.has(product.ref) }" :aria-pressed="selectedProductRefs.has(product.ref)" @click="toggleProduct(product.ref)"><div class="product-option-image"><v-img v-if="product.imageUrl" :src="product.imageUrl" :alt="product.name" contain /><v-icon v-else size="28" color="grey-lighten-1" aria-hidden="true">mdi-image-outline</v-icon></div><div class="product-option-copy"><div class="product-option-top"><span class="product-ref">{{ product.ref }}</span><span class="product-price">{{ productPrice(product) }}</span></div><b>{{ product.name }}</b><small>{{ product.catalogSlug === 'interpilhas' ? 'Utilidades' : product.catalogLabel }} · {{ product.categoryLabel || 'Sem categoria' }}</small></div><v-icon class="product-option-check" :color="selectedProductRefs.has(product.ref) ? 'primary' : 'grey-lighten-1'" aria-hidden="true">{{ selectedProductRefs.has(product.ref) ? 'mdi-check-circle' : 'mdi-plus-circle-outline' }}</v-icon></button><div v-if="!filteredProducts.length" class="product-empty"><v-icon size="40" color="grey-lighten-1">mdi-package-variant-closed-remove</v-icon><b>Nenhum produto encontrado</b><span>Experimente outra referência, nome ou categoria.</span></div></div><div v-if="matchingProducts.length > filteredProducts.length" class="product-picker-foot">Use a pesquisa para encontrar os restantes {{ matchingProducts.length - filteredProducts.length }} produtos.</div></div></v-col>
      <v-col v-if="selectedProducts.length" cols="12"><div class="promo-price-grid"><div v-for="product in selectedProducts" :key="product.ref" class="promo-price-item"><div><b>{{ product.ref }}</b><small>{{ product.name }}</small></div><v-text-field v-model="form.promotional_prices[product.ref]" type="number" min="0" step="0.01" density="compact" hide-details clearable suffix="€" label="Preço especial" /><v-btn icon="mdi-close" size="small" variant="text" :aria-label="`Remover ${product.ref}`" @click="toggleProduct(product.ref)" /></div></div><div class="text-caption text-medium-emphasis mt-2">O preço especial é opcional e substitui a regra geral apenas neste produto.</div></v-col><v-col cols="12"><v-switch v-model="form.active" color="success" label="Campanha ativa" hint="Aparece na página inicial dentro do período definido." persistent-hint /></v-col></v-row></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer/><v-btn variant="text" @click="dialog=false">Cancelar</v-btn><v-btn color="primary" :disabled="!form.title.trim() || !form.product_refs.length" :loading="saving" @click="save">Guardar campanha</v-btn></v-card-actions></v-card>
    </v-dialog>

    <v-dialog v-model="groupDialog" max-width="720"><v-card><v-card-title class="pa-6 pb-2">{{ editingGroupId ? 'Editar grupo' : 'Novo grupo de clientes' }}</v-card-title><v-card-text class="pa-6"><v-text-field v-model="groupForm.name" label="Nome do grupo" /><v-textarea v-model="groupForm.description" label="Descrição (opcional)" rows="2" /><v-autocomplete v-model="groupForm.user_ids" :items="clientOptions" multiple chips closable-chips clearable label="Clientes do grupo" prepend-inner-icon="mdi-account-search-outline" /><div class="group-member-actions"><v-btn variant="tonal" prepend-icon="mdi-account-multiple-plus-outline" :disabled="!clients.length || allClientsSelected" @click="addAllClients">Adicionar todos</v-btn><span>{{ selectedClientCount }} de {{ clients.length }} clientes selecionados</span></div><v-switch v-model="groupForm.active" color="success" label="Grupo ativo" /></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer/><v-btn variant="text" @click="groupDialog=false">Cancelar</v-btn><v-btn color="primary" :disabled="!groupForm.name.trim()" :loading="savingGroup" @click="saveGroup">Guardar grupo</v-btn></v-card-actions></v-card></v-dialog>
  </div>
</template>

<style scoped>
.campaign-manager { overflow: hidden; }
.campaign-tabs { padding: 8px 12px 0; }
.campaign-tabs :deep(.v-tab) { min-height: 52px; text-transform: none; }
.tab-count { background: rgba(var(--v-theme-primary), .08); border-radius: 999px; font-size: .72rem; margin-left: 8px; min-width: 24px; padding: 2px 7px; }
.campaign-list { display: flex; flex-direction: column; }
.campaign-row { align-items: center; display: grid; gap: 18px; grid-template-columns: 136px minmax(0, 1fr) auto; min-height: 126px; padding: 18px 20px; }
.campaign-row + .campaign-row { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.campaign-media { align-items: center; background: rgba(var(--v-theme-primary), .035); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 10px; display: flex; height: 84px; justify-content: center; overflow: hidden; width: 136px; }
.campaign-media .v-img { height: 100%; width: 100%; }
.campaign-main { flex: 1; min-width: 0; }
.campaign-title-line { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; }
.campaign-title-line h2 { font-size: 1rem; line-height: 1.35; margin: 0; }
.campaign-description { color: rgba(var(--v-theme-on-surface), .68); font-size: .875rem; margin: 5px 0 8px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.campaign-meta { color: rgba(var(--v-theme-on-surface), .62); display: flex; flex-wrap: wrap; font-size: .78rem; gap: 6px 18px; }
.campaign-meta span { align-items: center; display: inline-flex; gap: 5px; }
.campaign-refs { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.campaign-refs span { background: rgba(var(--v-theme-primary), .055); border-radius: 5px; color: rgba(var(--v-theme-on-surface), .7); font-size: .68rem; font-weight: 700; padding: 3px 7px; }
.campaign-actions { align-items: center; display: flex; flex: 0 0 auto; gap: 8px; }
.manager-empty { align-items: center; color: rgba(var(--v-theme-on-surface), .62); display: flex; gap: 18px; min-height: 180px; padding: 32px; }
.manager-empty > div { display: flex; flex: 1; flex-direction: column; }
.manager-empty b { color: rgb(var(--v-theme-on-surface)); font-size: 1rem; }
.manager-empty span { font-size: .875rem; margin-top: 3px; }
.group-toolbar { align-items: center; display: flex; gap: 20px; justify-content: space-between; padding: 18px 20px; }
.group-toolbar > div { display: flex; flex-direction: column; }
.group-toolbar span { color: rgba(var(--v-theme-on-surface), .62); font-size: .82rem; margin-top: 2px; }
.group-list { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: flex; flex-direction: column; }
.group-row { align-items: center; display: grid; gap: 16px; grid-template-columns: auto minmax(0, 1fr) 74px auto; min-height: 84px; padding: 14px 20px; }
.group-row + .group-row { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); }
.group-copy { display: flex; flex-direction: column; min-width: 0; }
.group-copy > div { align-items: center; display: flex; flex-wrap: wrap; gap: 8px; }
.group-copy > span { color: rgba(var(--v-theme-on-surface), .62); font-size: .82rem; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-members { display: flex; flex-direction: column; text-align: right; }
.group-members b { font-variant-numeric: tabular-nums; }
.group-members span { color: rgba(var(--v-theme-on-surface), .58); font-size: .72rem; }
.group-actions { display: flex; gap: 2px; }
.campaign-preview-label { align-items: baseline; display: flex; gap: 10px; justify-content: space-between; margin-bottom: 8px; }
.campaign-preview-label span { font-size: .875rem; font-weight: 700; }
.campaign-preview-label small { color: rgba(var(--v-theme-on-surface), .62); }
.campaign-preview { align-items: center; aspect-ratio: 3 / 1; background: rgb(var(--v-theme-primary)); border-radius: 10px; color: white; display: flex; min-height: 0; overflow: hidden; padding: clamp(18px, 4vw, 48px); position: relative; width: 100%; }
.campaign-preview::after { background: linear-gradient(90deg, rgba(7, 22, 45, .9), rgba(7, 22, 45, .28)); content: ''; inset: 0; position: absolute; }
.campaign-preview-image { height: 100%; inset: 0; object-fit: contain; position: absolute; width: 100%; }
.campaign-preview-copy { max-width: 70%; position: relative; text-shadow: 0 2px 18px rgba(0, 0, 0, .42); z-index: 1; }
.campaign-preview-copy span { font-size: .72rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
.campaign-preview-copy h3 { font-size: clamp(1.7rem, 4vw, 2.8rem); line-height: 1.05; margin-top: 4px; }
.campaign-preview-copy p { margin: 8px 0 0; white-space: pre-line; }
.campaign-preview.image-only::after { background: transparent; }
.group-member-actions { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; margin: -6px 0 12px; }
.group-member-actions span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; }
.product-picker { background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 12px; overflow: hidden; }
.product-picker-head { align-items: center; background: rgb(var(--v-theme-surface)); display: flex; gap: 16px; padding: 16px; }
.product-search { flex: 1; min-width: 0; }
.product-search small { color: rgba(var(--v-theme-on-surface), .58); display: block; margin: 6px 4px 0; }
.selected-count { border-left: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: flex; flex-direction: column; min-width: 92px; padding-left: 16px; text-align: right; }
.selected-count b { color: rgb(var(--v-theme-primary)); font-size: 1.1rem; }
.selected-count span { color: rgba(var(--v-theme-on-surface), .58); font-size: .72rem; }
.product-options { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); max-height: 430px; overflow-y: auto; padding: 12px; }
.product-option { align-items: center; background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 9px; color: inherit; cursor: pointer; display: grid; gap: 12px; grid-template-columns: 62px minmax(0, 1fr) 28px; min-height: 86px; padding: 10px; text-align: left; transition: border-color .16s ease, background-color .16s ease; width: 100%; }
.product-option:hover { background: rgba(var(--v-theme-primary), .025); border-color: rgba(var(--v-theme-primary), .45); }
.product-option:focus-visible { outline: 3px solid rgba(var(--v-theme-primary), .28); outline-offset: 2px; }
.product-option.selected { background: rgba(var(--v-theme-primary), .055); border-color: rgb(var(--v-theme-primary)); }
.product-option-image { align-items: center; background: rgba(var(--v-theme-primary), .035); border-radius: 7px; display: flex; height: 62px; justify-content: center; overflow: hidden; width: 62px; }
.product-option-image .v-img { height: 100%; width: 100%; }
.product-option-copy { display: flex; flex-direction: column; min-width: 0; }
.product-option-copy b, .product-option-copy small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.product-option-copy b { font-size: .9rem; margin-top: 3px; }
.product-option-copy small { color: rgba(var(--v-theme-on-surface), .62); margin-top: 3px; }
.product-option-top { align-items: center; display: flex; gap: 8px; justify-content: space-between; }
.product-ref { color: rgb(var(--v-theme-primary)); font-size: .73rem; font-weight: 800; letter-spacing: .035em; }
.product-price { color: rgba(var(--v-theme-on-surface), .72); font-size: .78rem; font-variant-numeric: tabular-nums; font-weight: 700; }
.product-option-check { justify-self: center; }
.product-empty { align-items: center; color: rgba(var(--v-theme-on-surface), .62); display: flex; flex-direction: column; gap: 4px; grid-column: 1 / -1; padding: 34px 16px; text-align: center; }
.product-empty b { color: rgb(var(--v-theme-on-surface)); margin-top: 6px; }
.product-picker-foot { background: rgb(var(--v-theme-surface)); border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; padding: 10px 16px; text-align: center; }
.promo-price-grid { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }
.promo-price-item { align-items: center; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 9px; display: grid; gap: 10px; grid-template-columns: minmax(0, 1fr) 160px 36px; padding: 10px 12px; }
.promo-price-item > div:first-child { display: flex; flex-direction: column; min-width: 0; }
.promo-price-item small { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
@media (max-width: 800px) { .campaign-row { align-items: start; grid-template-columns: 104px minmax(0, 1fr); } .campaign-media { height: 72px; width: 104px; } .campaign-actions { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); grid-column: 1 / -1; justify-content: flex-end; padding-top: 10px; width: 100%; } .campaign-meta { flex-direction: column; gap: 4px; } .campaign-description { white-space: normal; } .group-row { grid-template-columns: auto minmax(0, 1fr) auto; } .group-members { display: none; } .product-picker-head { align-items: stretch; flex-direction: column; } .selected-count { border-left: 0; border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); flex-direction: row; gap: 6px; justify-content: flex-end; padding: 10px 0 0; } .product-options { grid-template-columns: 1fr; } .campaign-preview-copy { max-width: 88%; } .campaign-preview-copy h3 { font-size: clamp(1.15rem, 5vw, 1.7rem); } .campaign-preview-copy p { display: none; } }
@media (max-width: 480px) { .product-options { gap: 8px; padding: 8px; } .product-option { gap: 9px; grid-template-columns: 54px minmax(0, 1fr) 24px; min-height: 76px; padding: 9px; } .product-option-image { height: 54px; width: 54px; } }
@media (max-width: 800px) { .promo-price-grid { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .campaign-tabs { padding-inline: 4px; } .campaign-tabs :deep(.v-tab) { flex: 1; font-size: .78rem; padding-inline: 8px; } .campaign-row { gap: 12px; padding: 14px; } .campaign-media { grid-column: 1 / -1; height: 130px; width: 100%; } .campaign-main { grid-column: 1 / -1; } .campaign-refs { display: none; } .group-toolbar { align-items: stretch; flex-direction: column; padding: 16px; } .group-row { gap: 10px; padding: 12px 14px; } .group-actions { grid-column: 2 / -1; justify-content: flex-end; } .manager-empty { align-items: flex-start; flex-direction: column; padding: 28px 20px; } }
</style>
