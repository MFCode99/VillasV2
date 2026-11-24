import { defineStore } from 'pinia'
import { api, rootApi, idempotencyKey } from '../services/api'

const emptyCart = catalog => ({ catalog_slug: catalog, items: [], revision: 0, units: 0, lines: 0, subtotal: '0.00', total: '0.00', minimum_total: catalog === 'interpilhas' ? '300.00' : '250.00' })
const normalizedCatalog = value => /^[a-z0-9][a-z0-9-]{0,79}$/.test(String(value || '').toLowerCase()) ? String(value).toLowerCase() : 'villas'

export const useCartStore = defineStore('cart', {
  state: () => ({
    activeCatalog: 'villas',
    carts: { villas: emptyCart('villas'), interpilhas: emptyCart('interpilhas') },
    loaded: { villas: false, interpilhas: false },
    loading: false,
  }),
  getters: {
    cart: state => state.carts[state.activeCatalog] || emptyCart(state.activeCatalog),
    totalUnits: state => Object.values(state.carts).reduce((total, cart) => total + Number(cart.units || 0), 0),
  },
  actions: {
    select(catalog) { this.activeCatalog = normalizedCatalog(catalog) },
    setCart(catalog, value) {
      const slug = normalizedCatalog(catalog)
      this.carts[slug] = { ...emptyCart(slug), ...value, catalog_slug: slug }
      this.loaded[slug] = true
    },
    async load(catalog = this.activeCatalog) {
      const slug = normalizedCatalog(catalog)
      this.select(slug)
      this.loading = true
      try {
        const { data } = await api.get('/cart', { params: { catalog: slug } })
        this.setCart(slug, data.cart)
        return this.carts[slug]
      } finally { this.loading = false }
    },
    async loadAll(catalogs = ['villas', 'interpilhas']) { await Promise.all(catalogs.map(slug => this.load(slug))) },
    async add(product, color = '', size = '', quantity = null) {
      const slug = normalizedCatalog(product.catalogSlug || product.catalog_slug)
      if (!this.loaded[slug]) await this.load(slug)
      this.select(slug)
      const current = this.carts[slug]
      const { data } = await rootApi.post('/me/cart/items', { catalog_slug: slug, idempotency_key: idempotencyKey('add'), cart_revision: current.revision, ref: product.ref, color, size, quantity: quantity || product.quantityStep })
      this.setCart(slug, data.cart)
    },
    async update(item, quantity, catalog = this.activeCatalog, ignoreQuantityStep = false) {
      const slug = normalizedCatalog(catalog); const current = this.carts[slug]
      const { data } = await rootApi.patch(`/me/cart/items/${item.id}`, { catalog_slug: slug, idempotency_key: idempotencyKey('qty'), cart_revision: current.revision, quantity, ignore_quantity_step: Boolean(ignoreQuantityStep) })
      this.setCart(slug, data.cart)
    },
    async remove(item, catalog = this.activeCatalog) {
      const slug = normalizedCatalog(catalog); const current = this.carts[slug]
      const { data } = await rootApi.delete(`/me/cart/items/${item.id}`, { data: { catalog_slug: slug, idempotency_key: idempotencyKey('remove'), cart_revision: current.revision } })
      this.setCart(slug, data.cart)
    },
    async clear(catalog = this.activeCatalog) {
      const slug = normalizedCatalog(catalog); const current = this.carts[slug]
      const { data } = await rootApi.delete('/me/cart', { data: { catalog_slug: slug, idempotency_key: idempotencyKey('clear'), cart_revision: current.revision } })
      this.setCart(slug, data.cart)
    },
  },
})
