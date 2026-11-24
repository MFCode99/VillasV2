<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import QRCode from 'qrcode'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'

const route = useRoute(), router = useRouter(), auth = useAuthStore(), feedback = useFeedbackStore()
const data = ref(null), form = reactive({}), saving = ref(false), password = ref(''), showPassword = ref(false)
const sendingAccess = ref(false), sendingPdf = ref(''), inviteDurationDialog = ref(false), accessDialog = ref(false), accessData = ref(null), sharingAccess = ref(false), qrDataUrl = ref('')
const inviteHours = ref(1)
const activityTab = ref('carts'), documentSearch = ref(''), documentKind = ref('all')
let inviteStatusTimer, activityTimer

const inviteStatusMeta = {
  valid: { label: 'Válido', color: 'success', icon: 'mdi-link-variant' },
  used: { label: 'Utilizado', color: 'info', icon: 'mdi-check-circle-outline' },
  expired: { label: 'Expirado ou substituído', color: 'warning', icon: 'mdi-clock-alert-outline' },
}
const inviteDurationOptions = [
  { title: '1 hora', value: 1 },
  { title: '6 horas', value: 6 },
  { title: '12 horas', value: 12 },
  { title: '24 horas', value: 24 },
  { title: '3 dias', value: 72 },
  { title: '7 dias', value: 168 },
  { title: '14 dias', value: 336 },
  { title: '30 dias', value: 720 },
]
const filteredDocuments = computed(() => {
  const query = documentSearch.value.trim().toLocaleLowerCase('pt-PT')
  return (data.value?.activity?.documents || []).filter(document => {
    if (documentKind.value !== 'all' && document.kind !== documentKind.value) return false
    return !query || [document.publicNumber, document.catalogLabel, document.label, document.orderStatusLabel].some(value => String(value || '').toLocaleLowerCase('pt-PT').includes(query))
  })
})
const latestOrder = computed(() => data.value?.orders?.[0] || null)
const money = value => `${Number(value || 0).toFixed(2).replace('.', ',')} €`
const formatDate = value => value ? new Date(value).toLocaleString('pt-PT') : '—'
const inviteMeta = status => inviteStatusMeta[status] || inviteStatusMeta.expired
const inviteDurationLabel = hours => {
  const value = Number(hours || 1)
  if (value < 24) return `${value} ${value === 1 ? 'hora' : 'horas'}`
  const days = value / 24
  return `${days} ${days === 1 ? 'dia' : 'dias'}`
}
const accessValidityLabel = computed(() => inviteDurationLabel(Number(accessData.value?.expiresInSeconds || 3600) / 3600))
const orderStatusColor = status => status === 'pending' ? 'warning' : status === 'confirmed' ? 'success' : 'info'
const cartProgress = cart => Math.min(100, Number(cart.minimum_total) > 0 ? (Number(cart.total) / Number(cart.minimum_total)) * 100 : 100)

