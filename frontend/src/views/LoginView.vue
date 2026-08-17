<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useFeedbackStore } from '../stores/feedback'
import { errorMessage } from '../services/api'

const auth = useAuthStore(); const feedback = useFeedbackStore(); const router = useRouter(); const route = useRoute()
const form = reactive({ username: '', password: '' }); const visible = ref(false); const loading = ref(false)
async function submit() { loading.value = true; try { const user = await auth.login(form); feedback.show(`Bem-vindo, ${user.fullName}.`); router.replace(route.query.next || (user.role === 'admin' ? '/admin' : '/catalogo')) } catch (error) { feedback.show(errorMessage(error), 'error') } finally { loading.value = false } }
</script>
<template>
  <div class="login-shell">
    <v-card class="login-card soft-card">
      <div class="d-flex align-center ga-3 mb-8"><div class="brand-mark">V</div><div><div class="text-h5 font-weight-black">Villas</div></div></div>
      <h1 class="text-h4 font-weight-black mb-2">Olá novamente</h1><p class="text-medium-emphasis mb-7">Entre para consultar o catálogo e gerir encomendas.</p>
      <v-form @submit.prevent="submit">
        <v-text-field v-model="form.username" label="Utilizador" prepend-inner-icon="mdi-account-outline" autocomplete="username" required />
        <v-text-field v-model="form.password" label="Password" prepend-inner-icon="mdi-lock-outline" :type="visible ? 'text' : 'password'" :append-inner-icon="visible ? 'mdi-eye-off' : 'mdi-eye'" autocomplete="current-password" required @click:append-inner="visible = !visible" />
        <v-btn type="submit" color="primary" block size="large" class="mt-3" :loading="loading">Entrar</v-btn>
      </v-form>
    </v-card>
  </div>
</template>
