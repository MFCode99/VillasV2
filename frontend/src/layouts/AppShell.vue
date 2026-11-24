<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useCartStore } from '../stores/cart'
import { useFeedbackStore } from '../stores/feedback'
import { useTablet } from '../composables/useTablet'
import { api } from '../services/api'
import CatalogNavigation from '../components/CatalogNavigation.vue'
import NotificationBadge from '../components/NotificationBadge.vue'

const route = useRoute(); const router = useRouter(); const auth = useAuthStore(); const cart = useCartStore(); const feedback = useFeedbackStore()
const { mobile, touch, isTablet } = useTablet(); const drawer = ref(!mobile.value && !isTablet.value)
const compactNavigation = computed(() => mobile.value || isTablet.value)
const touchNavigation = computed(() => (touch.value || mobile.value) && (isTablet.value || mobile.value))
const safeAreaTop = ref(0)
const topBarHeight = computed(() => 64 + safeAreaTop.value)
const online = ref(typeof navigator === 'undefined' ? true : navigator.onLine)
const installPrompt = ref(null)
const mobileSection = ref(null)
const navigationCatalogs = ref([])
const activeCampaignCount = ref(0)
const appearanceAdminVisible = ref(false)
const darkModeAvailable = ref(false)
const userThemeMode = ref('light')
const savingThemeMode = ref(false)
const isPublicRoute = computed(() => Boolean(route.meta.public)); const pendingOrders = ref(0); const emailOnline = ref(null); let pendingTimer; let emailTimer; let updateTimer; let campaignTimer
const availableUpdate = ref(null)
const updateAnnouncement = ref(null)
const announcementOpen = ref(false)
const acknowledgingAnnouncement = ref(false)
const updateStatus = computed(() => availableUpdate.value ? 'Atualização disponível: ' + availableUpdate.value : 'Atualizações do site')
const userRoleLabel = computed(() => auth.user?.role === 'admin' ? 'Administrador' : auth.user?.role === 'developer' ? 'Developer' : auth.user?.companyName || 'Cliente')
const userInitials = computed(() => String(auth.user?.fullName || auth.user?.username || 'U').split(/\s+/).filter(Boolean).slice(0, 2).map(part => part[0]).join('').toUpperCase())
const utilityCategoryKeys = { 'interpilhas-pilhas': 'pilhas', 'interpilhas-ambientadores': 'ambientadores', 'interpilhas-colas-adesivos': 'colas' }
const utilityCategoryIcons = { 'interpilhas-pilhas': 'mdi-battery-charging-medium', 'interpilhas-ambientadores': 'mdi-spray-bottle', 'interpilhas-colas-adesivos': 'mdi-bottle-tonic-outline' }
const catalogGroups = computed(() => {
  const catalogs = navigationCatalogs.value.length
    ? navigationCatalogs.value
    : auth.catalogs.map(slug => ({ slug, label: slug === 'interpilhas' ? 'Utilidades' : 'Villas', categories: [] }))
  const groups = []
  if (activeCampaignCount.value > 0) groups.push({
    key: 'campaigns', title: 'Campanhas', icon: 'mdi-sale-outline', to: '/', allTitle: 'Ver campanhas', children: [],
  })
  for (const catalog of catalogs) {
    if (catalog.slug === 'villas') {
      groups.push({
        key: 'villas', title: 'Villas', icon: 'mdi-hanger', to: '/catalogo/villas', allTitle: 'Ver todos',
        children: (catalog.categories || []).map(category => ({ key: category.slug, title: category.label, icon: category.icon || 'mdi-tag-outline', to: { path: '/catalogo/villas', query: { categoria: category.slug } } })),
      })
      continue
    }
    if (catalog.slug === 'interpilhas') for (const category of catalog.categories || []) {
      const publicKey = utilityCategoryKeys[category.slug] || category.slug
      groups.push({
        key: category.slug, title: category.label, icon: category.icon || utilityCategoryIcons[category.slug] || 'mdi-shape-outline',
        to: { path: '/catalogo/utilidades', query: { categoria: publicKey } }, allTitle: 'Ver todos',
        children: (category.children || []).map(child => ({ key: child.slug, title: child.label, icon: child.icon || 'mdi-chevron-right', to: { path: '/catalogo/utilidades', query: { categoria: publicKey, subcategoria: child.slug } } })),
      })
    }
    if (catalog.slug !== 'interpilhas') groups.push({
      key: catalog.slug, title: catalog.label, icon: catalog.icon || 'mdi-bookshelf', to: `/catalogo/${catalog.slug}`, allTitle: 'Ver todos',
      children: (catalog.categories || []).map(category => ({ key: category.slug, title: category.label, icon: category.icon || 'mdi-tag-outline', to: { path: `/catalogo/${catalog.slug}`, query: { categoria: category.slug } } })),
    })
  }
  return groups
})
const cartCatalog = computed(() => {
  const routeValue = String(route.params.catalog || '').toLowerCase()
  const routeCatalog = routeValue === 'utilidades' ? 'interpilhas' : routeValue
  if (auth.catalogs.includes(routeCatalog)) return routeCatalog
  if (auth.catalogs.includes(cart.activeCatalog)) return cart.activeCatalog
  return auth.catalogs[0] || 'villas'
})
const cartRoute = computed(() => `/carrinho/${cartCatalog.value === 'interpilhas' ? 'utilidades' : cartCatalog.value}`)
const catalogRoute = computed(() => `/catalogo/${cartCatalog.value === 'interpilhas' ? 'utilidades' : cartCatalog.value}`)
const navSections = computed(() => auth.isAdmin ? [
  {
    title: 'Principal',
    items: [{ title: 'Faturação', icon: 'mdi-finance', to: '/admin' }],
  },
  {
    title: 'Operações',
    items: [
      { title: 'Encomendas', icon: 'mdi-receipt-text-outline', to: '/admin/encomendas', notifications: pendingOrders.value },
      { title: 'Carrinho', icon: 'mdi-cart-outline', to: cartRoute.value, badge: cart.totalUnits },
    ],
  },
  { title: 'Catálogos', icon: 'mdi-bookshelf', items: [], catalog: true },
  {
    title: 'Gestão', icon: 'mdi-cog-outline',
    items: [
      { title: 'Produtos', icon: 'mdi-package-variant-closed', to: '/admin/produtos' },
      { title: 'Campanhas', icon: 'mdi-sale-outline', to: '/admin/campanhas' },
      { title: 'Promoções com oferta', icon: 'mdi-gift-outline', to: '/admin/promocoes-oferta' },
      { title: 'Catálogos', icon: 'mdi-bookshelf', to: '/admin/catalogos' },
      { title: 'Importar produtos', icon: 'mdi-database-import-outline', to: '/admin/importacao' },
      { title: 'Categorias', icon: 'mdi-shape-outline', to: '/admin/categorias' },
      { title: 'Utilizadores', icon: 'mdi-account-group-outline', to: '/admin/utilizadores' },
    ],
  },
  {
    title: 'Acompanhamento', icon: 'mdi-chart-box-outline',
    items: [
      { title: 'Carrinhos pendentes', icon: 'mdi-cart-outline', to: '/admin/acompanhamento/carrinhos' },
      { title: 'Estado do sistema', icon: 'mdi-heart-pulse', to: '/admin/acompanhamento/sistema' },
      { title: 'Histórico', icon: 'mdi-history', to: '/admin/historico' },
      ...(auth.isDeveloper || appearanceAdminVisible.value ? [{ title: 'Aparência do site', icon: 'mdi-palette-outline', to: '/admin/developer/aparencia' }] : []),
      ...(auth.isDeveloper ? [{ title: 'Domínio e Cloudflare', icon: 'mdi-cloud-lock-outline', to: '/admin/developer/cloudflare' }] : []),
      auth.isDeveloper
        ? { title: 'Avisos de atualizações', icon: 'mdi-bullhorn-outline', to: '/admin/gestao/atualizacoes?tab=announcements&create=1' }
        : { title: 'Avisos', icon: 'mdi-alert-circle-outline', to: '/admin/avisos' },
    ],
  },
] : [
  {
    title: 'A minha área',
    items: [
      { title: 'Encomendas', icon: 'mdi-receipt-text-outline', to: '/encomendas' },
      { title: 'Carrinho', icon: 'mdi-cart-outline', to: cartRoute.value, badge: cart.totalUnits },
    ],
  },
  { title: 'Catálogos', icon: 'mdi-bookshelf', items: [], catalog: true },
])
function isItemActive(item) { return item.to.includes('?categoria=') ? route.fullPath === item.to : undefined }
function sectionContainsCurrentRoute(section) {
  return section.items.some(item => route.fullPath === item.to || route.path.startsWith(`${item.to}/`))
}
async function refreshPendingOrders() { try { pendingOrders.value = Number((await api.get('/admin/dashboard')).data.metrics.pending_orders || 0); return pendingOrders.value } catch { pendingOrders.value = 0; return 0 } }
async function refreshEmailStatus() { try { emailOnline.value = Boolean((await api.get('/email/status')).data.ok) } catch { emailOnline.value = false } }
async function refreshUpdateStatus() {
  try {
    const { data } = await api.get('/admin/system-update')
    availableUpdate.value = data.updateAvailable ? data.pending?.version || 'Nova versão' : null
    if (auth.user?.role === 'admin' && availableUpdate.value && data.pending?.notifyAdminsOnLogin !== false) {
      const key = `villas_update_notified_${availableUpdate.value}`
      if (!sessionStorage.getItem(key)) {
        sessionStorage.setItem(key, '1')
        feedback.show(`Atualização ${availableUpdate.value} disponível. Abra Atualizações no menu para consultar e instalar.`, 'info')
      }
    }
    if (auth.user?.role === 'admin') await refreshUpdateAnnouncement()
  } catch { /* Preserve the last known state during temporary network failures. */ }
}
async function refreshUpdateAnnouncement() {
  if (announcementOpen.value || updateAnnouncement.value) return
  const { data } = await api.get('/system-update/announcement')
  if (!data.announcement) return
  updateAnnouncement.value = data.announcement
  announcementOpen.value = true
  await api.post(`/system-update/announcements/${data.announcement.id}/viewed`)
}
async function respondUpdateAnnouncement(action) {
  if (!updateAnnouncement.value) return
  acknowledgingAnnouncement.value = true
  try {
    await api.post(`/system-update/announcements/${updateAnnouncement.value.id}/${action}`)
    announcementOpen.value = false
    updateAnnouncement.value = null
    setTimeout(refreshUpdateAnnouncement, 500)
  } catch { feedback.show('Não foi possível confirmar a leitura do aviso.', 'error') }
  finally { acknowledgingAnnouncement.value = false }
}
async function refreshCatalogNavigation() { try { navigationCatalogs.value = (await api.get('/catalog/navigation')).data.catalogs || [] } catch { navigationCatalogs.value = [] } }
async function refreshAppearanceAccess() {
  try {
    const themeSettings = (await api.get('/site/theme')).data.theme || {}
    appearanceAdminVisible.value = Boolean(themeSettings.adminCanView)
    darkModeAvailable.value = Boolean(themeSettings.modeEnabled)
  } catch {
    appearanceAdminVisible.value = false
    darkModeAvailable.value = false
  }
  window.dispatchEvent(new CustomEvent('villas:user-theme-mode', { detail: { mode: darkModeAvailable.value ? userThemeMode.value : 'light' } }))
}
async function setUserThemeMode(mode) {
  if (!darkModeAvailable.value || savingThemeMode.value) return
  savingThemeMode.value = true
  try {
    await api.put('/user/appearance', { mode })
    userThemeMode.value = mode
    auth.user = { ...auth.user, appearanceMode: mode }
    window.dispatchEvent(new CustomEvent('villas:user-theme-mode', { detail: { mode } }))
    feedback.show('Preferência visual guardada.')
  } catch (error) { feedback.show('Não foi possível guardar o modo visual.', 'error') }
  finally { savingThemeMode.value = false }
}
async function refreshActiveCampaigns() { try { activeCampaignCount.value = ((await api.get('/campaigns/active')).data.campaigns || []).length } catch { activeCampaignCount.value = 0 } }
async function remindPendingOrders(count) { if (!auth.isAdmin || !count || sessionStorage.getItem('villas_pending_orders_reminder')) return; sessionStorage.setItem('villas_pending_orders_reminder', '1'); if (await feedback.confirm(`Existem ${count} encomenda${count === 1 ? '' : 's'} pendente${count === 1 ? '' : 's'} para rever. Pretende abrir agora?`, 'Encomendas pendentes')) router.push('/admin/encomendas?status=pending') }
function openMobileSection(section) { mobileSection.value = section }
function handleNavClick() { mobileSection.value = null; if (compactNavigation.value) drawer.value = false }
function handleCatalogNavigate() { handleNavClick() }
function openDrawerOnSwipe() { if (compactNavigation.value && !drawer.value) drawer.value = true }
function closeDrawerOnSwipe() { if (compactNavigation.value && drawer.value) drawer.value = false }
function updateConnectionStatus() { online.value = navigator.onLine }
function updateSafeArea() {
  const probe = document.createElement('div')
  probe.style.cssText = 'position:fixed;inset:0 auto auto 0;padding-top:env(safe-area-inset-top, 0px);visibility:hidden;pointer-events:none'
  document.body.appendChild(probe)
  safeAreaTop.value = Math.max(0, Math.round(Number.parseFloat(getComputedStyle(probe).paddingTop) || 0))
  probe.remove()
}
function captureInstallPrompt(event) { event.preventDefault(); installPrompt.value = event }
async function installPortal() {
  if (!installPrompt.value) return
  await installPrompt.value.prompt()
  await installPrompt.value.userChoice
  installPrompt.value = null
}
watch(drawer, value => { if (!value) mobileSection.value = null })
watch([mobile, isTablet], ([isMobile, tablet]) => {
  drawer.value = !(isMobile || tablet)
})
watch(() => auth.user, async value => { clearInterval(pendingTimer); clearInterval(emailTimer); clearInterval(updateTimer); clearInterval(campaignTimer); availableUpdate.value = null; updateAnnouncement.value = null; announcementOpen.value = false; pendingOrders.value = 0; emailOnline.value = null; activeCampaignCount.value = 0; appearanceAdminVisible.value = false; darkModeAvailable.value = false; userThemeMode.value = value?.appearanceMode || 'light'; navigationCatalogs.value = []; if (!value) { window.dispatchEvent(new CustomEvent('villas:user-theme-mode', { detail: { mode: 'light' } })); return } refreshCatalogNavigation(); refreshAppearanceAccess(); refreshActiveCampaigns(); campaignTimer = setInterval(refreshActiveCampaigns, 60000); cart.loadAll(auth.catalogs).then(() => cart.select(auth.catalogs[0] || 'villas')).catch(() => {}); if (auth.canManageUpdates) { refreshUpdateStatus(); updateTimer = setInterval(refreshUpdateStatus, 30000) } if (auth.isAdmin) { refreshEmailStatus(); emailTimer = setInterval(refreshEmailStatus, 300000); const count = await refreshPendingOrders(); remindPendingOrders(count); pendingTimer = setInterval(refreshPendingOrders, 30000) } }, { immediate: true })
function sessionExpired() {
  if (!auth.authenticated) return
  auth.clearSession()
  feedback.show('A sessão terminou. Volte a entrar para continuar.', 'warning')
  router.replace({ name: 'login' })
}
function themeAccessChanged(event) {
  appearanceAdminVisible.value = Boolean(event.detail?.adminCanView)
  darkModeAvailable.value = Boolean(event.detail?.modeEnabled)
  window.dispatchEvent(new CustomEvent('villas:user-theme-mode', { detail: { mode: darkModeAvailable.value ? userThemeMode.value : 'light' } }))
}
onMounted(() => { updateSafeArea(); window.addEventListener('villas:session-expired', sessionExpired); window.addEventListener('villas:theme-access', themeAccessChanged); window.addEventListener('online', updateConnectionStatus); window.addEventListener('offline', updateConnectionStatus); window.addEventListener('resize', updateSafeArea); window.addEventListener('orientationchange', updateSafeArea); window.addEventListener('beforeinstallprompt', captureInstallPrompt) })
onUnmounted(() => { clearInterval(pendingTimer); clearInterval(emailTimer); clearInterval(updateTimer); clearInterval(campaignTimer); window.removeEventListener('villas:session-expired', sessionExpired); window.removeEventListener('villas:theme-access', themeAccessChanged); window.removeEventListener('online', updateConnectionStatus); window.removeEventListener('offline', updateConnectionStatus); window.removeEventListener('resize', updateSafeArea); window.removeEventListener('orientationchange', updateSafeArea); window.removeEventListener('beforeinstallprompt', captureInstallPrompt) })
async function logout() {
  if (!await feedback.confirm('Pretende terminar esta sessão?', 'Terminar sessão')) return
  try { await auth.logout() }
  finally { router.replace('/login') }
}
</script>

