<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import PendingCartsOverview from '../components/PendingCartsOverview.vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const activity = ref({ summary: {}, customers: [] })
const loading = ref(true)
let refreshTimer = null

async function load({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    activity.value = (await api.get('/admin/pending-carts')).data
  } catch (error) {
    if (!silent) feedback.show(errorMessage(error), 'error')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await load()
  refreshTimer = window.setInterval(() => load({ silent: true }), 30000)
})
onBeforeUnmount(() => window.clearInterval(refreshTimer))
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div><div class="text-overline text-secondary font-weight-bold">Acompanhamento</div><h1>Carrinhos pendentes</h1><p>Veja quem demonstrou intenção de encomendar e ainda tem produtos guardados.</p></div>
    </div>
    <v-skeleton-loader v-if="loading && !activity.customers?.length" type="article, table" />
    <PendingCartsOverview v-else :activity="activity" :loading="loading" @refresh="load()" />
  </div>
</template>
