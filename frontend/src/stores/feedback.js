import { defineStore } from 'pinia'

export const useFeedbackStore = defineStore('feedback', {
  state: () => ({ snackbar: false, message: '', color: 'success', confirmOpen: false, confirmTitle: '', confirmText: '', resolver: null }),
  actions: {
    show(message, color = 'success') { this.message = message; this.color = color; this.snackbar = true },
    confirm(text, title = 'Confirmar operação') { this.confirmTitle = title; this.confirmText = text; this.confirmOpen = true; return new Promise(resolve => { this.resolver = resolve }) },
    answer(value) { this.confirmOpen = false; this.resolver?.(value); this.resolver = null }
  }
})
