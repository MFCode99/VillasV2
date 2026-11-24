import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/convite', name: 'access-invite', component: () => import('../views/AccessInviteView.vue'), meta: { public: true } },
  { path: '/', component: () => import('../views/HomeView.vue') },
  { path: '/catalogo', redirect: () => useAuthStore().isAdmin ? '/catalogo/villas' : '/encomendas' },
  { path: '/catalogo/interpilhas', redirect: to => ({ path: '/catalogo/utilidades', query: to.query }) },
  { path: '/catalogo/interpilhas/:ref', redirect: to => `/catalogo/utilidades/${to.params.ref}` },
  { path: '/catalogo/:catalog', component: () => import('../views/CatalogView.vue') },
  { path: '/catalogo/:catalog/:ref', component: () => import('../views/ProductView.vue') },
  { path: '/catalogo/:ref', redirect: to => `/catalogo/villas/${to.params.ref}` },
  { path: '/carrinho', redirect: () => `/carrinho/${useAuthStore().catalogs[0] === 'interpilhas' ? 'utilidades' : useAuthStore().catalogs[0] || 'villas'}` },
  { path: '/carrinho/interpilhas', redirect: '/carrinho/utilidades' },
  { path: '/carrinho/:catalog', component: () => import('../views/CartView.vue') },
  { path: '/encomendas', component: () => import('../views/OrdersView.vue') },
  { path: '/encomendas/:id', component: () => import('../views/OrderDetailView.vue') },
  { path: '/conta', component: () => import('../views/AccountView.vue') },
  { path: '/admin', component: () => import('../views/StatisticsView.vue'), meta: { admin: true } },
  { path: '/admin/utilizadores', component: () => import('../views/UsersView.vue'), meta: { admin: true } },
  { path: '/admin/utilizadores/:id', component: () => import('../views/UserDetailView.vue'), meta: { admin: true } },
  { path: '/admin/produtos', component: () => import('../views/ProductsView.vue'), meta: { admin: true } },
  { path: '/admin/catalogos', component: () => import('../views/CatalogsView.vue'), meta: { admin: true } },
  { path: '/admin/campanhas', component: () => import('../views/CampaignsView.vue'), meta: { admin: true } },
  { path: '/admin/promocoes-oferta', component: () => import('../views/GiftPromotionsView.vue'), meta: { admin: true } },
  { path: '/admin/importacao', component: () => import('../views/ProductImportView.vue'), meta: { admin: true } },
  { path: '/admin/categorias', component: () => import('../views/CategoriesView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas', component: () => import('../views/OrdersView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas/nova', component: () => import('../views/NewOrderView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas/:id', component: () => import('../views/OrderDetailView.vue'), meta: { admin: true } },
  { path: '/admin/avisos', component: () => import('../views/WarningsView.vue'), meta: { admin: true } },
  { path: '/admin/acompanhamento/carrinhos', component: () => import('../views/PendingCartsView.vue'), meta: { admin: true } },
  { path: '/admin/acompanhamento/sistema', component: () => import('../views/SystemHealthView.vue'), meta: { admin: true } },
  { path: '/admin/developer/aparencia', component: () => import('../views/AppearanceView.vue'), meta: { admin: true } },
  { path: '/admin/developer/cloudflare', component: () => import('../views/CloudflareView.vue'), meta: { developer: true } },
  { path: '/admin/gestao/atualizacoes', component: () => import('../views/UpdatesView.vue'), meta: { updates: true } },
  { path: '/admin/estatisticas', redirect: '/admin', meta: { admin: true } },
  { path: '/admin/historico', component: () => import('../views/AuditLogView.vue'), meta: { admin: true } },
  { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue') }
]

const router = createRouter({ history: createWebHistory('/'), routes, scrollBehavior: () => ({ top: 0 }) })
router.beforeEach(async to => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.restore()
  if (!to.meta.public && !auth.authenticated) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && auth.authenticated) return '/'
  if (to.meta.admin && !auth.isAdmin) return '/encomendas'
  if (to.meta.updates && !auth.canManageUpdates) return '/encomendas'
  if (to.meta.developer && !auth.isDeveloper) return '/encomendas'
  const routeCatalog = String(to.params.catalog || '').toLowerCase()
  const requestedCatalog = routeCatalog === 'utilidades' ? 'interpilhas' : routeCatalog
  if (requestedCatalog && !auth.isAdmin && !auth.catalogs.includes(requestedCatalog)) return '/encomendas'
})

export default router
