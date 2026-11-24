<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const route = useRoute()
const data = ref(null)
const loading = ref(false)
const installing = ref(false)
const savingMetadata = ref(false)
const tab = ref(route.query.tab === 'announcements' ? 'announcements' : route.query.tab === 'history' ? 'history' : 'release')
const channel = ref('stable')
const notificationMode = ref('notify')
const announcementCenter = ref(null)
const announcementDialog = ref(false)
const announcementVersion = ref('')
const selectedAnnouncementNotes = ref([])
const creatingAnnouncement = ref(false)
const centerLoading = ref(false)
const channelOptions = [
  { title: 'Estável', value: 'stable', color: 'success', icon: 'mdi-shield-check-outline' },
  { title: 'Beta', value: 'beta', color: 'info', icon: 'mdi-flask-outline' },
  { title: 'Experimental', value: 'experimental', color: 'warning', icon: 'mdi-test-tube' },
  { title: 'Teste', value: 'test', color: 'secondary', icon: 'mdi-bug-check-outline' },
]

const shownRelease = computed(() => data.value?.pending || data.value?.current)
const shownSections = computed(() => releaseSections(shownRelease.value))
const changeCount = computed(() => shownSections.value.reduce((total, section) => total + section.items.length, 0))
const settingsDirty = computed(() => {
  if (!data.value?.pending) return false
  return channel.value !== (data.value.pending.channel || 'stable') || (notificationMode.value === 'notify') !== (data.value.pending.notifyAdminsOnLogin !== false)
})
const selectedAnnouncementRelease = computed(() => announcementCenter.value?.releases?.find(release => release.version === announcementVersion.value) || null)
const selectedReleaseNotes = computed(() => (selectedAnnouncementRelease.value?.sections || []).flatMap(section => (section.items || []).map(text => ({ section: section.title, text }))))
const activeAnnouncementCount = computed(() => announcementCenter.value?.announcements?.filter(item => item.active).length || 0)