async function load() {
  try {
    data.value = (await api.get(`/admin/users/${route.params.id}`)).data
    const user = data.value.user
    Object.assign(form, {
      full_name: user.fullName, email: user.email, additional_emails: [...(user.additionalEmails || [])], nif: user.nif,
      company_name: user.companyName, phone: user.phone, address_line1: user.addressLine1, address_line2: user.addressLine2,
      postal_code: user.postalCode, city: user.city, country: user.country, delivery_same_as_billing: user.deliverySameAsBilling,
      delivery_address_line1: user.deliveryAddressLine1, delivery_address_line2: user.deliveryAddressLine2,
      delivery_postal_code: user.deliveryPostalCode, delivery_city: user.deliveryCity, delivery_country: user.deliveryCountry,
      carrier: user.carrier, role: user.role, active: user.active, admin_notes: user.adminNotes, catalogs: [...(user.catalogs || [])],
    })
    activityTab.value = data.value.activity?.carts?.length ? 'carts' : 'documents'
  } catch (error) { feedback.show(errorMessage(error), 'error') }
}
async function refreshInviteStatus() { if (data.value) try { data.value.accessInvite = (await api.get(`/admin/users/${route.params.id}/access-invite-status`)).data.accessInvite } catch { /* background */ } }
async function refreshActivity() { if (data.value) try { data.value.activity = (await api.get(`/admin/users/${route.params.id}/commercial-activity`)).data.activity } catch { /* background */ } }
async function save() { saving.value = true; try { await api.put(`/admin/users/${route.params.id}`, form); await load(); feedback.show('Alterações guardadas.') } catch (error) { feedback.show(errorMessage(error), 'error') } finally { saving.value = false } }
async function resetPassword() { try { await api.put(`/admin/users/${route.params.id}/password`, { password: password.value }); password.value = ''; feedback.show('Password atualizada e sessões antigas terminadas.') } catch (error) { feedback.show(errorMessage(error), 'error') } }
async function resendAccess() { if (!await feedback.confirm('Será criada uma nova password e enviada para o email deste utilizador. A password atual deixará de funcionar.', 'Reenviar acesso')) return; sendingAccess.value = true; try { await api.post(`/admin/users/${route.params.id}/welcome-email`); feedback.show('Nova password enviada por email.') } catch (error) { feedback.show(errorMessage(error), 'error') } finally { sendingAccess.value = false } }
async function generateWhatsAppAccess() { sendingAccess.value = true; try { accessData.value = (await api.post(`/admin/users/${route.params.id}/access-invite`, { expires_in_hours: inviteHours.value })).data.invite; data.value.accessInvite = { id: null, status: accessData.value.status, createdAt: accessData.value.createdAt, expiresAt: accessData.value.expiresAt, usedAt: null }; qrDataUrl.value = await QRCode.toDataURL(accessData.value.url, { width: 360, margin: 2, color: { dark: '#17243D', light: '#FFFFFF' } }); inviteDurationDialog.value = false; accessDialog.value = true } catch (error) { feedback.show(errorMessage(error), 'error') } finally { sendingAccess.value = false } }
function accessText() { const invite = accessData.value; return `Olá ${invite.fullName},\n\nuse este link pessoal para criar o seu acesso ao portal Vitor Gouveia:\n${invite.url}\n\nO link só pode ser utilizado uma vez e expira em ${accessValidityLabel.value}.` }
async function copyInviteLink() { try { await navigator.clipboard.writeText(accessData.value.url); feedback.show('Link copiado.') } catch { feedback.show('Não foi possível copiar o link.', 'error') } }
function downloadQr() { const link = document.createElement('a'); link.href = qrDataUrl.value; link.download = `convite-${accessData.value.username}.png`; link.click() }
async function shareWhatsApp() { sharingAccess.value = true; const text = accessText(); try { if (navigator.share) { try { await navigator.share({ title: 'Convite Vitor Gouveia', text, url: accessData.value.url }); feedback.show('Convite preparado para partilhar.'); return } catch (error) { if (error?.name === 'AbortError') return } } window.location.href = `https://wa.me/?text=${encodeURIComponent(text)}` } finally { sharingAccess.value = false } }
async function sendDocumentPdf(document) { const recipients = [data.value.user.email, ...(data.value.user.additionalEmails || [])].filter(Boolean).join(', '); if (!await feedback.confirm(`Enviar o PDF ${document.label.toLocaleLowerCase('pt-PT')} da encomenda ${document.publicNumber} para ${recipients || 'os emails deste utilizador'}?`, 'Enviar PDF')) return; sendingPdf.value = document.id; try { await api.post(`/admin/users/${route.params.id}/orders/${document.publicNumber}/email-pdf`, { hide_prices: document.kind === 'no_prices' }); await refreshActivity(); feedback.show(`PDF ${document.label.toLocaleLowerCase('pt-PT')} enviado por email.`) } catch (error) { feedback.show(errorMessage(error), 'error') } finally { sendingPdf.value = '' } }
async function remove() { if (!await feedback.confirm('Esta operação é definitiva. Eliminar este utilizador?', 'Eliminar utilizador')) return; try { await api.delete(`/admin/users/${route.params.id}`); feedback.show('Utilizador eliminado.'); router.push('/admin/utilizadores') } catch (error) { feedback.show(errorMessage(error), 'error') } }

onMounted(async () => { await load(); inviteStatusTimer = setInterval(refreshInviteStatus, 15000); activityTimer = setInterval(refreshActivity, 30000) })
onUnmounted(() => { clearInterval(inviteStatusTimer); clearInterval(activityTimer) })
</script>