<template>
  <router-view v-if="isPublicRoute" />
  <template v-else-if="auth.authenticated">
    <v-navigation-drawer v-model="drawer" :temporary="compactNavigation" width="288" color="primary">
      <template v-if="mobileSection">
        <div class="mobile-panel-header">
          <v-btn icon="mdi-arrow-left" variant="text" color="white" aria-label="Voltar à navegação principal" @click="mobileSection = null" />
          <div><div class="text-caption text-white opacity-70">Navegação</div><div class="text-h6 text-white font-weight-bold">{{ mobileSection.title }}</div></div>
        </div>
        <v-divider class="opacity-20 mx-4 mb-2" />
        <v-list nav density="comfortable" class="sidebar-nav px-3" :aria-label="mobileSection.title">
          <v-list-item v-for="item in mobileSection.items" :key="item.to" :to="item.to" :active="isItemActive(item)" :prepend-icon="item.icon" :title="item.title" color="secondary" rounded="lg" class="sidebar-item drawer-item" @click="handleNavClick">
            <template v-if="item.badge || item.notifications" #append><v-chip v-if="item.badge" size="x-small" color="secondary">{{ item.badge }}</v-chip><NotificationBadge v-if="item.notifications"><v-icon size="18">mdi-bell-ring-outline</v-icon></NotificationBadge></template>
          </v-list-item>
        </v-list>
      </template>
      <template v-else>
        <router-link to="/" class="sidebar-brand pa-4" aria-label="Ir para a página inicial" @click="handleNavClick">
          <img class="sidebar-wordmark" :src="'/static/assets/vitor-gouveia-wordmark-white.png?v=20261114-1'" alt="" />
        </router-link>
        <v-divider class="opacity-20 mx-4 mb-3" />
        <v-list nav density="compact" class="sidebar-nav px-3" aria-label="Navegação principal">
          <template v-for="(section, sectionIndex) in (auth.isAdmin ? navSections.slice(0, 2) : navSections.filter(item => !item.catalog))" :key="section.title">
            <v-divider v-if="sectionIndex" class="sidebar-section-divider mx-2" />
            <v-list-subheader class="sidebar-section-title">{{ section.title }}</v-list-subheader>
            <v-list-item v-for="item in section.items" :key="item.to" :to="item.to" :active="isItemActive(item)" :prepend-icon="item.icon" :title="item.title" color="secondary" rounded="lg" class="sidebar-item drawer-item" @click="handleNavClick">
              <template v-if="item.badge || item.notifications" #append><v-chip v-if="item.badge" size="x-small" color="secondary">{{ item.badge }}</v-chip><NotificationBadge v-if="item.notifications"><v-icon size="18">mdi-bell-ring-outline</v-icon></NotificationBadge></template>
            </v-list-item>
          </template>
        </v-list>
        <div class="sidebar-catalogs px-3">
          <div class="sidebar-catalog-heading">
            <v-icon size="18" aria-hidden="true">mdi-bookshelf</v-icon>
            <span>Catálogos</span>
          </div>
          <CatalogNavigation :groups="catalogGroups" :comfortable="compactNavigation" dark embedded @navigate="handleCatalogNavigate" />
        </div>
        <v-list v-if="auth.isAdmin" nav density="compact" class="sidebar-nav sidebar-nav-after-catalogs px-3" aria-label="Administração">
          <template v-if="auth.isAdmin">
            <template v-for="section in navSections.slice(3)" :key="section.title">
              <v-list-item v-if="compactNavigation" :prepend-icon="section.icon" append-icon="mdi-chevron-right" :title="section.title" :active="sectionContainsCurrentRoute(section)" color="secondary" rounded="lg" class="sidebar-group-title drawer-item" @click="openMobileSection(section)" />
              <v-menu v-else location="end" :offset="8" close-on-content-click>
                <template #activator="{ props }">
                  <v-list-item v-bind="props" :prepend-icon="section.icon" append-icon="mdi-chevron-right" :title="section.title" :active="sectionContainsCurrentRoute(section)" color="secondary" rounded="lg" class="sidebar-group-title drawer-item" />
                </template>
                <v-card class="sidebar-flyout" min-width="250" elevation="10">
                  <v-list nav density="comfortable" class="pa-2">
                    <v-list-subheader class="flyout-title">{{ section.title }}</v-list-subheader>
                    <v-list-item v-for="item in section.items" :key="item.to" :to="item.to" :active="isItemActive(item)" :prepend-icon="item.icon" :title="item.title" color="primary" rounded="lg" class="sidebar-item" @click="handleNavClick">
                      <template v-if="item.badge || item.notifications" #append><v-chip v-if="item.badge" size="x-small" color="secondary">{{ item.badge }}</v-chip><NotificationBadge v-if="item.notifications"><v-icon size="18">mdi-bell-ring-outline</v-icon></NotificationBadge></template>
                    </v-list-item>
                  </v-list>
                </v-card>
              </v-menu>
            </template>
          </template>
        </v-list>
      </template>
      <template #append>
        <div class="sidebar-footer">
          <div class="sidebar-status-actions">
            <v-tooltip v-if="auth.canManageUpdates" location="top" :text="updateStatus">
              <template #activator="{ props }">
                <v-badge :model-value="Boolean(availableUpdate)" dot color="error" floating>
                  <v-btn v-bind="props" variant="text" :color="availableUpdate ? 'secondary' : 'white'" icon="mdi-update" class="sidebar-status-button" :aria-label="updateStatus" to="/admin/gestao/atualizacoes" @click="handleNavClick" />
                </v-badge>
              </template>
            </v-tooltip>
            <v-tooltip v-if="auth.isAdmin" location="top" :text="emailOnline === true ? 'Email operacional' : emailOnline === false ? 'Email indisponível' : 'A verificar email'">
              <template #activator="{ props }"><v-btn v-bind="props" variant="text" :color="emailOnline === true ? 'success' : emailOnline === false ? 'error' : 'white'" :icon="emailOnline === true ? 'mdi-email-check-outline' : emailOnline === false ? 'mdi-email-alert-outline' : 'mdi-email-outline'" class="sidebar-status-button" /></template>
            </v-tooltip>
          </div>
          <v-btn block variant="text" color="white" prepend-icon="mdi-logout" class="sidebar-logout" @click="logout">Terminar sessão</v-btn>
        </div>
      </template>
    </v-navigation-drawer>
    <v-app-bar flat color="surface" class="app-topbar border-b" :height="topBarHeight" :style="{ '--app-safe-top': `${safeAreaTop}px` }">
      <v-app-bar-nav-icon class="app-drawer-toggle" color="primary" aria-label="Abrir navegação" @click="drawer = !drawer" />
      <v-spacer />
      <v-menu location="bottom end" :offset="8">
        <template #activator="{ props }">
          <button v-bind="props" type="button" class="top-user" aria-label="Abrir menu do utilizador">
            <v-avatar color="secondary" size="38" class="top-user-avatar"><span>{{ userInitials }}</span></v-avatar>
            <span class="top-user-copy"><strong>{{ auth.user.fullName }}</strong><small>{{ userRoleLabel }}</small></span>
            <v-icon size="18" class="top-user-chevron">mdi-chevron-down</v-icon>
          </button>
        </template>
        <v-card class="user-menu" min-width="280" elevation="10">
          <div class="user-menu-head">
            <v-avatar color="secondary" size="46"><span class="font-weight-bold">{{ userInitials }}</span></v-avatar>
            <div class="min-width-0"><strong>{{ auth.user.fullName }}</strong><span>@{{ auth.user.username }} · {{ userRoleLabel }}</span></div>
          </div>
          <v-divider />
          <v-list nav density="comfortable" class="pa-2">
            <v-list-item to="/" prepend-icon="mdi-home-outline" title="Página inicial" rounded="lg" />
            <v-list-item :to="auth.isAdmin ? '/admin/encomendas' : '/encomendas'" prepend-icon="mdi-receipt-text-outline" title="Encomendas" rounded="lg" />
            <v-list-item to="/conta" prepend-icon="mdi-account-cog-outline" title="A minha conta" rounded="lg" />
            <v-list-item v-if="installPrompt" prepend-icon="mdi-download-outline" title="Instalar no tablet" subtitle="Adicionar ao ecrã principal" rounded="lg" @click="installPortal" />
            <template v-if="darkModeAvailable">
              <v-divider class="my-2" />
              <div class="user-theme-picker" @click.stop>
                <div><v-icon size="18">mdi-theme-light-dark</v-icon><span>Modo visual</span></div>
                <v-btn-toggle :model-value="userThemeMode" mandatory divided density="compact" variant="outlined" :disabled="savingThemeMode" @update:model-value="setUserThemeMode">
                  <v-btn value="light" icon="mdi-white-balance-sunny" aria-label="Modo claro" />
                  <v-btn value="dark" icon="mdi-weather-night" aria-label="Modo escuro" />
                  <v-btn value="system" icon="mdi-theme-light-dark" aria-label="Modo automático" />
                </v-btn-toggle>
              </div>
            </template>
            <v-divider class="my-2" />
            <v-list-item prepend-icon="mdi-logout" title="Terminar sessão" base-color="error" rounded="lg" @click="logout" />
          </v-list>
        </v-card>
      </v-menu>
    </v-app-bar>
    <v-main
      v-touch="{ left: closeDrawerOnSwipe, right: openDrawerOnSwipe }"
      class="portal-main"
      :class="{ 'portal-main--bottom-nav': touchNavigation }"
    >
      <v-alert v-if="!online" type="warning" variant="tonal" icon="mdi-wifi-off" class="offline-alert" role="status">
        Sem ligação. Pode consultar páginas já abertas, mas compras e alterações ficam bloqueadas até a ligação regressar.
      </v-alert>
      <router-view />
    </v-main>
    <v-bottom-navigation v-if="touchNavigation" grow color="primary" class="client-bottom-nav" aria-label="Navegação principal">
      <template v-if="auth.isAdmin">
        <v-btn to="/admin" value="dashboard"><v-icon>mdi-finance</v-icon><span>Faturação</span></v-btn>
        <v-btn to="/admin/encomendas" value="orders"><v-badge :model-value="pendingOrders > 0" :content="pendingOrders" color="secondary"><v-icon>mdi-receipt-text-outline</v-icon></v-badge><span>Encomendas</span></v-btn>
        <v-btn to="/admin/produtos" value="products"><v-icon>mdi-package-variant-closed</v-icon><span>Produtos</span></v-btn>
        <v-btn :to="cartRoute" value="cart"><v-badge :model-value="cart.totalUnits > 0" :content="cart.totalUnits" color="secondary"><v-icon>mdi-cart-outline</v-icon></v-badge><span>Carrinho</span></v-btn>
        <v-btn value="menu" aria-label="Abrir todas as opções" @click="drawer = true"><v-icon>mdi-menu</v-icon><span>Menu</span></v-btn>
      </template>
      <template v-else>
        <v-btn to="/" value="home"><v-icon>mdi-home-outline</v-icon><span>Início</span></v-btn>
        <v-btn :to="catalogRoute" value="catalog"><v-icon>mdi-bookshelf</v-icon><span>Catálogo</span></v-btn>
        <v-btn :to="cartRoute" value="cart"><v-badge :model-value="cart.totalUnits > 0" :content="cart.totalUnits" color="secondary"><v-icon>mdi-cart-outline</v-icon></v-badge><span>Carrinho</span></v-btn>
        <v-btn to="/encomendas" value="orders"><v-icon>mdi-receipt-text-outline</v-icon><span>Encomendas</span></v-btn>
        <v-btn to="/conta" value="account"><v-icon>mdi-account-outline</v-icon><span>Conta</span></v-btn>
      </template>
    </v-bottom-navigation>
    <v-dialog v-model="announcementOpen" max-width="680" persistent>
      <v-card v-if="updateAnnouncement" class="update-announcement-card">
        <div class="update-announcement-hero"><div class="announcement-spark"><v-icon size="34">mdi-star-four-points</v-icon></div><div><div class="text-overline">Nova atualização para conhecer</div><div class="text-h4 font-weight-bold">Versão {{ updateAnnouncement.version }}</div><div class="announcement-hero-hint">O Developer selecionou estas novidades para si.</div></div></div>
        <v-card-text class="px-6 pt-5"><h2 class="text-h6 mb-2">{{ updateAnnouncement.title }}</h2><p v-if="updateAnnouncement.summary" class="text-body-2 text-medium-emphasis mb-5">{{ updateAnnouncement.summary }}</p><div class="announcement-dialog-notes"><div v-for="(note, index) in updateAnnouncement.notes" :key="index"><v-icon color="success" size="20">mdi-check-circle-outline</v-icon><div><span>{{ note.section }}</span><p>{{ note.text }}</p></div></div></div></v-card-text>
        <v-card-actions class="announcement-response-actions px-6 pb-6 pt-2"><v-btn size="large" variant="outlined" color="grey-darken-1" prepend-icon="mdi-close-circle-outline" :disabled="acknowledgingAnnouncement" @click="respondUpdateAnnouncement('ignored')">Ignorar</v-btn><v-spacer /><v-btn size="large" color="success" prepend-icon="mdi-check-decagram-outline" :loading="acknowledgingAnnouncement" @click="respondUpdateAnnouncement('acknowledged')">Lido</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </template>
