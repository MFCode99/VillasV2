import { defineStore } from 'pinia'
import { api } from '../services/api'

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null, ready: false }),
  getters: { authenticated: s => Boolean(s.user), isAdmin: s => s.user?.role === 'admin' },
  actions: {
    async restore() { try { const { data } = await api.get('/session'); this.user = data.user } finally { this.ready = true } },
    async login(credentials) { const { data } = await api.post('/auth/login', credentials); this.user = data.user; return data.user },
    async logout() { await api.post('/auth/logout'); this.user = null }
  }
})
