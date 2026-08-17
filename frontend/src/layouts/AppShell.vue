<script setup>
import { computed, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useDisplay } from 'vuetify'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useFeedbackStore } from '../stores/feedback'
import { api } from '../services/api'
import NotificationBadge from '../components/NotificationBadge.vue'

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const cart = useCartStore(); const feedback = useFeedbackStore()
const { mobile } = useDisplay(); const drawer = ref(!mobile.value)
const isLogin = computed(() => route.name === 'login'); const pendingOrders = ref(0); const emailOnline = ref(null); let pendingTimer; let emailTimer
const items = computed(() => auth.isAdmin ? [
  { title: 'Visão geral', icon: 'mdi-view-dashboard-outline', to: '/admin' },
  { title: 'Catálogo', icon: 'mdi-view-grid-outline', to: '/catalogo' },
  { title: 'Carrinho', icon: 'mdi-cart-outline', to: '/carrinho', badge: cart.cart.units },
  { title: 'Utilizadores', icon: 'mdi-account-group-outline', to: '/admin/utilizadores' },
  { title: 'Produtos', icon: 'mdi-package-variant-closed', to: '/admin/produtos' },
  { title: 'Categorias', icon: 'mdi-shape-outline', to: '/admin/categorias' },
  { title: 'Encomendas', icon: 'mdi-receipt-text-outline', to: '/admin/encomendas', notifications: pendingOrders.value },
  { title: 'Nova encomenda', icon: 'mdi-cart-plus', to: '/admin/encomendas/nova' },
  { title: 'Avisos', icon: 'mdi-alert-circle-outline', to: '/admin/avisos' },
  { title: 'Estatísticas', icon: 'mdi-chart-line', to: '/admin/estatisticas' },
] : [
  { title: 'Catálogo', icon: 'mdi-view-grid-outline', to: '/catalogo' },
  { title: 'Carrinho', icon: 'mdi-cart-outline', to: '/carrinho', badge: cart.cart.units },
  { title: 'Encomendas', icon: 'mdi-receipt-text-outline', to: '/encomendas' }
])
async function refreshPendingOrders() { try { pendingOrders.value = Number((await api.get('/admin/dashboard')).data.metrics.pending_orders || 0) } catch { pendingOrders.value = 0 } }
async function refreshEmailStatus() { try { emailOnline.value = Boolean((await api.get('/email/status')).data.ok) } catch { emailOnline.value = false } }
watch(() => auth.user, value => { clearInterval(pendingTimer); clearInterval(emailTimer); pendingOrders.value = 0; emailOnline.value = null; if (!value) return; refreshEmailStatus(); cart.load().catch(() => {}); emailTimer = setInterval(refreshEmailStatus, 300000); if (auth.isAdmin) { refreshPendingOrders(); pendingTimer = setInterval(refreshPendingOrders, 30000) } }, { immediate: true })
onUnmounted(() => { clearInterval(pendingTimer); clearInterval(emailTimer) })
async function logout() { if (!await feedback.confirm('Pretende terminar esta sessão?', 'Terminar sessão')) return; await auth.logout(); router.replace('/login') }
</script>

<template>
  <router-view v-if="isLogin" />
  <template v-else-if="auth.authenticated">
    <v-navigation-drawer v-model="drawer" :temporary="mobile" width="272" color="primary">
      <div class="d-flex align-center ga-3 pa-5">
        <div class="brand-mark">V</div><div class="text-white"><div class="text-h6 font-weight-bold">Villas</div></div>
      </div>
      <v-divider class="opacity-20 mx-4 mb-3" />
      <v-list nav density="comfortable" class="px-3">
        <v-list-item v-for="item in items" :key="item.to" :to="item.to" :prepend-icon="item.icon" :title="item.title" color="secondary" rounded="lg">
          <template v-if="item.badge || item.notifications" #append><v-chip v-if="item.badge" size="x-small" color="secondary">{{ item.badge }}</v-chip><NotificationBadge v-if="item.notifications"><v-icon size="18">mdi-bell-ring-outline</v-icon></NotificationBadge></template>
        </v-list-item>
      </v-list>
      <template #append><div class="pa-4"><v-tooltip location="top" :text="emailOnline === true ? 'Email operacional' : emailOnline === false ? 'Email indisponível' : 'A verificar email'" ><template #activator="{ props }"><v-btn v-bind="props" block variant="text" :color="emailOnline === true ? 'success' : emailOnline === false ? 'error' : 'white'" :icon="emailOnline === true ? 'mdi-email-check-outline' : emailOnline === false ? 'mdi-email-alert-outline' : 'mdi-email-outline'" class="mb-1" /></template></v-tooltip><v-btn block variant="text" color="white" prepend-icon="mdi-logout" @click="logout">Terminar sessão</v-btn></div></template>
    </v-navigation-drawer>
    <v-app-bar flat color="surface" class="border-b">
      <v-app-bar-nav-icon @click="drawer = !drawer" />
      <v-spacer />
      <div class="text-right mr-3 d-none d-sm-block"><div class="text-body-2 font-weight-bold">{{ auth.user.fullName }}</div><div class="text-caption text-medium-emphasis">{{ auth.user.role === 'admin' ? 'Administrador' : auth.user.companyName || 'Cliente' }}</div></div>
      <v-avatar color="secondary" size="38" class="mr-4"><span class="font-weight-bold">{{ auth.user.fullName?.charAt(0)?.toUpperCase() }}</span></v-avatar>
    </v-app-bar>
    <v-main><router-view /></v-main>
  </template>
</template>