</template>

<style scoped>
.sidebar-brand { align-items: center; box-sizing: border-box; display: flex; justify-content: center; min-height: calc(88px + env(safe-area-inset-top)); padding: calc(16px + env(safe-area-inset-top)) 24px 16px !important; text-decoration: none; width: 100%; }
.sidebar-brand:focus-visible { border-radius: 12px; outline: 3px solid rgb(var(--v-theme-secondary)); outline-offset: -5px; }
.sidebar-wordmark { display: block; height: 56px; margin-inline: auto; object-fit: contain; object-position: center; transform: translateX(4px); width: min(216px, 100%); }
.sidebar-nav { padding-bottom: 14px; }
.sidebar-section-title { color: rgba(255, 255, 255, .52) !important; font-size: .66rem; font-weight: 800; letter-spacing: .1em; min-height: 30px; padding-inline: 12px !important; text-transform: uppercase; }
.sidebar-section-divider { border-color: rgba(255, 255, 255, .12); margin-bottom: 5px; margin-top: 9px; }
.sidebar-item { min-height: 44px; }
.drawer-item { color: rgba(255, 255, 255, .84); font-size: .86rem; font-weight: 680; margin-block: 3px; min-height: 46px; transition: background-color .16s ease, color .16s ease; }
.drawer-item:hover { background: rgba(255, 255, 255, .075); color: white; }
.drawer-item.v-list-item--active { background: rgba(var(--v-theme-secondary), .16); color: white; }
.drawer-item :deep(.v-list-item__prepend > .v-icon) { align-items: center; background: rgba(255, 255, 255, .1); border: 1px solid rgba(255, 255, 255, .06); border-radius: 9px; display: inline-flex; height: 30px; justify-content: center; margin-inline-end: 10px; opacity: .92; width: 30px; }
.drawer-item.v-list-item--active :deep(.v-list-item__prepend > .v-icon) { background: rgba(var(--v-theme-secondary), .24); color: rgb(var(--v-theme-secondary)); opacity: 1; }
.drawer-item :deep(.v-list-item__append > .v-icon) { color: rgba(255, 255, 255, .46); font-size: 19px; }
.sidebar-group-title { font-size: .86rem; font-weight: 680; letter-spacing: 0; min-height: 46px; text-transform: none; }
.sidebar-flyout { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 14px !important; }
.flyout-title { color: rgb(var(--v-theme-primary)) !important; font-size: .72rem; font-weight: 800; letter-spacing: .1em; text-transform: uppercase; }
.mobile-panel-header { align-items: center; box-sizing: border-box; display: flex; gap: 8px; min-height: calc(72px + env(safe-area-inset-top)); padding: calc(10px + env(safe-area-inset-top)) 12px 10px; }
.sidebar-catalogs { border-bottom: 1px solid rgba(255, 255, 255, .12); border-top: 1px solid rgba(255, 255, 255, .12); margin: 7px 12px 10px; padding: 9px 0 !important; }
.sidebar-catalog-heading { align-items: center; color: rgba(255, 255, 255, .52); display: flex; font-size: .66rem; font-weight: 800; gap: 7px; letter-spacing: .1em; min-height: 30px; padding: 0 12px 4px; text-transform: uppercase; }
.sidebar-nav-after-catalogs { padding-bottom: 8px; padding-top: 0; }
.sidebar-footer { border-top: 1px solid rgba(255, 255, 255, .12); margin: 0 12px; padding: 10px 0 max(12px, env(safe-area-inset-bottom)); }
.sidebar-status-actions { align-items: center; display: flex; gap: 6px; justify-content: center; margin-bottom: 6px; }
.sidebar-status-button { background: rgba(255, 255, 255, .075); border: 1px solid rgba(255, 255, 255, .07); height: 38px !important; width: 38px !important; }
.sidebar-status-button:hover { background: rgba(255, 255, 255, .13); }
.sidebar-logout { border-radius: 12px !important; font-size: .82rem; font-weight: 680; min-height: 42px; opacity: .82; }
.sidebar-logout:hover { background: rgba(255, 255, 255, .075); opacity: 1; }
.app-topbar { padding-left: max(0px, env(safe-area-inset-left)); padding-right: max(12px, env(safe-area-inset-right)); }
.app-topbar :deep(.v-toolbar__content) { box-sizing: border-box; padding-top: var(--app-safe-top); }
.app-drawer-toggle { background: rgba(var(--v-theme-primary), .07); margin-left: 8px; }
.top-user { align-items: center; background: transparent; border: 1px solid transparent; border-radius: 14px; color: rgb(var(--v-theme-on-surface)); cursor: pointer; display: flex; gap: 10px; max-width: min(290px, calc(100vw - 82px)); min-height: 48px; padding: 4px 8px 4px 5px; text-align: left; transition: background-color .16s ease, border-color .16s ease; }
.top-user:hover, .top-user[aria-expanded="true"] { background: rgba(var(--v-theme-primary), .055); border-color: rgba(var(--v-theme-primary), .1); }
.top-user:focus-visible { outline: 3px solid rgba(var(--v-theme-secondary), .5); outline-offset: 2px; }
.top-user-avatar span { font-size: .78rem; font-weight: 850; letter-spacing: .02em; }
.top-user-avatar { flex: 0 0 auto; }
.top-user-copy { display: flex; flex: 1 1 auto; flex-direction: column; line-height: 1.2; max-width: 210px; min-width: 0; }
.top-user-copy strong { font-size: .82rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-user-copy small { color: rgba(var(--v-theme-on-surface), .58); font-size: .69rem; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.top-user-chevron { color: rgba(var(--v-theme-on-surface), .48); }
.user-menu { border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 16px !important; overflow: hidden; }
.user-menu-head { align-items: center; display: flex; gap: 12px; padding: 18px; }
.user-menu-head div { display: flex; flex-direction: column; }
.user-menu-head strong { font-size: .9rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-menu-head span { color: rgba(var(--v-theme-on-surface), .58); font-size: .72rem; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.user-theme-picker { align-items: center; display: flex; gap: 12px; justify-content: space-between; padding: 8px 10px; }
.user-theme-picker > div { align-items: center; display: flex; font-size: .78rem; font-weight: 700; gap: 8px; }
.user-theme-picker :deep(.v-btn) { min-width: 34px; width: 34px; }
.min-width-0 { min-width: 0; }
.update-announcement-card { border: 1px solid rgba(var(--v-theme-secondary), .3); border-radius: 24px !important; box-shadow: 0 24px 70px rgba(4, 16, 43, .28) !important; overflow: hidden; }.update-announcement-hero { align-items: center; background: linear-gradient(135deg, rgb(var(--v-theme-primary)), color-mix(in srgb, rgb(var(--v-theme-primary)) 72%, rgb(var(--v-theme-secondary)))); color: rgb(var(--v-theme-on-primary)); display: flex; gap: 18px; padding: 28px 26px; position: relative; }.update-announcement-hero::after { background: radial-gradient(circle, rgba(255,255,255,.22), transparent 68%); content: ''; height: 190px; position: absolute; right: -45px; top: -80px; width: 190px; }.announcement-spark { align-items: center; background: rgba(255,255,255,.16); border: 1px solid rgba(255,255,255,.28); border-radius: 16px; display: flex; flex: 0 0 62px; height: 62px; justify-content: center; }.announcement-hero-hint { font-size: .78rem; margin-top: 4px; opacity: .78; }.announcement-dialog-notes { display: grid; gap: 10px; max-height: 44vh; overflow: auto; }.announcement-dialog-notes > div { align-items: flex-start; background: rgba(var(--v-theme-primary), .045); border: 1px solid rgba(var(--v-theme-primary), .08); border-radius: 14px; display: flex; gap: 10px; padding: 13px; }.announcement-dialog-notes span { color: rgb(var(--v-theme-primary)); display: block; font-size: .67rem; font-weight: 850; letter-spacing: .04em; text-transform: uppercase; }.announcement-dialog-notes p { font-size: .84rem; line-height: 1.55; margin: 2px 0 0; overflow-wrap: anywhere; }.announcement-response-actions .v-btn { min-width: 132px; }
.portal-main { touch-action: pan-y; }
.offline-alert { border-radius: 0 !important; margin: 0; position: sticky; top: 0; z-index: 20; }
.client-bottom-nav { border-top: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); height: calc(68px + env(safe-area-inset-bottom)) !important; padding-bottom: env(safe-area-inset-bottom); }
.client-bottom-nav :deep(.v-btn) { font-size: .68rem; min-width: 0; }
.client-bottom-nav :deep(.v-btn__content) { gap: 3px; }
.portal-main--bottom-nav { padding-bottom: calc(68px + env(safe-area-inset-bottom)); }
:deep(.v-navigation-drawer__content) { scrollbar-width: none; }
:deep(.v-navigation-drawer__content::-webkit-scrollbar) { display: none; }
@media (max-width: 600px) {
  .sidebar-item { min-height: 48px; }
  .sidebar-catalogs { margin-inline: 10px; }
  .top-user { background: rgba(var(--v-theme-primary), .055); border-color: rgba(var(--v-theme-primary), .1); gap: 8px; margin-right: 2px; max-width: min(238px, calc(100vw - 76px)); padding: 4px 7px 4px 4px; }
  .top-user-copy { max-width: 145px; }
  .top-user-copy strong { font-size: .78rem; }
  .top-user-copy small { font-size: .65rem; }
  .top-user-chevron { flex: 0 0 auto; }
}
@media (max-width: 360px) {
  .top-user { max-width: 205px; }
  .top-user-copy { max-width: 118px; }
  .top-user-chevron { display: none; }
}
</style>
