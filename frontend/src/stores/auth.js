import { defineStore } from 'pinia'
import { api } from '../services/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null, ready: false }),
  getters: {
    authenticated: s => Boolean(s.user),
    isAdmin: s => ['admin', 'developer'].includes(s.user?.role),
    isDeveloper: s => s.user?.role === 'developer',
    canManageUpdates: s => ['admin', 'developer'].includes(s.user?.role),
    catalogs: s => s.user?.catalogs || []
  },
  actions: {
    async restore() { try { const { data } = await api.get('/session'); this.user = data.user } finally { this.ready = true } },
    async login(credentials) { const { data } = await api.post('/auth/login', credentials); Object.keys(sessionStorage).filter(key => key.startsWith('villas_update_notified_')).forEach(key => sessionStorage.removeItem(key)); this.user = data.user; return data.user },
    clearSession() { this.user = null; this.ready = true },
    async logout() {
      try { await api.post('/auth/logout') }
      finally { this.clearSession() }
    }
  }
})
