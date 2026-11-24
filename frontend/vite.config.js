import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    vue(),
    vuetify({ autoImport: true }),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: false,
      manifest: false,
      workbox: {
        cleanupOutdatedCaches: true,
        clientsClaim: true,
        skipWaiting: true,
        navigateFallback: '/index.html',
        navigateFallbackDenylist: [/^\/api\//, /^\/me\//],
        globPatterns: [
          'index.html',
          'icons/*.{svg,png}',
          'assets/index-*.{js,css}',
          'assets/{VBtn,VCard,VChip,VOverlay,feedback,forwardRefs,LoginView}-*.{js,css}',
        ],
        inlineWorkboxRuntime: true,
        runtimeCaching: [
          {
            urlPattern: ({ url }) => url.origin === self.location.origin && url.pathname.startsWith('/assets/'),
            handler: 'CacheFirst',
            options: {
              cacheName: 'villas-interface-v1',
              expiration: { maxEntries: 180, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
          {
            urlPattern: ({ url }) => url.origin === self.location.origin && (url.pathname.startsWith('/media/products/') || url.pathname.startsWith('/static/assets/')),
            handler: 'CacheFirst',
            options: {
              cacheName: 'villas-public-media-v1',
              expiration: { maxEntries: 240, maxAgeSeconds: 60 * 60 * 24 * 14 },
              cacheableResponse: { statuses: [0, 200] },
            },
          },
        ],
      },
    }),
  ],
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true },
  test: { environment: 'jsdom', globals: true },
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8001',
      '/me': 'http://127.0.0.1:8001',
      '/media': 'http://127.0.0.1:8001',
      '/admin': 'http://127.0.0.1:8001'
    }
  }
})
