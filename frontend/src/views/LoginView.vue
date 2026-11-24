<script setup>
import { reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
import { api, errorMessage } from '../services/api'

const auth = useAuthStore(); const feedback = useFeedbackStore(); const route = useRoute()
const form = reactive({ username: '', password: '' }); const visible = ref(false); const loading = ref(false)
async function submit() {
  if (loading.value) return
  loading.value = true
  try {
    await auth.login(form)
    const { data } = await api.get('/session', { headers: { 'Cache-Control': 'no-cache' } })
    if (!data.authenticated || !data.user) throw new Error('O iPhone não guardou a sessão. Feche o modo privado e permita cookies para este site.')
    auth.user = data.user
    const requested = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/'
    window.location.replace(requested)
  } catch (error) {
    feedback.show(errorMessage(error), 'error')
    loading.value = false
  }
}
</script>
<template>
  <div class="login-shell">
    <main class="login-frame">
      <v-card class="login-card" elevation="0">
        <img class="login-wordmark" :src="'/static/assets/vitor-gouveia-wordmark-navy.png?v=20261114-1'" alt="Vitor Gouveia" />
        <v-form class="login-form" @submit.prevent="submit">
          <v-text-field v-model.trim="form.username" label="Utilizador" prepend-inner-icon="mdi-account-outline" autocomplete="username" required />
          <v-text-field v-model="form.password" label="Password" prepend-inner-icon="mdi-lock-outline" :type="visible ? 'text' : 'password'" :append-inner-icon="visible ? 'mdi-eye-off' : 'mdi-eye'" autocomplete="current-password" required @click:append-inner="visible = !visible" />
          <v-btn type="submit" color="primary" block size="large" class="login-submit" :loading="loading">Entrar</v-btn>
        </v-form>
      </v-card>
    </main>
  </div>
</template>
