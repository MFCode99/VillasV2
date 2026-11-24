import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import vuetify from './plugins/vuetify'
import './styles.css'

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js', { scope: '/' })
    .then(() => window.dispatchEvent(new CustomEvent('villas:pwa-ready')))
    .catch(() => { /* The portal remains usable online if registration is unavailable. */ })
}

createApp(App).use(createPinia()).use(router).use(vuetify).mount('#app')