<template>
  <div class="page">
    <v-btn to="/admin/utilizadores" variant="text" prepend-icon="mdi-arrow-left" class="mb-4">Voltar aos utilizadores</v-btn>
    <v-skeleton-loader v-if="!data" type="article, article, table" />
    <template v-else>
      <div class="page-head"><div><h1>{{ data.user.fullName }}</h1><p>@{{ data.user.username }} · {{ data.user.companyName || 'Sem empresa' }}</p></div><v-chip size="large" :color="form.active ? 'success' : 'grey'">{{ form.active ? 'Ativo' : 'Inativo' }}</v-chip></div>

      <div class="customer-metrics mb-5">
        <div class="customer-metric"><v-icon color="primary">mdi-receipt-text-outline</v-icon><span>Encomendas</span><b>{{ data.activity.summary.orders }}</b></div>
        <div class="customer-metric"><v-icon color="success">mdi-cash-multiple</v-icon><span>Valor encomendado</span><b>{{ money(data.activity.summary.orderValue) }}</b></div>
        <div class="customer-metric" :class="{ 'metric-attention': data.activity.summary.pendingCarts }"><v-icon :color="data.activity.summary.pendingCarts ? 'warning' : 'grey'">mdi-cart-outline</v-icon><span>Carrinhos pendentes</span><b>{{ data.activity.summary.pendingCarts }}</b></div>
        <div class="customer-metric"><v-icon color="secondary">mdi-file-pdf-box</v-icon><span>PDFs disponíveis</span><b>{{ data.activity.summary.documents }}</b></div>
      </div>

      <v-card class="soft-card commercial-card mb-5">
        <div class="commercial-head"><div><div class="text-h6 font-weight-bold">Atividade comercial</div><div class="text-body-2 text-medium-emphasis">Carrinhos, encomendas e documentos deste cliente.</div></div><div class="d-flex align-center ga-2"><v-btn v-if="latestOrder" :to="{path:`/admin/encomendas/${latestOrder.publicNumber}`,query:{editPdf:'1'}}" color="secondary" variant="tonal" prepend-icon="mdi-file-edit-outline">Editar PDFs do cliente</v-btn><v-btn icon="mdi-refresh" variant="text" aria-label="Atualizar atividade comercial" @click="refreshActivity" /></div></div>
        <v-tabs v-model="activityTab" color="primary" class="activity-tabs"><v-tab value="carts"><v-icon start>mdi-cart-outline</v-icon>Carrinhos<v-badge v-if="data.activity.carts.length" inline color="warning" :content="data.activity.carts.length" /></v-tab><v-tab value="documents"><v-icon start>mdi-file-pdf-box</v-icon>PDFs <span class="tab-count">{{ data.activity.documents.length }}</span></v-tab><v-tab value="orders"><v-icon start>mdi-receipt-text-outline</v-icon>Encomendas <span class="tab-count">{{ data.orders.length }}</span></v-tab></v-tabs>
        <v-divider />
        <v-window v-model="activityTab">
          <v-window-item value="carts" class="activity-panel">
            <v-alert v-if="!data.activity.carts.length" type="success" variant="tonal" title="Sem carrinhos pendentes">Este cliente não tem artigos guardados no carrinho.</v-alert>
            <v-row v-else><v-col v-for="cart in data.activity.carts" :key="cart.catalog_slug" cols="12" md="6"><v-card variant="outlined" class="cart-watch-card h-100"><div class="cart-watch-head"><div class="d-flex align-center ga-3"><v-avatar color="warning" variant="tonal"><v-icon>{{ cart.catalogIcon }}</v-icon></v-avatar><div><b>{{ cart.catalogLabel }}</b><div class="text-caption text-medium-emphasis">Alterado em {{ formatDate(cart.updatedAt) }}</div></div></div><v-chip color="warning" size="small" variant="tonal">Pendente</v-chip></div><div class="cart-watch-total"><div><span>Valor no carrinho</span><b>{{ money(cart.total) }}</b></div><div><span>Artigos</span><b>{{ cart.lines }} linhas · {{ cart.units }} un.</b></div></div><div class="px-4 pb-3"><div class="d-flex justify-space-between text-caption mb-1"><span>Mínimo {{ money(cart.minimum_total) }}</span><b v-if="!cart.minimumReached" class="text-warning">Faltam {{ money(cart.missingToMinimum) }}</b><b v-else class="text-success">Mínimo atingido</b></div><v-progress-linear :model-value="cartProgress(cart)" :color="cart.minimumReached ? 'success' : 'warning'" height="8" rounded /></div><v-expansion-panels variant="accordion" class="cart-items-panel"><v-expansion-panel><v-expansion-panel-title>Ver {{ cart.lines }} {{ cart.lines === 1 ? 'artigo' : 'artigos' }}</v-expansion-panel-title><v-expansion-panel-text><v-list density="compact"><v-list-item v-for="item in cart.items" :key="item.id" :title="`${item.ref} · ${item.name}`" :subtitle="[item.color,item.size].filter(Boolean).join(' · ') || 'Sem variante'"><template #append><div class="text-right"><b>{{ item.quantity }} un.</b><div class="text-caption">{{ money(item.line_total) }}</div></div></template></v-list-item></v-list></v-expansion-panel-text></v-expansion-panel></v-expansion-panels></v-card></v-col></v-row>
          </v-window-item>

          <v-window-item value="documents" class="activity-panel">
            <div class="document-toolbar"><v-text-field v-model="documentSearch" label="Procurar PDF ou encomenda" prepend-inner-icon="mdi-magnify" clearable hide-details /><v-select v-model="documentKind" label="Tipo de PDF" :items="[{title:'Todos',value:'all'},{title:'Com preços',value:'priced'},{title:'Sem preços',value:'no_prices'}]" hide-details /></div>
            <div v-if="filteredDocuments.length" class="document-list"><div v-for="document in filteredDocuments" :key="document.id" class="document-row"><div class="document-icon"><v-icon color="error" size="28">mdi-file-pdf-box</v-icon></div><div class="document-main"><div class="d-flex flex-wrap align-center ga-2"><router-link :to="`/admin/encomendas/${document.publicNumber}`" class="document-title">{{ document.publicNumber }}</router-link><v-chip size="x-small" :color="document.kind === 'priced' ? 'primary' : 'secondary'" variant="tonal">{{ document.label }}</v-chip><v-chip size="x-small" :color="orderStatusColor(document.orderStatus)" variant="tonal">{{ document.orderStatusLabel }}</v-chip></div><div class="text-caption text-medium-emphasis">{{ document.catalogLabel }} · {{ formatDate(document.createdAt) }} · {{ money(document.total) }}</div><div v-if="document.lastSentAt" class="text-caption text-success"><v-icon size="14">mdi-email-check-outline</v-icon> Enviado em {{ formatDate(document.lastSentAt) }}<span v-if="document.lastRecipient"> para {{ document.lastRecipient }}</span></div><div v-else class="text-caption text-medium-emphasis">Ainda não foi enviado diretamente pela ficha do cliente.</div></div><div class="document-actions"><v-tooltip text="Abrir PDF"><template #activator="{ props }"><v-btn v-bind="props" :href="document.viewUrl" target="_blank" icon="mdi-open-in-new" variant="tonal" color="primary" aria-label="Abrir PDF" /></template></v-tooltip><v-tooltip text="Descarregar PDF"><template #activator="{ props }"><v-btn v-bind="props" :href="document.downloadUrl" icon="mdi-download" variant="tonal" aria-label="Descarregar PDF" /></template></v-tooltip><v-tooltip text="Enviar por email"><template #activator="{ props }"><v-btn v-bind="props" icon="mdi-email-fast-outline" variant="tonal" color="success" aria-label="Enviar PDF por email" :loading="sendingPdf === document.id" @click="sendDocumentPdf(document)" /></template></v-tooltip></div></div></div>
            <div v-else class="empty-state">Não existem PDFs com estes filtros.</div>
          </v-window-item>

          <v-window-item value="orders" class="activity-panel pa-0"><v-list v-if="data.orders.length" lines="two"><v-list-item v-for="order in data.orders" :key="order.id" :to="`/admin/encomendas/${order.publicNumber}`" :title="order.publicNumber" :subtitle="`${order.catalogLabel} · ${formatDate(order.createdAt)} · ${money(order.total)}`"><template #prepend><v-avatar :color="orderStatusColor(order.orderStatus)" variant="tonal"><v-icon>mdi-receipt-text-outline</v-icon></v-avatar></template><template #append><v-chip :color="orderStatusColor(order.orderStatus)" size="small" variant="tonal">{{ order.orderStatusLabel }}</v-chip><v-icon class="ml-2">mdi-chevron-right</v-icon></template></v-list-item></v-list><div v-else class="empty-state">Sem encomendas.</div></v-window-item>
        </v-window>
      </v-card>

      <v-row><v-col cols="12" lg="8"><v-card class="soft-card pa-6"><div class="text-h6 font-weight-bold mb-5">Dados do utilizador</div><v-row density="compact">
        <v-col cols="12" md="6"><v-text-field v-model="form.full_name" label="Nome completo" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.company_name" label="Empresa" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.email" type="email" label="Email principal" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.phone" label="Telefone" /></v-col><v-col cols="12"><v-combobox v-model="form.additional_emails" multiple chips closable-chips type="email" label="Emails adicionais para encomendas" hint="As notas de encomenda serão enviadas para todos estes endereços." persistent-hint /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.nif" label="NIF" /></v-col><v-col cols="12" md="6"><v-select v-model="form.role" label="Tipo" :items="[{title:'Cliente',value:'client'},{title:'Administrador',value:'admin'},{title:'Developer legado',value:'developer'}]" /></v-col><v-col cols="12"><v-select v-model="form.catalogs" :items="data.catalogs" item-title="label" item-value="slug" multiple chips closable-chips label="Catálogos visíveis para este utilizador" prepend-inner-icon="mdi-bookshelf" /></v-col><v-col cols="12"><v-text-field v-model="form.carrier" label="Transportadora / Transitário" hint="Aparece no detalhe e nas notas de encomenda." persistent-hint prepend-inner-icon="mdi-truck-outline" /></v-col><v-col cols="12"><div class="text-subtitle-2 font-weight-bold mt-3">Morada</div></v-col><v-col cols="12"><v-text-field v-model="form.address_line1" label="Morada" /></v-col><v-col cols="12"><v-text-field v-model="form.address_line2" label="Complemento da morada" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.postal_code" label="Código postal" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.city" label="Localidade" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.country" label="País" /></v-col><v-col cols="12"><v-switch v-model="form.delivery_same_as_billing" color="primary" label="Morada de entrega igual à morada" hide-details /></v-col><template v-if="!form.delivery_same_as_billing"><v-col cols="12"><div class="text-subtitle-2 font-weight-bold mt-3">Morada de entrega</div></v-col><v-col cols="12"><v-text-field v-model="form.delivery_address_line1" label="Morada de entrega" /></v-col><v-col cols="12"><v-text-field v-model="form.delivery_address_line2" label="Complemento da morada de entrega" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_postal_code" label="Código postal" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_city" label="Localidade" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_country" label="País" /></v-col></template><v-col cols="12"><v-textarea v-model="form.admin_notes" label="Notas internas do administrador" rows="4" /></v-col><v-col cols="12"><v-switch v-model="form.active" color="success" label="Utilizador ativo" /></v-col>
      </v-row><div class="d-flex justify-end"><v-btn color="primary" :loading="saving" @click="save">Guardar alterações</v-btn></div></v-card></v-col>
      <v-col cols="12" lg="4"><v-card class="soft-card pa-5 mb-5"><div class="text-h6 font-weight-bold mb-4">Acesso ao portal</div><v-text-field v-model="password" label="Nova password" :type="showPassword ? 'text' : 'password'" :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'" hint="Mínimo de 8 caracteres" persistent-hint @click:append-inner="showPassword = !showPassword" /><v-btn block variant="tonal" color="primary" class="mt-4" @click="resetPassword">Atualizar password</v-btn><v-btn block variant="tonal" color="secondary" class="mt-2" prepend-icon="mdi-email-fast-outline" :loading="sendingAccess" :disabled="!data.user.email" @click="resendAccess">Reenviar por email</v-btn><v-btn block variant="tonal" color="success" class="mt-2" prepend-icon="mdi-whatsapp" :loading="sendingAccess" @click="inviteDurationDialog = true">Convite por WhatsApp</v-btn><div v-if="!data.user.email" class="text-caption text-error mt-2">Este utilizador não tem email definido.</div><v-divider class="my-5"/><div class="d-flex align-center justify-space-between ga-3 mb-2"><div class="text-subtitle-2 font-weight-bold">Último convite</div><v-chip v-if="data.accessInvite" :color="inviteMeta(data.accessInvite.status).color" :prepend-icon="inviteMeta(data.accessInvite.status).icon" size="small" variant="tonal">{{ inviteMeta(data.accessInvite.status).label }}</v-chip><v-chip v-else size="small" color="grey" variant="tonal">Nunca gerado</v-chip></div><div v-if="data.accessInvite" class="invite-status-details"><span>Gerado em <b>{{ formatDate(data.accessInvite.createdAt) }}</b></span><span v-if="data.accessInvite.status === 'used'">Utilizado em <b>{{ formatDate(data.accessInvite.usedAt) }}</b></span><span v-else-if="data.accessInvite.status === 'valid'">Expira em <b>{{ formatDate(data.accessInvite.expiresAt) }}</b></span><span v-else>Expirou em <b>{{ formatDate(data.accessInvite.expiresAt) }}</b></span></div><p v-else class="text-body-2 text-medium-emphasis mb-0">Ainda não foi criado nenhum convite por WhatsApp.</p></v-card><v-card class="soft-card pa-5"><div class="text-h6 font-weight-bold mb-2">Zona sensível</div><p class="text-body-2 text-medium-emphasis mb-4">Só é possível eliminar utilizadores sem histórico.</p><v-btn block color="error" variant="tonal" :disabled="Number(route.params.id) === auth.user.id" @click="remove">Eliminar utilizador</v-btn></v-card></v-col></v-row>

      <v-dialog v-model="accessDialog" max-width="620"><v-card class="invite-dialog"><v-card-title class="d-flex align-center justify-space-between pa-6 pb-2"><div><div class="text-h5 font-weight-bold">Convite de acesso</div><div class="text-body-2 text-medium-emphasis">Válido por {{ accessValidityLabel }} e apenas para este utilizador.</div></div><v-btn icon="mdi-close" variant="text" aria-label="Fechar" @click="accessDialog = false" /></v-card-title><v-card-text class="pa-6"><v-alert type="info" variant="tonal" class="mb-5">O utilizador abre o link ou lê o QR Code e escolhe a própria password. A password atual não é alterada até o convite ser utilizado.</v-alert><div v-if="accessData" class="invite-share"><div class="invite-qr"><img v-if="qrDataUrl" :src="qrDataUrl" alt="QR Code do convite de acesso" width="220" height="220" /><v-btn size="small" variant="text" prepend-icon="mdi-download" @click="downloadQr">Descarregar QR</v-btn></div><div class="access-summary"><div><span>Utilizador</span><b>{{ accessData.username }}</b></div><div><span>Validade</span><b>{{ accessValidityLabel }} · utilização única</b></div><div><span>Link pessoal</span><b>{{ accessData.url }}</b></div><v-btn block variant="tonal" prepend-icon="mdi-content-copy" @click="copyInviteLink">Copiar link</v-btn></div></div></v-card-text><v-card-actions class="px-6 pb-6"><v-btn variant="text" @click="accessDialog = false">Fechar</v-btn><v-spacer/><v-btn color="success" prepend-icon="mdi-whatsapp" :loading="sharingAccess" @click="shareWhatsApp">Partilhar no WhatsApp</v-btn></v-card-actions></v-card></v-dialog>
    </template>

    <v-dialog v-model="inviteDurationDialog" max-width="480">
      <v-card>
        <v-card-title class="d-flex align-center justify-space-between pa-6 pb-2">
          <div>
            <div class="text-h5 font-weight-bold">Gerar convite</div>
            <div class="text-body-2 text-medium-emphasis">Escolha durante quanto tempo o link fica disponível.</div>
          </div>
          <v-btn icon="mdi-close" variant="text" aria-label="Fechar" @click="inviteDurationDialog = false" />
        </v-card-title>
        <v-card-text class="pa-6">
          <v-select v-model="inviteHours" :items="inviteDurationOptions" label="Validade do link" prepend-inner-icon="mdi-clock-outline" hide-details />
          <v-alert type="info" variant="tonal" density="compact" class="mt-4">O link é pessoal e só pode ser utilizado uma vez. Ao gerar, qualquer convite anterior deste utilizador deixa de funcionar.</v-alert>
        </v-card-text>
        <v-card-actions class="px-6 pb-6">
          <v-spacer />
          <v-btn variant="text" @click="inviteDurationDialog = false">Cancelar</v-btn>
          <v-btn color="success" prepend-icon="mdi-link-plus" :loading="sendingAccess" @click="generateWhatsAppAccess">Gerar convite</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.customer-metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.customer-metric{display:grid;grid-template-columns:auto 1fr;grid-template-rows:auto auto;column-gap:12px;padding:16px 18px;border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:16px;background:rgb(var(--v-theme-surface));box-shadow:0 5px 18px rgba(23,36,61,.05)}.customer-metric .v-icon{grid-row:1/3;align-self:center}.customer-metric span{font-size:.75rem;color:rgba(var(--v-theme-on-surface),.62)}.customer-metric b{font-size:1.12rem;color:rgb(var(--v-theme-primary));font-variant-numeric:tabular-nums}.customer-metric.metric-attention{border-color:rgba(var(--v-theme-warning),.4);background:rgba(var(--v-theme-warning),.04)}
