import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const routes = [
  { path: '/login', name: 'login', component: () => import('../views/LoginView.vue'), meta: { public: true } },
  { path: '/', redirect: () => useAuthStore().isAdmin ? '/admin' : '/catalogo' },
  { path: '/catalogo', component: () => import('../views/CatalogView.vue') },
  { path: '/catalogo/:ref', component: () => import('../views/ProductView.vue') },
  { path: '/carrinho', component: () => import('../views/CartView.vue') },
  { path: '/encomendas', component: () => import('../views/OrdersView.vue') },
  { path: '/encomendas/:id', component: () => import('../views/OrderDetailView.vue') },
  { path: '/admin', component: () => import('../views/AdminDashboardView.vue'), meta: { admin: true } },
  { path: '/admin/utilizadores', component: () => import('../views/UsersView.vue'), meta: { admin: true } },
  { path: '/admin/utilizadores/:id', component: () => import('../views/UserDetailView.vue'), meta: { admin: true } },
  { path: '/admin/produtos', component: () => import('../views/ProductsView.vue'), meta: { admin: true } },
  { path: '/admin/categorias', component: () => import('../views/CategoriesView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas', component: () => import('../views/OrdersView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas/nova', component: () => import('../views/NewOrderView.vue'), meta: { admin: true } },
  { path: '/admin/encomendas/:id', component: () => import('../views/OrderDetailView.vue'), meta: { admin: true } },
  { path: '/admin/avisos', component: () => import('../views/WarningsView.vue'), meta: { admin: true } },
  { path: '/admin/estatisticas', component: () => import('../views/StatisticsView.vue'), meta: { admin: true } },
  { path: '/:pathMatch(.*)*', component: () => import('../views/NotFoundView.vue') }
]

const router = createRouter({ history: createWebHistory('/'), routes, scrollBehavior: () => ({ top: 0 }) })
router.beforeEach(async to => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.restore()
  if (!to.meta.public && !auth.authenticated) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && auth.authenticated) return auth.isAdmin ? '/admin' : '/catalogo'
  if (to.meta.admin && !auth.isAdmin) return '/catalogo'
})

export default router
