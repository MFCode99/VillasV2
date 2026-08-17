import { defineStore } from 'pinia'
import { api, rootApi, idempotencyKey } from '../services/api'

export const useCartStore = defineStore('cart', {
  state: () => ({ cart: { items: [], revision: 0, units: 0, total: '0.00' }, loading: false }),
  actions: {
    async load() { this.loading = true; try { const { data } = await api.get('/cart'); this.cart = data.cart } finally { this.loading = false } },
    async add(product, color = '', size = '', quantity = null) { const { data } = await rootApi.post('/me/cart/items', { idempotency_key: idempotencyKey('add'), cart_revision: this.cart.revision, ref: product.ref, color, size, quantity: quantity || product.quantityStep }); this.cart = data.cart },
    async update(item, quantity) { const { data } = await rootApi.patch(`/me/cart/items/${item.id}`, { idempotency_key: idempotencyKey('qty'), cart_revision: this.cart.revision, quantity }); this.cart = data.cart },
    async remove(item) { const { data } = await rootApi.delete(`/me/cart/items/${item.id}`, { data: { idempotency_key: idempotencyKey('remove'), cart_revision: this.cart.revision } }); this.cart = data.cart },
    async clear() { const { data } = await rootApi.delete('/me/cart', { data: { idempotency_key: idempotencyKey('clear'), cart_revision: this.cart.revision } }); this.cart = data.cart }
  }
})