.commercial-card{overflow:hidden}.commercial-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:20px 22px 10px}.activity-tabs{padding-inline:10px}.tab-count{margin-left:7px;color:rgba(var(--v-theme-on-surface),.62);font-size:.75rem}.activity-panel{padding:20px 22px;min-height:180px}.cart-watch-card{overflow:hidden;border-radius:16px!important}.cart-watch-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:16px}.cart-watch-total{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:0 16px 14px}.cart-watch-total>div{display:grid;gap:2px;padding:10px 12px;border-radius:12px;background:rgba(var(--v-theme-primary),.04)}.cart-watch-total span{font-size:.72rem;color:rgba(var(--v-theme-on-surface),.6)}.cart-watch-total b{font-variant-numeric:tabular-nums}.cart-items-panel{border-top:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.cart-items-panel :deep(.v-expansion-panel){box-shadow:none!important}.cart-items-panel :deep(.v-expansion-panel-title){min-height:48px}
.document-toolbar{display:grid;grid-template-columns:minmax(240px,1fr) 220px;gap:12px;margin-bottom:16px}.document-list{display:grid}.document-row{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:14px;padding:14px 4px;border-bottom:1px solid rgba(var(--v-border-color),var(--v-border-opacity))}.document-row:last-child{border-bottom:0}.document-icon{width:48px;height:48px;display:grid;place-items:center;border-radius:14px;background:rgba(var(--v-theme-error),.08)}.document-main{min-width:0}.document-title{color:rgb(var(--v-theme-primary));font-weight:800;text-decoration:none}.document-title:hover{text-decoration:underline}.document-actions{display:flex;gap:8px}.document-actions .v-btn{min-width:44px;min-height:44px}
.access-summary{display:grid;gap:10px;min-width:0;flex:1}.access-summary>div{background:rgba(var(--v-theme-primary),.05);border-radius:12px;display:flex;flex-direction:column;padding:12px 14px}.access-summary span{color:rgba(var(--v-theme-on-surface),.62);font-size:.75rem;text-transform:uppercase}.access-summary b{overflow-wrap:anywhere}.invite-share{display:flex;align-items:center;gap:22px}.invite-qr{display:flex;flex-direction:column;align-items:center;gap:4px}.invite-qr img{display:block;max-width:100%;height:auto;border:1px solid rgba(var(--v-border-color),var(--v-border-opacity));border-radius:16px}.invite-status-details{display:grid;gap:5px;color:rgba(var(--v-theme-on-surface),.68);font-size:.82rem}.invite-status-details span{display:flex;justify-content:space-between;gap:12px}.invite-status-details b{text-align:right;color:rgba(var(--v-theme-on-surface),.9)}
@media(max-width:959px){.customer-metrics{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:599px){.customer-metrics{gap:8px}.customer-metric{padding:12px;column-gap:8px}.customer-metric b{font-size:.96rem}.commercial-head{align-items:flex-start;flex-direction:column;padding:17px 16px 8px}.commercial-head>div:last-child{width:100%}.commercial-head>div:last-child .v-btn:first-child{flex:1}.activity-tabs{padding-inline:0}.activity-tabs :deep(.v-tab){min-width:0;padding-inline:10px;font-size:.78rem}.activity-tabs :deep(.v-tab .v-icon){display:none}.activity-panel{padding:14px}.cart-watch-total{grid-template-columns:1fr}.document-toolbar{grid-template-columns:1fr}.document-row{grid-template-columns:auto minmax(0,1fr);gap:10px}.document-icon{width:42px;height:42px}.document-actions{grid-column:1/-1;justify-content:flex-end}.invite-share{flex-direction:column}.invite-qr img{width:190px}.invite-dialog .v-card-actions{flex-wrap:wrap}.invite-dialog .v-card-actions .v-btn:last-child{width:100%;margin-top:6px}.invite-status-details span{display:grid;gap:1px}.invite-status-details b{text-align:left}}
</style>