function releaseSections(release) {
  if (release?.sections?.length) return release.sections
  if (release?.notes?.length) return [{ title: 'Alterações', items: release.notes }]
  return []
}
function dateTime(value) { return value ? new Date(value).toLocaleString('pt-PT') : '—' }
function channelInfo(value) { return channelOptions.find(item => item.value === value) || channelOptions[0] }
function sectionIcon(title = '', index = 0) {
  const value = title.toLowerCase()
  if (value.includes('promo')) return 'mdi-sale-outline'
  if (value.includes('oferta')) return 'mdi-gift-outline'
  if (value.includes('carrinho')) return 'mdi-cart-outline'
  if (value.includes('developer') || value.includes('acesso')) return 'mdi-shield-account-outline'
  if (value.includes('atualiza')) return 'mdi-update'
  return ['mdi-star-four-points-outline', 'mdi-lightning-bolt-outline', 'mdi-check-decagram-outline'][index % 3]
}
async function load() {
  loading.value = true
  try {
    data.value = (await api.get('/admin/system-update')).data
    channel.value = data.value.pending?.channel || 'stable'
    notificationMode.value = data.value.pending?.notifyAdminsOnLogin === false ? 'silent' : 'notify'
    if (data.value.canEditRelease) await loadAnnouncementCenter()
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
async function loadAnnouncementCenter() {
  centerLoading.value = true
  try { announcementCenter.value = (await api.get('/admin/system-update/announcement-center')).data }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { centerLoading.value = false }
}
function openAnnouncementDialog() {
  announcementVersion.value = ''
  selectedAnnouncementNotes.value = []
  announcementDialog.value = true
}
function chooseAnnouncementVersion(version) { announcementVersion.value = version; selectedAnnouncementNotes.value = [] }
function releaseChangeCount(release) { return (release.sections || []).reduce((total, section) => total + (section.items || []).length, 0) }
function toggleAnnouncementNote(note) {
  selectedAnnouncementNotes.value = selectedAnnouncementNotes.value.includes(note) ? selectedAnnouncementNotes.value.filter(value => value !== note) : [...selectedAnnouncementNotes.value, note]
}
function selectAllAnnouncementNotes() {
  selectedAnnouncementNotes.value = selectedAnnouncementNotes.value.length === selectedReleaseNotes.value.length ? [] : selectedReleaseNotes.value.map(item => item.text)
}
async function createAnnouncement() {
  if (!announcementVersion.value || !selectedAnnouncementNotes.value.length) return feedback.show('Escolha uma versão e pelo menos uma alteração.', 'warning')
  creatingAnnouncement.value = true
  try {
    await api.post('/admin/system-update/announcements', { version: announcementVersion.value, selected_notes: selectedAnnouncementNotes.value })
    announcementDialog.value = false
    await loadAnnouncementCenter()
    feedback.show('Aviso publicado para os administradores.', 'success')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { creatingAnnouncement.value = false }
}
async function toggleAnnouncement(item, active) {
  const previous = item.active
  item.active = active
  try { await api.patch(`/admin/system-update/announcements/${item.id}`, { active }); await loadAnnouncementCenter(); feedback.show(active ? 'Aviso reativado.' : 'Aviso pausado.') }
  catch (error) { item.active = previous; feedback.show(errorMessage(error), 'error') }
}
async function removeAnnouncement(item) {
  if (!await feedback.confirm(`Eliminar o aviso da versão ${item.version} e todo o respetivo histórico de visualizações?`, 'Eliminar aviso')) return
  try { await api.delete(`/admin/system-update/announcements/${item.id}`); await loadAnnouncementCenter(); feedback.show('Aviso eliminado.') }
  catch (error) { feedback.show(errorMessage(error), 'error') }
}
async function install() {
  if (!data.value?.updateAvailable || !data.value?.canInstall) return
  if (!await feedback.confirm(`Instalar a versão ${data.value.pending.version}? O portal reinicia automaticamente e poderá ficar indisponível durante alguns segundos.`, 'Atualizar o site')) return
  installing.value = true
  try {
    await api.post('/admin/system-update/apply')
    feedback.show('Atualização iniciada. O portal vai reiniciar automaticamente.', 'success')
    setTimeout(() => window.location.reload(), 8000)
  } catch (error) { feedback.show(errorMessage(error), 'error'); installing.value = false }
}
async function saveMetadata() {
  if (!data.value?.pending) return
  savingMetadata.value = true
  try {
    await api.put('/admin/system-update/metadata', { channel: channel.value, notify_admins_on_login: notificationMode.value === 'notify' })
    await load()
    feedback.show(notificationMode.value === 'notify' ? 'Os administradores serão avisados ao iniciarem sessão.' : 'Esta atualização não será anunciada no login.', 'success')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingMetadata.value = false }
}
onMounted(async () => { await load(); if (data.value?.canEditRelease && route.query.create === '1') openAnnouncementDialog() })
</script>

<template>
  <div class="page updates-page">
    <div class="page-head">
      <div><h1>Atualizações</h1><p>Consulte cada versão, escolha como é anunciada e reveja todo o histórico.</p></div>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-refresh" :loading="loading" @click="load">Verificar</v-btn>
    </div>
    <v-skeleton-loader v-if="!data" type="article, article" />
    <template v-else>
      <v-alert :type="data.updateAvailable ? 'info' : data.state === 'incomplete' ? 'warning' : 'success'" variant="tonal" class="mb-5" :title="data.updateAvailable ? 'Atualização pronta' : data.state === 'incomplete' ? 'Preparação incompleta' : 'O site está atualizado'">
        {{ data.updateAvailable ? `A versão ${data.pending.version} está pronta para instalar.` : data.state === 'incomplete' ? 'Existe uma atualização registada, mas o pacote ainda não está completo.' : 'Não existem atualizações pendentes.' }}
      </v-alert>

      <v-tabs v-model="tab" color="primary" class="update-tabs mb-5">
        <v-tab value="release" prepend-icon="mdi-text-box-check-outline">Versão atual</v-tab>
        <v-tab value="history" prepend-icon="mdi-history">Histórico ({{ data.history?.length || 0 }})</v-tab>
        <v-tab v-if="data.canEditRelease" value="announcements" prepend-icon="mdi-bullhorn-outline">Os meus avisos ({{ activeAnnouncementCount }})</v-tab>
      </v-tabs>

      <v-window v-model="tab">
        <v-window-item value="release">
          <v-card class="release-hero mb-5" variant="flat">
            <div class="release-hero-main">
              <div class="release-icon"><v-icon size="34">mdi-rocket-launch-outline</v-icon></div>
              <div class="release-copy">
                <div class="d-flex flex-wrap align-center ga-2 mb-2">
                  <v-chip size="small" :color="channelInfo(shownRelease?.channel).color" variant="tonal" :prepend-icon="channelInfo(shownRelease?.channel).icon">{{ channelInfo(shownRelease?.channel).title }}</v-chip>
                  <v-chip v-if="data.pending" size="small" color="info" variant="tonal" prepend-icon="mdi-clock-outline">Pendente</v-chip>
                  <v-chip v-else size="small" color="success" variant="tonal" prepend-icon="mdi-check-circle-outline">Instalada</v-chip>
                </div>
                <div class="release-version">{{ shownRelease?.version || 'Sem registo' }}</div>
                <h2>{{ shownRelease?.title || `Notas da versão ${shownRelease?.version || ''}` }}</h2>
                <p>{{ shownRelease?.summary || 'Ainda não existe um resumo para esta versão.' }}</p>
                <div class="release-facts">
                  <span><v-icon size="18">mdi-calendar-outline</v-icon>{{ dateTime(shownRelease?.installedAt || shownRelease?.releasedAt) }}</span>
                  <span><v-icon size="18">mdi-format-list-checks</v-icon>{{ changeCount }} alterações em {{ shownSections.length }} secções</span>
                  <span v-if="data.pending"><v-icon size="18">{{ data.pending.notifyAdminsOnLogin === false ? 'mdi-bell-off-outline' : 'mdi-bell-ring-outline' }}</v-icon>{{ data.pending.notifyAdminsOnLogin === false ? 'Sem aviso no login' : 'Aviso aos admins ativo' }}</span>
                </div>
              </div>
            </div>
            <div class="release-action">
              <div class="installed-version"><span>Instalada</span><strong>{{ data.current?.version || '—' }}</strong></div>
              <v-btn v-if="data.canInstall" block size="large" color="primary" prepend-icon="mdi-download-circle-outline" :disabled="!data.updateAvailable" :loading="installing" @click="install">Atualizar o site</v-btn>
              <v-alert v-else type="info" variant="tonal" density="compact">Não tem permissão para instalar esta atualização.</v-alert>
            </div>
          </v-card>

          <v-card v-if="data.canEditRelease && data.pending" class="developer-controls soft-card pa-5 mb-5">
            <div class="control-heading">
              <v-avatar color="secondary" variant="tonal" size="48"><v-icon>mdi-account-cog-outline</v-icon></v-avatar>
              <div><div class="text-h6 font-weight-bold">Controlo de lançamento — Developer</div><div class="text-body-2 text-medium-emphasis">Estas opções aplicam-se apenas à versão {{ data.pending.version }} enquanto estiver pendente.</div></div>
            </div>
            <v-row class="mt-2">
              <v-col cols="12" md="4"><v-select v-model="channel" :items="channelOptions" item-title="title" item-value="value" label="Canal da atualização" persistent-hint hint="Identifica o nível de estabilidade desta versão."><template #selection="{ item }"><v-chip :color="item.raw.color" variant="tonal" :prepend-icon="item.raw.icon">{{ item.raw.title }}</v-chip></template></v-select></v-col>
              <v-col cols="12" md="8">
                <div class="setting-label">Aviso aos administradores quando iniciam sessão</div>
                <div class="notification-choices" role="radiogroup" aria-label="Aviso aos administradores">
                  <button type="button" class="notification-choice" :class="{ active: notificationMode === 'notify' }" role="radio" :aria-checked="notificationMode === 'notify'" @click="notificationMode = 'notify'">
                    <span class="choice-icon"><v-icon>mdi-bell-ring-outline</v-icon></span><span><b>Notificar no login</b><small>Cada administrador vê o aviso uma vez por login enquanto a versão estiver pendente.</small></span><v-icon class="choice-check">{{ notificationMode === 'notify' ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank' }}</v-icon>
                  </button>
                  <button type="button" class="notification-choice" :class="{ active: notificationMode === 'silent' }" role="radio" :aria-checked="notificationMode === 'silent'" @click="notificationMode = 'silent'">
                    <span class="choice-icon"><v-icon>mdi-bell-off-outline</v-icon></span><span><b>Não notificar</b><small>A atualização continua visível no botão, mas não abre qualquer aviso no login.</small></span><v-icon class="choice-check">{{ notificationMode === 'silent' ? 'mdi-radiobox-marked' : 'mdi-radiobox-blank' }}</v-icon>
                  </button>
                </div>
              </v-col>
            </v-row>
            <div class="control-footer"><div class="current-choice"><v-icon size="19">{{ notificationMode === 'notify' ? 'mdi-bell-check-outline' : 'mdi-bell-cancel-outline' }}</v-icon>{{ notificationMode === 'notify' ? 'Os administradores serão avisados no próximo login.' : 'O aviso no login ficará desativado.' }}</div><v-btn color="primary" prepend-icon="mdi-content-save-outline" :disabled="!settingsDirty" :loading="savingMetadata" @click="saveMetadata">Guardar opções</v-btn></div>
          </v-card>

          <div v-if="shownSections.length" class="release-sections">
            <v-card v-for="(section, sectionIndex) in shownSections" :key="section.title" class="release-section soft-card" variant="flat">
              <div class="section-heading"><v-avatar color="primary" variant="tonal" size="44"><v-icon>{{ sectionIcon(section.title, sectionIndex) }}</v-icon></v-avatar><div><h3>{{ section.title }}</h3><span>{{ section.items.length }} {{ section.items.length === 1 ? 'alteração' : 'alterações' }}</span></div></div>
              <div class="change-list"><div v-for="(note, noteIndex) in section.items" :key="noteIndex" class="change-item"><span class="change-number">{{ noteIndex + 1 }}</span><p>{{ note }}</p></div></div>
            </v-card>
          </div>
          <v-card v-else class="empty-notes soft-card">Ainda não existem notas para esta versão.</v-card>
        </v-window-item>

        <v-window-item value="history">
          <div class="history-intro mb-4"><div><h2>Histórico de versões</h2><p>Consulte o resumo e abra cada versão para ver todas as alterações.</p></div><v-chip color="primary" variant="tonal" prepend-icon="mdi-archive-outline">{{ data.history?.length || 0 }} versões</v-chip></div>
          <v-expansion-panels v-if="data.history?.length" variant="accordion" class="history-list">
            <v-expansion-panel v-for="release in data.history" :key="release.version" class="history-panel">
              <v-expansion-panel-title>
                <div class="history-title"><v-avatar color="primary" variant="tonal"><v-icon>mdi-package-variant-closed-check</v-icon></v-avatar><div><div class="d-flex flex-wrap align-center ga-2"><strong>{{ release.version }}</strong><v-chip size="x-small" :color="channelInfo(release.channel).color" variant="tonal">{{ channelInfo(release.channel).title }}</v-chip></div><span>{{ release.title || 'Atualização do portal' }}</span><small>{{ dateTime(release.installedAt || release.releasedAt) }}</small></div></div>
              </v-expansion-panel-title>
              <v-expansion-panel-text><p class="history-summary">{{ release.summary || release.notes?.[0] || 'Sem resumo.' }}</p><div class="history-sections"><section v-for="(section, index) in releaseSections(release)" :key="section.title"><h3><v-icon size="19">{{ sectionIcon(section.title, index) }}</v-icon>{{ section.title }}</h3><ul><li v-for="(note, noteIndex) in section.items" :key="noteIndex">{{ note }}</li></ul></section></div></v-expansion-panel-text>
            </v-expansion-panel>
          </v-expansion-panels>
          <v-card v-else class="empty-notes soft-card">O histórico começa a ser preenchido com as próximas instalações.</v-card>
        </v-window-item>

        <v-window-item v-if="data.canEditRelease" value="announcements">
          <div class="announcement-head mb-5"><div><h2>Centro de avisos do Developer</h2><p>Escolha alterações de qualquer versão e acompanhe quem abriu ou confirmou cada aviso.</p></div><v-btn color="primary" prepend-icon="mdi-bullhorn-outline" @click="openAnnouncementDialog">Criar aviso</v-btn></div>
          <v-progress-linear v-if="centerLoading" indeterminate color="primary" class="mb-4" />
          <div v-if="announcementCenter?.announcements?.length" class="announcement-list">
            <v-card v-for="item in announcementCenter.announcements" :key="item.id" class="announcement-card soft-card" variant="flat">
              <div class="announcement-card-top">
                <div class="announcement-identity"><v-avatar :color="item.active ? 'primary' : 'grey'" variant="tonal"><v-icon>mdi-bullhorn-outline</v-icon></v-avatar><div><div class="d-flex flex-wrap align-center ga-2"><strong>Versão {{ item.version }}</strong><v-chip size="x-small" :color="item.active ? 'success' : 'grey'" variant="tonal">{{ item.active ? 'A notificar' : 'Pausado' }}</v-chip></div><span>{{ item.title }}</span><small>Criado em {{ dateTime(item.createdAt) }}<template v-if="item.createdBy"> por {{ item.createdBy }}</template></small></div></div>
                <div class="announcement-actions"><v-switch :model-value="item.active" color="success" hide-details :aria-label="`Ativar aviso ${item.version}`" @update:model-value="toggleAnnouncement(item, $event)" /><v-btn icon="mdi-delete-outline" color="error" variant="text" :aria-label="`Eliminar aviso ${item.version}`" @click="removeAnnouncement(item)" /></div>
              </div>
              <div class="announcement-metrics"><div><span>{{ item.acknowledgedCount }}</span><small>clicaram em Lido</small></div><div><span>{{ item.ignoredCount }}</span><small>clicaram em Ignorar</small></div><div><span>{{ item.pendingCount }}</span><small>ainda não abriram</small></div><div><span>{{ item.notes.length }}</span><small>alterações anunciadas</small></div></div>
              <v-progress-linear :model-value="item.recipientCount ? (item.viewedCount / item.recipientCount) * 100 : 0" color="success" height="8" rounded class="mb-4" />
              <v-expansion-panels variant="accordion">
                <v-expansion-panel>
                  <v-expansion-panel-title><v-icon class="mr-2">mdi-format-list-checks</v-icon>Alterações selecionadas</v-expansion-panel-title>
                  <v-expansion-panel-text><div class="announced-notes"><div v-for="(note, index) in item.notes" :key="index"><v-icon size="18" color="primary">mdi-check-circle-outline</v-icon><span><small>{{ note.section }}</small>{{ note.text }}</span></div></div></v-expansion-panel-text>
                </v-expansion-panel>
                <v-expansion-panel>
                  <v-expansion-panel-title><v-icon class="mr-2">mdi-account-eye-outline</v-icon>Administradores e visualizações</v-expansion-panel-title>
                  <v-expansion-panel-text><div class="recipient-list"><div v-for="recipient in item.recipients" :key="recipient.id" class="recipient-row"><v-avatar size="36" :color="recipient.status === 'acknowledged' ? 'success' : recipient.status === 'ignored' ? 'warning' : recipient.status === 'viewed' ? 'info' : 'grey'" variant="tonal"><v-icon size="20">{{ recipient.status === 'acknowledged' ? 'mdi-check-decagram-outline' : recipient.status === 'ignored' ? 'mdi-close-circle-outline' : recipient.status === 'viewed' ? 'mdi-eye-outline' : 'mdi-clock-outline' }}</v-icon></v-avatar><div><b>{{ recipient.fullName }}</b><span>@{{ recipient.username }}</span></div><div class="recipient-state"><v-chip size="small" :color="recipient.status === 'acknowledged' ? 'success' : recipient.status === 'ignored' ? 'warning' : recipient.status === 'viewed' ? 'info' : 'grey'" variant="tonal">{{ recipient.status === 'acknowledged' ? 'Clicou em Lido' : recipient.status === 'ignored' ? 'Clicou em Ignorar' : recipient.status === 'viewed' ? 'Abriu o aviso' : 'Ainda não abriu' }}</v-chip><small v-if="recipient.acknowledgedAt || recipient.ignoredAt || recipient.viewedAt">{{ dateTime(recipient.acknowledgedAt || recipient.ignoredAt || recipient.viewedAt) }}</small></div></div></div></v-expansion-panel-text>
                </v-expansion-panel>
              </v-expansion-panels>
            </v-card>
          </div>
          <v-card v-else-if="!centerLoading" class="empty-notes soft-card"><div><v-icon size="56" color="primary">mdi-bullhorn-outline</v-icon><h3 class="mt-3">Ainda não criou avisos personalizados</h3><p class="text-medium-emphasis">Pode recuperar uma versão antiga e anunciar apenas as alterações que escolher.</p><v-btn color="primary" class="mt-3" @click="openAnnouncementDialog">Criar primeiro aviso</v-btn></div></v-card>
        </v-window-item>
      </v-window>

      <v-dialog v-model="announcementDialog" max-width="900" persistent>
        <v-card>
          <v-card-title class="pa-6 pb-2">Criar aviso de atualização</v-card-title>
          <v-card-text class="pa-6">
            <template v-if="!selectedAnnouncementRelease">
              <div class="version-step-heading"><div class="step-number">1</div><div><h3>Escolha uma versão</h3><p>Estão disponíveis a versão atual e todas as versões antigas guardadas.</p></div></div>
              <div v-if="announcementCenter?.releases?.length" class="version-picker">
                <button v-for="release in announcementCenter.releases" :key="release.version" type="button" class="version-option" @click="chooseAnnouncementVersion(release.version)">
                  <span class="version-option-icon"><v-icon>mdi-package-variant-closed-check</v-icon></span>
                  <span class="version-option-copy"><b>Versão {{ release.version }}</b><strong>{{ release.title }}</strong><small>{{ releaseChangeCount(release) }} alterações disponíveis</small></span>
                  <v-icon color="primary">mdi-chevron-right</v-icon>
                </button>
              </div>
              <v-alert v-else type="warning" variant="tonal">Não foram encontradas versões no histórico.</v-alert>
            </template>
            <template v-else>
              <div class="selected-version-bar"><v-btn icon="mdi-arrow-left" variant="tonal" aria-label="Voltar à lista de versões" @click="announcementVersion = ''; selectedAnnouncementNotes = []" /><div><span>Versão escolhida</span><b>{{ selectedAnnouncementRelease.version }} — {{ selectedAnnouncementRelease.title }}</b></div><v-chip color="primary" variant="tonal">{{ releaseChangeCount(selectedAnnouncementRelease) }} alterações</v-chip></div>
              <div class="version-step-heading mt-5"><div class="step-number">2</div><div><h3>Escolha o que pretende notificar</h3><p>Marque apenas as alterações que devem aparecer no pop-up dos administradores.</p></div></div>
              <div class="announcement-release-summary"><b>{{ selectedAnnouncementRelease.title }}</b><p>{{ selectedAnnouncementRelease.summary }}</p></div>
              <div class="selection-toolbar"><div><strong>{{ selectedAnnouncementNotes.length }}</strong> de {{ selectedReleaseNotes.length }} alterações selecionadas</div><v-btn variant="tonal" size="small" @click="selectAllAnnouncementNotes">{{ selectedAnnouncementNotes.length === selectedReleaseNotes.length ? 'Desmarcar todas' : 'Selecionar todas' }}</v-btn></div>
              <div class="announcement-note-groups"><section v-for="section in selectedAnnouncementRelease.sections || []" :key="section.title"><h3>{{ section.title }}</h3><button v-for="note in section.items" :key="note" type="button" class="selectable-note" :class="{ selected: selectedAnnouncementNotes.includes(note) }" :aria-pressed="selectedAnnouncementNotes.includes(note)" @click="toggleAnnouncementNote(note)"><v-icon>{{ selectedAnnouncementNotes.includes(note) ? 'mdi-checkbox-marked-circle' : 'mdi-checkbox-blank-circle-outline' }}</v-icon><span>{{ note }}</span></button></section></div>
            </template>
          </v-card-text>
          <v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="announcementDialog = false">Cancelar</v-btn><v-btn v-if="selectedAnnouncementRelease" color="primary" prepend-icon="mdi-send-outline" :disabled="!selectedAnnouncementNotes.length" :loading="creatingAnnouncement" @click="createAnnouncement">Publicar aviso</v-btn></v-card-actions>
        </v-card>
      </v-dialog>
    </template>
  </div>
</template>

<style scoped>
.update-tabs { border-bottom: 1px solid rgba(var(--v-theme-on-surface), .1); }
.release-hero { background: linear-gradient(135deg, rgba(var(--v-theme-primary), .10), rgba(var(--v-theme-secondary), .055)); border: 1px solid rgba(var(--v-theme-primary), .16); border-radius: 20px; display: grid; gap: 28px; grid-template-columns: minmax(0, 1fr) 230px; padding: 28px; }
.release-hero-main { display: flex; gap: 20px; min-width: 0; }.release-icon { align-items: center; background: rgb(var(--v-theme-primary)); border-radius: 16px; color: rgb(var(--v-theme-on-primary)); display: flex; flex: 0 0 64px; height: 64px; justify-content: center; }.release-copy { min-width: 0; }.release-version { color: rgb(var(--v-theme-primary)); font-size: .85rem; font-weight: 850; letter-spacing: .08em; }.release-copy h2 { font-size: clamp(1.45rem, 3vw, 2rem); line-height: 1.2; margin: 3px 0 8px; overflow-wrap: anywhere; }.release-copy > p { color: rgba(var(--v-theme-on-surface), .7); line-height: 1.55; margin: 0; max-width: 760px; }.release-facts { display: flex; flex-wrap: wrap; gap: 10px 18px; margin-top: 18px; }.release-facts span { align-items: center; color: rgba(var(--v-theme-on-surface), .7); display: flex; font-size: .78rem; font-weight: 650; gap: 6px; }.release-action { align-self: stretch; border-left: 1px solid rgba(var(--v-theme-primary), .15); display: flex; flex-direction: column; justify-content: center; padding-left: 28px; }.installed-version { margin-bottom: 18px; }.installed-version span { color: rgba(var(--v-theme-on-surface), .58); display: block; font-size: .72rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }.installed-version strong { display: block; font-size: 1.15rem; margin-top: 3px; overflow-wrap: anywhere; }
.control-heading { align-items: center; display: flex; gap: 14px; }.setting-label { font-size: .8rem; font-weight: 800; margin-bottom: 7px; }.notification-choices { display: grid; gap: 10px; grid-template-columns: repeat(2, minmax(0, 1fr)); }.notification-choice { align-items: center; background: transparent; border: 2px solid rgba(var(--v-theme-on-surface), .11); border-radius: 14px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: grid; gap: 10px; grid-template-columns: 38px minmax(0, 1fr) 24px; min-height: 88px; padding: 12px; text-align: left; transition: border-color .15s ease, background-color .15s ease, box-shadow .15s ease; }.notification-choice:hover, .notification-choice:focus-visible { border-color: rgba(var(--v-theme-primary), .5); outline: none; }.notification-choice.active { background: rgba(var(--v-theme-primary), .055); border-color: rgb(var(--v-theme-primary)); box-shadow: 0 0 0 2px rgba(var(--v-theme-primary), .08); }.choice-icon { align-items: center; background: rgba(var(--v-theme-primary), .1); border-radius: 10px; color: rgb(var(--v-theme-primary)); display: flex; height: 38px; justify-content: center; }.notification-choice b, .notification-choice small { display: block; }.notification-choice small { color: rgba(var(--v-theme-on-surface), .63); font-size: .7rem; line-height: 1.4; margin-top: 3px; }.choice-check { color: rgb(var(--v-theme-primary)); }.control-footer { align-items: center; border-top: 1px solid rgba(var(--v-theme-on-surface), .09); display: flex; gap: 16px; justify-content: space-between; margin-top: 18px; padding-top: 16px; }.current-choice { align-items: center; color: rgba(var(--v-theme-on-surface), .7); display: flex; font-size: .8rem; font-weight: 650; gap: 7px; }
.release-sections { display: grid; gap: 16px; grid-template-columns: repeat(2, minmax(0, 1fr)); }.release-section { border: 1px solid rgba(var(--v-theme-on-surface), .09); border-radius: 18px; overflow: hidden; }.section-heading { align-items: center; background: rgba(var(--v-theme-primary), .035); border-bottom: 1px solid rgba(var(--v-theme-on-surface), .08); display: flex; gap: 12px; padding: 18px; }.section-heading h3 { font-size: 1rem; margin: 0; }.section-heading span { color: rgba(var(--v-theme-on-surface), .57); font-size: .72rem; }.change-list { padding: 8px 18px 14px; }.change-item { align-items: flex-start; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .065); display: flex; gap: 11px; padding: 13px 0; }.change-item:last-child { border-bottom: 0; }.change-number { align-items: center; background: rgba(var(--v-theme-success), .11); border-radius: 999px; color: rgb(var(--v-theme-success)); display: flex; flex: 0 0 25px; font-size: .68rem; font-weight: 850; height: 25px; justify-content: center; }.change-item p { font-size: .84rem; line-height: 1.52; margin: 1px 0 0; overflow-wrap: anywhere; }
.empty-notes { color: rgba(var(--v-theme-on-surface), .58); display: grid; min-height: 180px; place-items: center; text-align: center; }.history-intro { align-items: center; display: flex; justify-content: space-between; }.history-intro h2 { font-size: 1.25rem; margin: 0; }.history-intro p { color: rgba(var(--v-theme-on-surface), .62); font-size: .84rem; margin: 3px 0 0; }.history-list { gap: 10px; }.history-panel { border: 1px solid rgba(var(--v-theme-on-surface), .09); border-radius: 16px !important; overflow: hidden; }.history-title { align-items: center; display: flex; gap: 13px; min-width: 0; }.history-title > div { min-width: 0; }.history-title strong { font-size: 1rem; }.history-title span, .history-title small { display: block; overflow-wrap: anywhere; }.history-title span { color: rgb(var(--v-theme-on-surface)); font-size: .86rem; font-weight: 650; margin-top: 3px; }.history-title small { color: rgba(var(--v-theme-on-surface), .58); font-size: .7rem; margin-top: 2px; }.history-summary { background: rgba(var(--v-theme-primary), .045); border-radius: 12px; color: rgba(var(--v-theme-on-surface), .72); line-height: 1.5; margin: 0 0 18px; padding: 13px 15px; }.history-sections { display: grid; gap: 18px; grid-template-columns: repeat(2, minmax(0, 1fr)); }.history-sections h3 { align-items: center; display: flex; font-size: .88rem; gap: 7px; margin: 0 0 8px; }.history-sections ul { margin: 0; padding-left: 20px; }.history-sections li { color: rgba(var(--v-theme-on-surface), .72); font-size: .79rem; line-height: 1.5; margin-bottom: 6px; overflow-wrap: anywhere; }
.announcement-head { align-items: center; display: flex; justify-content: space-between; }.announcement-head h2 { font-size: 1.3rem; margin: 0; }.announcement-head p { color: rgba(var(--v-theme-on-surface), .64); margin: 4px 0 0; }.announcement-list { display: grid; gap: 16px; }.announcement-card { border: 1px solid rgba(var(--v-theme-on-surface), .09); border-radius: 18px; padding: 20px; }.announcement-card-top { align-items: flex-start; display: flex; gap: 16px; justify-content: space-between; }.announcement-identity { align-items: center; display: flex; gap: 13px; min-width: 0; }.announcement-identity > div { min-width: 0; }.announcement-identity strong { font-size: 1rem; }.announcement-identity span, .announcement-identity small { display: block; overflow-wrap: anywhere; }.announcement-identity span { font-size: .84rem; font-weight: 650; margin-top: 3px; }.announcement-identity small { color: rgba(var(--v-theme-on-surface), .58); font-size: .7rem; margin-top: 3px; }.announcement-actions { align-items: center; display: flex; }.announcement-metrics { display: grid; gap: 10px; grid-template-columns: repeat(3, 1fr); margin: 20px 0 12px; }.announcement-metrics div { background: rgba(var(--v-theme-primary), .045); border-radius: 12px; padding: 12px; }.announcement-metrics span, .announcement-metrics small { display: block; }.announcement-metrics span { color: rgb(var(--v-theme-primary)); font-size: 1.2rem; font-weight: 850; }.announcement-metrics small { color: rgba(var(--v-theme-on-surface), .6); font-size: .68rem; margin-top: 2px; }.announced-notes { display: grid; gap: 10px; }.announced-notes > div { align-items: flex-start; display: flex; gap: 9px; }.announced-notes span { font-size: .8rem; line-height: 1.45; }.announced-notes small { color: rgb(var(--v-theme-primary)); display: block; font-size: .66rem; font-weight: 800; margin-bottom: 2px; text-transform: uppercase; }.recipient-list { display: grid; gap: 8px; }.recipient-row { align-items: center; border-bottom: 1px solid rgba(var(--v-theme-on-surface), .07); display: grid; gap: 10px; grid-template-columns: 36px minmax(0, 1fr) auto; padding: 9px 0; }.recipient-row:last-child { border-bottom: 0; }.recipient-row b, .recipient-row span { display: block; }.recipient-row b { font-size: .82rem; }.recipient-row span { color: rgba(var(--v-theme-on-surface), .58); font-size: .69rem; }.recipient-state { align-items: flex-end; display: flex; flex-direction: column; gap: 3px; }.recipient-state small { color: rgba(var(--v-theme-on-surface), .55); font-size: .65rem; }.announcement-release-summary { background: rgba(var(--v-theme-primary), .05); border-radius: 12px; margin-bottom: 16px; padding: 13px 15px; }.announcement-release-summary p { color: rgba(var(--v-theme-on-surface), .65); font-size: .8rem; margin: 3px 0 0; }.selection-toolbar { align-items: center; display: flex; justify-content: space-between; margin-bottom: 12px; }.selection-toolbar div { color: rgba(var(--v-theme-on-surface), .65); font-size: .8rem; }.selection-toolbar strong { color: rgb(var(--v-theme-primary)); }.announcement-note-groups { display: grid; gap: 14px; max-height: 46vh; overflow: auto; padding: 2px; }.announcement-note-groups section { border: 1px solid rgba(var(--v-theme-on-surface), .09); border-radius: 14px; overflow: hidden; }.announcement-note-groups h3 { background: rgba(var(--v-theme-primary), .045); font-size: .78rem; margin: 0; padding: 11px 13px; }.selectable-note { align-items: flex-start; background: transparent; border: 0; border-top: 1px solid rgba(var(--v-theme-on-surface), .065); color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: flex; gap: 10px; line-height: 1.45; min-height: 48px; padding: 12px 13px; text-align: left; width: 100%; }.selectable-note:hover, .selectable-note:focus-visible { background: rgba(var(--v-theme-primary), .035); outline: none; }.selectable-note.selected { background: rgba(var(--v-theme-primary), .07); color: rgb(var(--v-theme-primary)); }.selectable-note span { font-size: .8rem; overflow-wrap: anywhere; }
.version-step-heading { align-items: center; display: flex; gap: 12px; margin-bottom: 16px; }.step-number { align-items: center; background: rgb(var(--v-theme-primary)); border-radius: 999px; color: rgb(var(--v-theme-on-primary)); display: flex; flex: 0 0 34px; font-size: .82rem; font-weight: 850; height: 34px; justify-content: center; }.version-step-heading h3 { font-size: 1.05rem; margin: 0; }.version-step-heading p { color: rgba(var(--v-theme-on-surface), .62); font-size: .79rem; margin: 2px 0 0; }.version-picker { display: grid; gap: 10px; max-height: 58vh; overflow: auto; padding: 2px; }.version-option { align-items: center; background: rgb(var(--v-theme-surface)); border: 1px solid rgba(var(--v-theme-on-surface), .11); border-radius: 14px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: grid; gap: 12px; grid-template-columns: 44px minmax(0, 1fr) 24px; min-height: 82px; padding: 12px 14px; text-align: left; transition: border-color .15s ease, background-color .15s ease, transform .15s ease; }.version-option:hover, .version-option:focus-visible { background: rgba(var(--v-theme-primary), .045); border-color: rgba(var(--v-theme-primary), .5); outline: none; transform: translateY(-1px); }.version-option-icon { align-items: center; background: rgba(var(--v-theme-primary), .1); border-radius: 12px; color: rgb(var(--v-theme-primary)); display: flex; height: 44px; justify-content: center; }.version-option-copy b, .version-option-copy strong, .version-option-copy small { display: block; overflow-wrap: anywhere; }.version-option-copy b { color: rgb(var(--v-theme-primary)); font-size: .76rem; }.version-option-copy strong { font-size: .88rem; margin-top: 2px; }.version-option-copy small { color: rgba(var(--v-theme-on-surface), .58); font-size: .68rem; margin-top: 3px; }.selected-version-bar { align-items: center; background: rgba(var(--v-theme-primary), .055); border: 1px solid rgba(var(--v-theme-primary), .13); border-radius: 14px; display: grid; gap: 12px; grid-template-columns: 40px minmax(0, 1fr) auto; padding: 12px; }.selected-version-bar span, .selected-version-bar b { display: block; }.selected-version-bar span { color: rgba(var(--v-theme-on-surface), .58); font-size: .68rem; }.selected-version-bar b { font-size: .84rem; margin-top: 2px; overflow-wrap: anywhere; }
.announcement-metrics { grid-template-columns: repeat(4, minmax(0, 1fr)); }
@media (max-width: 960px) { .release-hero { grid-template-columns: 1fr; }.release-action { border-left: 0; border-top: 1px solid rgba(var(--v-theme-primary), .15); padding: 20px 0 0; }.release-sections { grid-template-columns: 1fr; }.notification-choices { grid-template-columns: 1fr; } }
@media (max-width: 600px) { .release-hero { padding: 18px; }.release-hero-main { flex-direction: column; }.release-icon { flex-basis: 54px; height: 54px; width: 54px; }.release-facts { flex-direction: column; }.control-heading { align-items: flex-start; }.control-footer { align-items: stretch; flex-direction: column; }.history-intro, .announcement-head { align-items: flex-start; flex-direction: column; gap: 12px; }.history-sections { grid-template-columns: 1fr; }.notification-choice { min-height: 96px; }.announcement-card-top { align-items: stretch; flex-direction: column; }.announcement-actions { justify-content: flex-end; }.announcement-metrics { grid-template-columns: 1fr; }.recipient-row { grid-template-columns: 36px minmax(0, 1fr); }.recipient-state { align-items: flex-start; grid-column: 2; }.selection-toolbar { align-items: flex-start; flex-direction: column; gap: 9px; } }
</style>
