<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../services/api'

const router = useRouter()
const token = ref('')
const invite = ref(null)
const password = ref('')
const confirmation = ref('')
const showPassword = ref(false)
const loading = ref(true)
const saving = ref(false)
const error = ref('')
const complete = ref(false)
const canSubmit = computed(() => password.value.length >= 8 && password.value === confirmation.value)

async function inspect() {
  const params = new URLSearchParams(window.location.search)
  const incomingToken = params.get('token') || decodeURIComponent(window.location.hash.slice(1))
  if (incomingToken) {
    sessionStorage.setItem('villas_access_invite', incomingToken)
    history.replaceState(null, '', '/convite')
  }
  token.value = incomingToken || sessionStorage.getItem('villas_access_invite') || ''
  if (!token.value) {
    error.value = 'Este convite não é válido.'
    loading.value = false
    return
  }
  try {
    invite.value = (await api.post('/access-invite/inspect', { token: token.value })).data.invite
  } catch (requestError) {
    error.value = errorMessage(requestError)
  } finally {
    loading.value = false
  }
}

async function activate() {
  if (!canSubmit.value) return
  saving.value = true
  error.value = ''
  try {
    await api.post('/access-invite/accept', {
      token: token.value,
      password: password.value,
      password_confirmation: confirmation.value,
    })
    complete.value = true
    sessionStorage.removeItem('villas_access_invite')
    history.replaceState(null, '', '/convite')
  } catch (requestError) {
    error.value = errorMessage(requestError)
  } finally {
    saving.value = false
  }
}

onMounted(inspect)
</script>

<template>
  <main class="invite-page">
    <v-card class="invite-card" elevation="0">
      <div class="invite-brand"><div><img class="invite-wordmark" :src="'/static/assets/vitor-gouveia-wordmark-white.png?v=20261114-1'" alt="Vitor Gouveia" /><span>Ativação de acesso</span></div></div>
      <v-progress-linear v-if="loading" indeterminate color="secondary" />
      <template v-else-if="complete">
        <div class="invite-content text-center">
          <v-icon icon="mdi-check-circle" color="success" size="64" />
          <h1 class="mt-4">Acesso criado</h1>
          <p class="text-medium-emphasis mt-2">A sua password ficou definida. Já pode entrar no portal.</p>
          <v-btn color="primary" size="large" block class="mt-6" @click="router.replace('/login')">Entrar no portal</v-btn>
        </div>
      </template>
      <template v-else-if="invite">
        <div class="invite-content">
          <div class="text-overline text-secondary">Convite individual</div>
          <h1>Criar acesso</h1>
          <p class="text-medium-emphasis mt-2 mb-6">Olá, <b>{{ invite.fullName }}</b>. Defina a sua password para aceder à conta <b>@{{ invite.username }}</b>.</p>
          <v-alert v-if="error" type="error" variant="tonal" class="mb-4">{{ error }}</v-alert>
          <v-text-field v-model="password" label="Nova password" :type="showPassword ? 'text' : 'password'" :append-inner-icon="showPassword ? 'mdi-eye-off' : 'mdi-eye'" hint="Mínimo de 8 caracteres" persistent-hint autocomplete="new-password" @click:append-inner="showPassword = !showPassword" />
          <v-text-field v-model="confirmation" label="Confirmar password" :type="showPassword ? 'text' : 'password'" autocomplete="new-password" :error="Boolean(confirmation && password !== confirmation)" :error-messages="confirmation && password !== confirmation ? 'As passwords não coincidem.' : ''" class="mt-3" @keyup.enter="activate" />
          <v-btn color="primary" size="large" block class="mt-5" :disabled="!canSubmit" :loading="saving" @click="activate">Criar o meu acesso</v-btn>
          <div class="invite-expiry"><v-icon size="18">mdi-clock-outline</v-icon>Este link é pessoal, só pode ser usado uma vez e expira em 1 hora.</div>
        </div>
      </template>
      <div v-else class="invite-content text-center">
        <v-icon icon="mdi-link-off" color="warning" size="58" />
        <h1 class="mt-4">Link indisponível</h1>
        <p class="text-medium-emphasis mt-2">{{ error }}</p>
        <v-btn variant="tonal" class="mt-6" to="/login">Voltar ao login</v-btn>
      </div>
    </v-card>
  </main>
</template>

<style scoped>
.invite-page{min-height:100dvh;display:grid;place-items:center;padding:24px;background:linear-gradient(145deg,#eef1f5,#f8f5ee)}
.invite-card{width:min(100%,520px);overflow:hidden;border:1px solid rgba(23,36,61,.1);border-radius:24px!important;box-shadow:0 24px 70px rgba(23,36,61,.14)!important}
.invite-brand{display:flex;align-items:center;justify-content:center;padding:22px 28px;background:#17243d;color:#fff}.invite-brand>div{display:flex;flex-direction:column;align-items:center;gap:7px;text-align:center}.invite-wordmark{display:block;height:auto;width:220px}.invite-brand span{color:#c9d0dd;font-size:.76rem;letter-spacing:.08em;text-transform:uppercase}
.invite-content{padding:32px 28px}.invite-content h1{font-size:1.8rem;color:#17243d}.invite-expiry{display:flex;align-items:center;justify-content:center;gap:7px;margin-top:22px;color:rgba(var(--v-theme-on-surface),.62);font-size:.82rem;text-align:center}
@media(max-width:599px){.invite-page{padding:0;background:#fff}.invite-card{min-height:100dvh;border:0;border-radius:0!important}.invite-brand{padding:max(20px,env(safe-area-inset-top)) 22px 20px}.invite-content{padding:30px 22px}}
</style>
