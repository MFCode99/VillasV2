<script setup>
import { useFeedbackStore } from './stores/feedback'
import AppShell from './layouts/AppShell.vue'
const feedback = useFeedbackStore()
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
