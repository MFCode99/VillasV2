<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { api, errorMessage } from '../services/api'
import { useFeedbackStore } from '../stores/feedback'

const feedback = useFeedbackStore()
const data = ref(null)
const loading = ref(false)
let refreshTimer = null

const services = computed(() => data.value ? [
  { key: 'database', title: 'Base de dados', icon: 'mdi-database-check-outline', ok: data.value.database.ok, detail: data.value.database.ok ? `${data.value.database.durationMs} ms` : 'Sem resposta' },
  { key: 'email', title: 'Email', icon: 'mdi-email-check-outline', ok: data.value.email.ok, detail: data.value.email.ok ? `${data.value.email.durationMs} ms` : data.value.email.configured ? 'Indisponível' : 'Não configurado' },
  { key: 'storage', title: 'Ficheiros', icon: 'mdi-folder-check-outline', ok: data.value.storage.ok, detail: `${data.value.storage.pathsChecked} locais verificados` },
] : [])

function uptime(seconds) {
  const total = Number(seconds || 0)
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  return [days ? `${days}d` : '', hours ? `${hours}h` : '', `${minutes}min`].filter(Boolean).join(' ')
}

function dateTime(value) {
  return value ? new Date(value).toLocaleString('pt-PT') : '—'
}

async function load({ quiet = false } = {}) {
  if (!quiet) loading.value = true
  try { data.value = (await api.get('/admin/system-health')).data }
  catch (error) { if (!quiet) feedback.show(errorMessage(error), 'error') }
  finally { loading.value = false }
}

onMounted(() => {
  load()
  refreshTimer = setInterval(() => load({ quiet: true }), 30000)
})
onUnmounted(() => clearInterval(refreshTimer))
</script>

