<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const data = ref({ connected: false, tokenConfigured: false, zoneName: 'vitorgouveia.com', records: [], email: null })
const loading = ref(false)
const saving = ref(false)
const token = ref('')
const showTokenForm = ref(false)
const recordDialog = ref(false)
const destinationDialog = ref(false)
const ruleDialog = ref(false)
const editingRecordId = ref(null)
const editingRuleId = ref(null)
const recordSearch = ref('')
const destinationEmail = ref('')
const recordForm = reactive(emptyRecord())
const ruleForm = reactive(emptyRule())

function emptyRecord() { return { type: 'A', name: '', content: '', ttl: 1, proxied: true, priority: 10 } }
function emptyRule() { return { source: '', destination: '', enabled: true } }
const filteredRecords = computed(() => {
  const value = recordSearch.value.trim().toLowerCase()
  return value ? data.value.records.filter(item => `${item.type} ${item.name} ${item.content}`.toLowerCase().includes(value)) : data.value.records
})
const verifiedDestinations = computed(() => (data.value.email?.destinations || []).filter(item => item.verified).map(item => ({ title: item.email, value: item.email })))

async function load() {
  loading.value = true
  try { data.value = (await api.get('/admin/cloudflare')).data }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
async function connect() {
  if (!token.value.trim()) return feedback.show('Cole o API Token do Cloudflare.', 'warning')
  saving.value = true
  try {
    await api.put('/admin/cloudflare/connection', { token: token.value.trim() })
    token.value = ''; showTokenForm.value = false
    await load(); feedback.show('Cloudflare ligado ao portal com sucesso.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
function newRecord() { editingRecordId.value = null; Object.assign(recordForm, emptyRecord(), { name: data.value.zoneName }); recordDialog.value = true }
function editRecord(item) { editingRecordId.value = item.id; Object.assign(recordForm, { type: item.type, name: item.name, content: item.content, ttl: item.ttl || 1, proxied: item.proxied, priority: item.priority ?? 10 }); recordDialog.value = true }
async function saveRecord() {
  if (!recordForm.name.trim() || !recordForm.content.trim()) return feedback.show('Indique o nome e o conteúdo do registo.', 'warning')
  const action = editingRecordId.value ? 'alterar' : 'criar'
  if (!await feedback.confirm(`Confirmar ${action} o registo ${recordForm.type} de ${recordForm.name}? Uma alteração DNS pode afetar o domínio.`, 'Confirmar alteração DNS')) return
  saving.value = true
  try {
    if (editingRecordId.value) await api.put(`/admin/cloudflare/dns-records/${editingRecordId.value}`, recordForm)
    else await api.post('/admin/cloudflare/dns-records', recordForm)
    recordDialog.value = false; await load(); feedback.show('Registo DNS guardado.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function deleteRecord(item) {
  if (!await feedback.confirm(`Eliminar o registo ${item.type} “${item.name}”? Esta alteração pode interromper o domínio ou o email.`, 'Eliminar registo DNS')) return
  try { await api.delete(`/admin/cloudflare/dns-records/${item.id}`); await load(); feedback.show('Registo DNS eliminado.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}
async function addDestination() {
  if (!destinationEmail.value.trim()) return feedback.show('Indique o novo email de destino.', 'warning')
  if (!await feedback.confirm(`Enviar a verificação do Cloudflare para ${destinationEmail.value.trim()}? O endereço só poderá receber encaminhamentos depois de confirmado.`, 'Adicionar email de destino')) return
  saving.value = true
  try { await api.post('/admin/cloudflare/email/destinations', { email: destinationEmail.value.trim() }); destinationDialog.value = false; destinationEmail.value = ''; await load(); feedback.show('Email adicionado. Confirme a mensagem enviada pelo Cloudflare.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function addPortalDestination() {
  if (!await feedback.confirm(`Usar o email já configurado no portal (${data.value.portalEmailMasked}) como destino? O Cloudflare enviará uma mensagem de verificação para esse endereço.`, 'Usar email do portal')) return
  saving.value = true
  try { await api.post('/admin/cloudflare/email/destinations/portal'); await load(); feedback.show('Email do portal adicionado. Confirme a mensagem enviada pelo Cloudflare.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
function newRule() { editingRuleId.value = null; Object.assign(ruleForm, emptyRule(), { source: `geral@${data.value.zoneName}` }); ruleDialog.value = true }
function editRule(item) { editingRuleId.value = item.id; Object.assign(ruleForm, { source: item.source, destination: item.destination, enabled: item.enabled }); ruleDialog.value = true }
async function saveRule() {
  if (!ruleForm.source.trim() || !ruleForm.destination) return feedback.show('Indique o endereço do domínio e o email de destino.', 'warning')
  if (!await feedback.confirm(`Encaminhar ${ruleForm.source} para ${ruleForm.destination}?`, 'Confirmar encaminhamento')) return
  saving.value = true
  try {
    if (editingRuleId.value) await api.put(`/admin/cloudflare/email/rules/${editingRuleId.value}`, ruleForm)
    else await api.post('/admin/cloudflare/email/rules', ruleForm)
    ruleDialog.value = false; await load(); feedback.show('Encaminhamento de email guardado.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function toggleRule(item, enabled) {
  try { await api.put(`/admin/cloudflare/email/rules/${item.id}`, { source: item.source, destination: item.destination, enabled }); await load(); feedback.show(enabled ? 'Encaminhamento ativado.' : 'Encaminhamento desativado.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}
async function deleteRule(item) {
  if (!await feedback.confirm(`Eliminar o encaminhamento de ${item.source}?`, 'Eliminar encaminhamento')) return
  try { await api.delete(`/admin/cloudflare/email/rules/${item.id}`); await load(); feedback.show('Encaminhamento eliminado.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}

onMounted(load)
</script>

<template>
  <div class="page cloudflare-page">
    <div class="page-head"><div><div class="text-overline text-secondary font-weight-bold">Exclusivo Developer</div><h1>Domínio e Cloudflare</h1><p>Controle o DNS e o encaminhamento de email de <b>{{ data.zoneName }}</b> sem sair do portal.</p></div><v-btn v-if="data.connected" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="load">Atualizar estado</v-btn></div>
    <v-progress-linear v-if="loading" indeterminate color="secondary" class="mb-4" />

    <v-card v-if="!data.connected" class="soft-card connection-card pa-6">
      <div class="connection-icon"><v-icon size="42">mdi-cloud-lock-outline</v-icon></div><div><h2 class="text-h5 font-weight-bold">Ligar vitorgouveia.com</h2><p class="text-medium-emphasis mt-1">Use um API Token limitado a esta zona, com leitura da zona, gestão de DNS e Email Routing. O token fica guardado apenas no servidor e nunca volta a ser apresentado.</p></div>
      <v-expand-transition><div v-if="showTokenForm" class="mt-5"><v-text-field v-model="token" type="password" autocomplete="new-password" label="API Token do Cloudflare" hint="O portal valida o acesso a vitorgouveia.com antes de guardar." persistent-hint prepend-inner-icon="mdi-key-outline" @keyup.enter="connect" /><div class="d-flex justify-end ga-2 mt-3"><v-btn variant="text" @click="showTokenForm = false; token = ''">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="connect">Validar e ligar</v-btn></div></div></v-expand-transition>
      <v-btn v-if="!showTokenForm" color="primary" prepend-icon="mdi-link-variant" class="mt-5" @click="showTokenForm = true">Configurar ligação</v-btn>
    </v-card>

    <template v-else>
      <div class="status-grid mb-5">
        <v-card class="soft-card status-card"><v-icon color="success">mdi-check-decagram-outline</v-icon><div><span>Ligação</span><strong>Cloudflare ligado</strong></div></v-card>
        <v-card class="soft-card status-card"><v-icon color="primary">mdi-web</v-icon><div><span>Zona</span><strong>{{ data.zone?.name }}</strong></div></v-card>
        <v-card class="soft-card status-card"><v-icon :color="data.zone?.status === 'active' ? 'success' : 'warning'">mdi-cloud-check-outline</v-icon><div><span>Estado</span><strong>{{ data.zone?.status === 'active' ? 'Ativo' : data.zone?.status }}</strong></div></v-card>
      </div>

      <v-card class="soft-card pa-5 mb-5">
        <div class="section-head"><div><h2>Registos DNS</h2><p>Endereços, subdomínios e validações do domínio.</p></div><v-btn color="primary" prepend-icon="mdi-plus" @click="newRecord">Novo registo</v-btn></div>
        <v-text-field v-model="recordSearch" label="Pesquisar registo" prepend-inner-icon="mdi-magnify" clearable hide-details class="my-4" />
        <div v-if="filteredRecords.length" class="record-list"><div v-for="item in filteredRecords" :key="item.id" class="record-row"><v-chip size="small" color="primary" variant="tonal" class="record-type">{{ item.type }}</v-chip><div class="record-main"><b>{{ item.name }}</b><span>{{ item.content }}</span></div><div class="record-flags"><v-chip v-if="item.proxiable" size="x-small" :color="item.proxied ? 'warning' : 'grey'" variant="tonal">{{ item.proxied ? 'Proxy ativo' : 'Só DNS' }}</v-chip><span>TTL {{ item.ttl === 1 ? 'Auto' : item.ttl }}</span></div><div class="record-actions"><v-btn icon="mdi-pencil-outline" variant="text" :aria-label="`Editar ${item.name}`" @click="editRecord(item)" /><v-btn icon="mdi-delete-outline" variant="text" color="error" :aria-label="`Eliminar ${item.name}`" @click="deleteRecord(item)" /></div></div></div>
        <div v-else class="empty-section"><v-icon size="44">mdi-dns-outline</v-icon><span>Não existem registos para mostrar.</span></div>
      </v-card>

      <v-card class="soft-card pa-5">
        <div class="section-head"><div><h2>Email @{{ data.zoneName }}</h2><p>Escolha para onde são encaminhados os endereços do domínio.</p></div><div class="d-flex flex-wrap ga-2"><v-btn v-if="data.portalEmailConfigured" variant="tonal" prepend-icon="mdi-email-check-outline" :loading="saving" @click="addPortalDestination">Usar email do portal</v-btn><v-btn variant="tonal" prepend-icon="mdi-email-plus-outline" @click="destinationDialog = true">Outro destino</v-btn><v-btn color="primary" prepend-icon="mdi-plus" :disabled="!verifiedDestinations.length" @click="newRule">Novo encaminhamento</v-btn></div></div>
        <v-alert v-if="!data.email?.available" type="warning" variant="tonal" class="mt-4">O token atual não permite consultar o Email Routing. Adicione as permissões de Email Routing ao token Cloudflare.</v-alert>
        <template v-else><div class="email-summary my-4"><v-chip :color="data.email.enabled ? 'success' : 'warning'" variant="tonal" prepend-icon="mdi-email-fast-outline">{{ data.email.enabled ? 'Email Routing ativo' : 'Email Routing inativo' }}</v-chip><span>{{ verifiedDestinations.length }} destinos verificados</span></div><div v-if="data.email.rules.length" class="rule-list"><div v-for="item in data.email.rules" :key="item.id" class="email-rule"><v-icon color="primary">mdi-email-arrow-right-outline</v-icon><div><b>{{ item.source }}</b><span>encaminha para {{ item.destination || 'ação personalizada' }}</span></div><v-switch :model-value="item.enabled" color="success" hide-details :disabled="item.sourceType === 'wrangler' || item.source === '*' || !item.destination" :aria-label="`Ativar encaminhamento ${item.source}`" @update:model-value="toggleRule(item, $event)" /><v-btn icon="mdi-pencil-outline" variant="text" :disabled="item.sourceType === 'wrangler' || item.source === '*' || !item.destination" :aria-label="`Editar ${item.source}`" @click="editRule(item)" /><v-btn icon="mdi-delete-outline" variant="text" color="error" :disabled="item.sourceType === 'wrangler'" :aria-label="`Eliminar ${item.source}`" @click="deleteRule(item)" /></div></div><div v-else class="empty-section"><v-icon size="44">mdi-email-outline</v-icon><span>Ainda não existem encaminhamentos de email.</span></div><div v-if="data.email.destinations.length" class="destination-list mt-5"><h3 class="text-subtitle-1 font-weight-bold mb-2">Emails de destino</h3><v-chip v-for="item in data.email.destinations" :key="item.id" :color="item.verified ? 'success' : 'warning'" variant="tonal" :prepend-icon="item.verified ? 'mdi-check-circle-outline' : 'mdi-clock-outline'">{{ item.email }} · {{ item.verified ? 'verificado' : 'aguarda verificação' }}</v-chip></div></template>
      </v-card>
    </template>

    <v-dialog v-model="recordDialog" max-width="720" persistent><v-card><v-card-title class="pa-6 pb-2">{{ editingRecordId ? 'Editar registo DNS' : 'Novo registo DNS' }}</v-card-title><v-card-text class="pa-6"><v-row><v-col cols="12" sm="4"><v-select v-model="recordForm.type" :items="['A','AAAA','CNAME','MX','TXT']" label="Tipo" /></v-col><v-col cols="12" sm="8"><v-text-field v-model.trim="recordForm.name" label="Nome completo" hint="Ex.: www.vitorgouveia.com" persistent-hint /></v-col><v-col cols="12"><v-textarea v-model.trim="recordForm.content" label="Conteúdo / destino" rows="2" auto-grow /></v-col><v-col cols="12" sm="4"><v-text-field v-model.number="recordForm.ttl" type="number" inputmode="numeric" min="1" max="86400" label="TTL" hint="1 = automático" persistent-hint /></v-col><v-col v-if="recordForm.type === 'MX'" cols="12" sm="4"><v-text-field v-model.number="recordForm.priority" type="number" inputmode="numeric" min="0" max="65535" label="Prioridade" /></v-col><v-col v-if="['A','AAAA','CNAME'].includes(recordForm.type)" cols="12" sm="4"><v-switch v-model="recordForm.proxied" color="warning" inset label="Proxy Cloudflare" /></v-col></v-row><v-alert type="warning" variant="tonal" density="compact">Confirme cuidadosamente o destino. Registos incorretos podem interromper o site ou o email.</v-alert></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="recordDialog = false">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="saveRecord">Guardar registo</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="destinationDialog" max-width="560"><v-card><v-card-title class="pa-6 pb-2">Novo email de destino</v-card-title><v-card-text class="pa-6"><v-text-field v-model.trim="destinationEmail" type="email" inputmode="email" label="Email que vai receber as mensagens" hint="O Cloudflare enviará uma mensagem de verificação." persistent-hint /></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="destinationDialog = false">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="addDestination">Adicionar e verificar</v-btn></v-card-actions></v-card></v-dialog>

    <v-dialog v-model="ruleDialog" max-width="620" persistent><v-card><v-card-title class="pa-6 pb-2">{{ editingRuleId ? 'Editar encaminhamento' : 'Novo encaminhamento' }}</v-card-title><v-card-text class="pa-6"><v-text-field v-model.trim="ruleForm.source" type="email" inputmode="email" label="Endereço @vitorgouveia.com" hint="Ex.: geral@vitorgouveia.com" persistent-hint class="mb-3" /><v-select v-model="ruleForm.destination" :items="verifiedDestinations" label="Encaminhar para" hint="Apenas aparecem destinos já verificados no Cloudflare." persistent-hint /><v-switch v-model="ruleForm.enabled" color="success" inset label="Encaminhamento ativo" /></v-card-text><v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="ruleDialog = false">Cancelar</v-btn><v-btn color="primary" :loading="saving" @click="saveRule">Guardar encaminhamento</v-btn></v-card-actions></v-card></v-dialog>
  </div>
</template>

<style scoped>
.connection-card { margin-inline: auto; max-width: 760px; }.connection-icon { align-items: center; background: rgba(var(--v-theme-primary), .09); border-radius: 18px; color: rgb(var(--v-theme-primary)); display: flex; height: 74px; justify-content: center; margin-bottom: 18px; width: 74px; }.status-grid { display: grid; gap: 14px; grid-template-columns: repeat(3, minmax(0, 1fr)); }.status-card { align-items: center; display: flex; gap: 14px; min-height: 92px; padding: 18px; }.status-card .v-icon { font-size: 30px; }.status-card div { display: flex; flex-direction: column; min-width: 0; }.status-card span { color: rgba(var(--v-theme-on-surface), .6); font-size: .75rem; }.status-card strong { overflow-wrap: anywhere; }.section-head { align-items: center; display: flex; gap: 16px; justify-content: space-between; }.section-head h2 { font-size: 1.2rem; }.section-head p { color: rgba(var(--v-theme-on-surface), .62); font-size: .84rem; margin-top: 3px; }.record-list, .rule-list { border: 1px solid rgba(var(--v-theme-on-surface), .1); border-radius: 14px; overflow: hidden; }.record-row { align-items: center; display: grid; gap: 12px; grid-template-columns: 62px minmax(0, 1fr) auto auto; min-height: 76px; padding: 12px 14px; }.record-row + .record-row, .email-rule + .email-rule { border-top: 1px solid rgba(var(--v-theme-on-surface), .08); }.record-main { display: flex; flex-direction: column; min-width: 0; }.record-main b, .record-main span { overflow-wrap: anywhere; }.record-main span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; }.record-flags { align-items: flex-end; color: rgba(var(--v-theme-on-surface), .58); display: flex; flex-direction: column; font-size: .72rem; gap: 4px; }.record-actions { display: flex; }.email-summary { align-items: center; display: flex; flex-wrap: wrap; gap: 12px; }.email-summary > span { color: rgba(var(--v-theme-on-surface), .62); font-size: .82rem; }.email-rule { align-items: center; display: grid; gap: 12px; grid-template-columns: auto minmax(0, 1fr) auto auto auto; min-height: 76px; padding: 10px 14px; }.email-rule > div { display: flex; flex-direction: column; min-width: 0; }.email-rule span { color: rgba(var(--v-theme-on-surface), .62); font-size: .78rem; overflow-wrap: anywhere; }.destination-list { display: flex; flex-wrap: wrap; gap: 8px; }.destination-list h3 { flex-basis: 100%; }.empty-section { align-items: center; color: rgba(var(--v-theme-on-surface), .55); display: flex; flex-direction: column; gap: 10px; justify-content: center; min-height: 150px; text-align: center; }
@media (max-width: 760px) { .status-grid { grid-template-columns: 1fr; }.section-head { align-items: stretch; flex-direction: column; }.section-head .v-btn { width: 100%; }.record-row { align-items: start; grid-template-columns: auto minmax(0, 1fr) auto; }.record-flags { align-items: flex-start; grid-column: 2 / -1; }.record-actions { grid-column: 3; grid-row: 1 / 3; }.email-rule { align-items: start; grid-template-columns: auto minmax(0, 1fr) auto; }.email-rule .v-switch { grid-column: 2; }.email-rule .v-btn { grid-row: 2; } }
</style>
