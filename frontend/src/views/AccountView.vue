<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'

const auth = useAuthStore()
const feedback = useFeedbackStore()
const loading = ref(true)
const saving = ref(false)
const savingPassword = ref(false)
const showPasswords = ref(false)
const form = reactive({
  full_name: '', email: '', additional_emails: [], phone: '', nif: '', company_name: '', carrier: '',
  address_line1: '', address_line2: '', postal_code: '', city: '', country: '', delivery_same_as_billing: true,
  delivery_address_line1: '', delivery_address_line2: '', delivery_postal_code: '', delivery_city: '', delivery_country: '',
})
const password = reactive({ current_password: '', new_password: '', confirmation: '' })
const passwordReady = computed(() => password.current_password && password.new_password.length >= 8 && password.new_password === password.confirmation)

function populate(user) {
  Object.assign(form, {
    full_name: user.fullName || '', email: user.email || '', additional_emails: [...(user.additionalEmails || [])],
    phone: user.phone || '', nif: user.nif || '', company_name: user.companyName || '', carrier: user.carrier || '',
    address_line1: user.addressLine1 || '', address_line2: user.addressLine2 || '', postal_code: user.postalCode || '', city: user.city || '', country: user.country || '',
    delivery_same_as_billing: Boolean(user.deliverySameAsBilling), delivery_address_line1: user.deliveryAddressLine1 || '',
    delivery_address_line2: user.deliveryAddressLine2 || '', delivery_postal_code: user.deliveryPostalCode || '', delivery_city: user.deliveryCity || '', delivery_country: user.deliveryCountry || '',
  })
}
async function load() {
  loading.value = true
  try { populate((await api.get('/account')).data.user) }
  catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}
async function save() {
  saving.value = true
  try {
    const payload = { ...form, email: form.email.trim() || null, additional_emails: form.additional_emails.filter(Boolean) }
    const user = (await api.put('/account', payload)).data.user
    auth.user = { ...auth.user, ...user }
    populate(user)
    feedback.show('Os seus dados foram atualizados.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { saving.value = false }
}
async function changePassword() {
  if (!passwordReady.value) return
  savingPassword.value = true
  try {
    await api.put('/account/password', password)
    Object.assign(password, { current_password: '', new_password: '', confirmation: '' })
    feedback.show('Password alterada. As outras sessões foram terminadas.')
  } catch (error) { feedback.show(errorMessage(error), 'error') }
  finally { savingPassword.value = false }
}
onMounted(load)
</script>

<template>
  <div class="page account-page">
    <div class="page-head"><div><h1>A minha conta</h1><p>Contactos, moradas e segurança da sua conta.</p></div><v-btn color="primary" prepend-icon="mdi-content-save-outline" :loading="saving" :disabled="loading" @click="save">Guardar alterações</v-btn></div>
    <v-progress-linear v-if="loading" indeterminate color="secondary" />
    <div v-else class="account-grid">
      <div class="account-main">
        <v-card class="soft-card pa-5">
          <div class="section-title"><v-icon color="primary">mdi-account-outline</v-icon><div><h2>Dados principais</h2><p>Informação utilizada nas encomendas e comunicações.</p></div></div>
          <v-row><v-col cols="12" md="6"><v-text-field v-model="form.full_name" label="Nome completo" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.company_name" label="Empresa" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.email" type="email" label="Email principal" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.phone" label="Telefone" /></v-col><v-col cols="12"><v-combobox v-model="form.additional_emails" multiple chips closable-chips type="email" label="Emails adicionais" hint="Também recebem as comunicações das encomendas." persistent-hint /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.nif" label="NIF" /></v-col><v-col cols="12" md="6"><v-text-field v-model="form.carrier" label="Transportadora / Transitário" prepend-inner-icon="mdi-truck-outline" /></v-col></v-row>
        </v-card>
        <v-card class="soft-card pa-5">
          <div class="section-title"><v-icon color="primary">mdi-map-marker-outline</v-icon><div><h2>Moradas</h2><p>Morada de faturação e local habitual de entrega.</p></div></div>
          <v-row><v-col cols="12"><v-text-field v-model="form.address_line1" label="Morada" /></v-col><v-col cols="12"><v-text-field v-model="form.address_line2" label="Complemento" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.postal_code" label="Código postal" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.city" label="Localidade" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.country" label="País" /></v-col><v-col cols="12"><v-switch v-model="form.delivery_same_as_billing" color="primary" label="Morada de entrega igual à morada acima" hide-details /></v-col><template v-if="!form.delivery_same_as_billing"><v-col cols="12"><v-divider class="my-1" /></v-col><v-col cols="12"><v-text-field v-model="form.delivery_address_line1" label="Morada de entrega" /></v-col><v-col cols="12"><v-text-field v-model="form.delivery_address_line2" label="Complemento da entrega" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_postal_code" label="Código postal" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_city" label="Localidade" /></v-col><v-col cols="12" md="4"><v-text-field v-model="form.delivery_country" label="País" /></v-col></template></v-row>
        </v-card>
      </div>
      <aside>
        <v-card class="soft-card pa-5 password-card">
          <div class="section-title"><v-icon color="secondary">mdi-lock-outline</v-icon><div><h2>Alterar password</h2><p>As restantes sessões serão terminadas.</p></div></div>
          <v-text-field v-model="password.current_password" label="Password atual" :type="showPasswords ? 'text' : 'password'" autocomplete="current-password" />
          <v-text-field v-model="password.new_password" label="Nova password" :type="showPasswords ? 'text' : 'password'" autocomplete="new-password" hint="Mínimo de 8 caracteres" persistent-hint />
          <v-text-field v-model="password.confirmation" label="Confirmar nova password" :type="showPasswords ? 'text' : 'password'" autocomplete="new-password" :error="Boolean(password.confirmation && password.new_password !== password.confirmation)" />
          <v-checkbox v-model="showPasswords" label="Mostrar passwords" hide-details density="compact" />
          <v-btn block color="secondary" variant="tonal" class="mt-4" :disabled="!passwordReady" :loading="savingPassword" @click="changePassword">Alterar password</v-btn>
        </v-card>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.account-grid{align-items:start;display:grid;gap:22px;grid-template-columns:minmax(0,1fr) 360px}.account-main{display:grid;gap:22px}.section-title{align-items:flex-start;display:flex;gap:12px;margin-bottom:20px}.section-title h2{font-size:1.05rem;margin:0}.section-title p{color:rgba(var(--v-theme-on-surface),.6);font-size:.76rem;margin:3px 0 0}.password-card{position:sticky;top:88px}@media(max-width:980px){.account-grid{grid-template-columns:1fr}.password-card{position:static}}
</style>