<template>
  <div class="page system-health-page">
    <div class="page-head">
      <div><h1>Estado do sistema</h1><p>Diagnóstico simples do portal e dos serviços essenciais.</p></div>
      <v-btn color="primary" variant="tonal" prepend-icon="mdi-refresh" :loading="loading" @click="load()">Atualizar</v-btn>
    </div>

    <v-skeleton-loader v-if="!data" type="article, article" />
    <template v-else>
      <v-alert :type="data.status === 'ok' ? 'success' : 'warning'" variant="tonal" class="mb-5" :title="data.status === 'ok' ? 'Sistema operacional' : 'Sistema com atenção necessária'">
        O portal está ativo há {{ uptime(data.runtime.uptimeSeconds) }}. A informação atualiza automaticamente a cada 30 segundos.
      </v-alert>

      <v-row density="compact" class="mb-3">
        <v-col v-for="service in services" :key="service.key" cols="12" sm="4">
          <v-card class="soft-card health-card pa-5" :class="service.ok ? 'health-card--ok' : 'health-card--down'">
            <div class="d-flex align-center ga-3">
              <v-avatar :color="service.ok ? 'success' : 'error'" variant="tonal"><v-icon>{{ service.icon }}</v-icon></v-avatar>
              <div class="min-width-0"><div class="font-weight-bold">{{ service.title }}</div><div class="text-body-2 text-medium-emphasis">{{ service.detail }}</div></div>
              <v-icon class="ml-auto" :color="service.ok ? 'success' : 'error'">{{ service.ok ? 'mdi-check-circle' : 'mdi-alert-circle' }}</v-icon>
            </div>
          </v-card>
        </v-col>
      </v-row>

      <v-card v-if="data.monitoring" class="soft-card monitor-card pa-5 mb-5" :class="data.monitoring.ok ? 'monitor-card--ok' : 'monitor-card--warning'">
        <div class="d-flex flex-wrap align-center ga-4">
          <v-avatar :color="data.monitoring.ok ? 'success' : 'warning'" variant="tonal"><v-icon>mdi-monitor-eye</v-icon></v-avatar>
          <div class="flex-grow-1"><div class="font-weight-bold">Monitorização automática</div><div class="text-body-2 text-medium-emphasis">Último controlo: {{ dateTime(data.monitoring.checkedAt) }} · executado a cada 5 minutos</div></div>
          <v-chip :color="data.monitoring.ok ? 'success' : 'warning'" variant="tonal">{{ data.monitoring.ok ? 'Sem alertas' : `${data.monitoring.issues.length} alerta(s)` }}</v-chip>
        </div>
        <v-alert v-if="data.monitoring.issues.length" type="warning" variant="tonal" class="mt-4"><div v-for="issue in data.monitoring.issues" :key="issue">{{ issue }}</div></v-alert>
      </v-card>

      <v-row density="compact" class="mb-3">
        <v-col cols="6" md="3"><v-card class="soft-card pa-4"><div class="metric-value">{{ data.runtime.totalRequests }}</div><div class="metric-label">Pedidos desde o arranque</div></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="soft-card pa-4"><div class="metric-value">{{ data.runtime.errorRequests }}</div><div class="metric-label">Erros internos</div></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="soft-card pa-4"><div class="metric-value">{{ data.runtime.slowRequests }}</div><div class="metric-label">Pedidos lentos</div></v-card></v-col>
        <v-col cols="6" md="3"><v-card class="soft-card pa-4"><div class="metric-value">{{ data.runtime.slowThresholdMs }} ms</div><div class="metric-label">Limite de lentidão</div></v-card></v-col>
      </v-row>

      <v-row density="compact">
        <v-col cols="12" lg="6">
          <v-card class="soft-card pa-5 fill-height">
            <div class="d-flex align-center ga-2 mb-4"><v-icon color="error">mdi-alert-circle-outline</v-icon><h2 class="text-h6">Erros recentes</h2></div>
            <div v-if="!data.runtime.recentErrors.length" class="empty-list"><v-icon>mdi-check-circle-outline</v-icon><span>Não foram registados erros internos desde o arranque.</span></div>
            <v-list v-else lines="two" class="pa-0">
              <v-list-item v-for="row in data.runtime.recentErrors" :key="`${row.requestId}-${row.time}`" :title="`${row.method} ${row.path}`" :subtitle="`${dateTime(row.time)} · ${row.durationMs} ms · Código ${row.requestId}`" prepend-icon="mdi-alert-outline" />
            </v-list>
          </v-card>
        </v-col>
        <v-col cols="12" lg="6">
          <v-card class="soft-card pa-5 fill-height">
            <div class="d-flex align-center ga-2 mb-4"><v-icon color="warning">mdi-timer-alert-outline</v-icon><h2 class="text-h6">Operações lentas</h2></div>
            <div v-if="!data.runtime.recentSlowRequests.length" class="empty-list"><v-icon>mdi-speedometer</v-icon><span>Não foram registadas operações lentas desde o arranque.</span></div>
            <v-list v-else lines="two" class="pa-0">
              <v-list-item v-for="row in data.runtime.recentSlowRequests" :key="`${row.requestId}-${row.time}`" :title="`${row.method} ${row.path}`" :subtitle="`${dateTime(row.time)} · ${row.durationMs} ms`" prepend-icon="mdi-timer-sand" />
            </v-list>
          </v-card>
        </v-col>
      </v-row>

      <div class="text-caption text-medium-emphasis mt-4">Backend: FastAPI {{ data.versions.fastapi }} · SQLAlchemy {{ data.versions.sqlalchemy }} · Pydantic {{ data.versions.pydantic }}</div>
    </template>
  </div>
</template>

<style scoped>
.health-card { border-left: 4px solid transparent; }
.health-card--ok { border-left-color: rgb(var(--v-theme-success)); }
.health-card--down { border-left-color: rgb(var(--v-theme-error)); }
.monitor-card { border-left: 4px solid transparent; }
.monitor-card--ok { border-left-color: rgb(var(--v-theme-success)); }
.monitor-card--warning { border-left-color: rgb(var(--v-theme-warning)); }
.metric-value { color: rgb(var(--v-theme-primary)); font-size: clamp(1.35rem, 3vw, 1.85rem); font-weight: 800; line-height: 1.15; }
.metric-label { color: rgba(var(--v-theme-on-surface), .62); font-size: .8rem; margin-top: 6px; }
.empty-list { min-height: 150px; display: grid; place-content: center; justify-items: center; gap: 10px; color: rgba(var(--v-theme-on-surface), .58); text-align: center; }
.empty-list .v-icon { font-size: 34px; }
.min-width-0 { min-width: 0; }
@media (max-width: 600px) { .system-health-page :deep(.v-list-item) { padding-inline: 0; } }
</style>
