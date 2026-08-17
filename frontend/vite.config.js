import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vuetify from 'vite-plugin-vuetify'

export default defineConfig({
  plugins: [vue(), vuetify({ autoImport: true })],
  base: '/',
  build: { outDir: 'dist', emptyOutDir: true },
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
