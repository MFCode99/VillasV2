<script setup>
import { onMounted, onUnmounted } from 'vue'
import { useTheme } from 'vuetify'
import { useFeedbackStore } from './stores/feedback'
import { api } from './services/api'
import AppShell from './layouts/AppShell.vue'
import { applySiteTheme, defaultSiteTheme, normalizeSiteTheme } from './theme'

const feedback = useFeedbackStore()
const theme = useTheme()

let siteTheme = { ...defaultSiteTheme }
let userThemeMode = 'light'
function applyCurrentTheme() { applySiteTheme(theme, { ...siteTheme, userMode: userThemeMode }) }
function handleThemePreview(event) { siteTheme = normalizeSiteTheme(event.detail || defaultSiteTheme); applyCurrentTheme() }
function handleUserThemeMode(event) { userThemeMode = event.detail?.mode || 'light'; applyCurrentTheme() }
async function loadTheme() {
  try { siteTheme = normalizeSiteTheme((await api.get('/site/theme')).data.theme) }
  catch { siteTheme = { ...defaultSiteTheme } }
  applyCurrentTheme()
}
onMounted(() => { window.addEventListener('villas:theme-preview', handleThemePreview); window.addEventListener('villas:user-theme-mode', handleUserThemeMode); loadTheme() })
onUnmounted(() => { window.removeEventListener('villas:theme-preview', handleThemePreview); window.removeEventListener('villas:user-theme-mode', handleUserThemeMode) })
</script>

<template>
  <v-app>
    <AppShell />
    <v-snackbar v-model="feedback.snackbar" :color="feedback.color" location="top right" rounded="lg" :timeout="4200">
      {{ feedback.message }}
      <template #actions><v-btn variant="text" @click="feedback.snackbar = false">Fechar</v-btn></template>
    </v-snackbar>
    <v-dialog v-model="feedback.confirmOpen" persistent max-width="470">
      <v-card class="pa-2">
        <v-card-title>{{ feedback.confirmTitle }}</v-card-title>
        <v-card-text class="text-medium-emphasis">{{ feedback.confirmText }}</v-card-text>
        <v-card-actions class="px-4 pb-4">
          <v-spacer />
          <v-btn variant="text" @click="feedback.answer(false)">Cancelar</v-btn>
          <v-btn color="primary" @click="feedback.answer(true)">Confirmar</v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </v-app>
</template>
