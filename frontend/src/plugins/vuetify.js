import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'

export default createVuetify({
  theme: {
    defaultTheme: 'villasLight',
    themes: {
      villasLight: {
        dark: false,
        colors: {
          background: '#f4f6fa',
          surface: '#ffffff',
          primary: '#17243d',
          secondary: '#c6a15b',
          accent: '#5271a5',
          success: '#2e7d61',
          warning: '#b77822',
          error: '#b83d48',
          info: '#3c6e9f'
        }
      }
    }
  },
  defaults: {
    VBtn: { rounded: 'lg', elevation: 0 },
    VCard: { rounded: 'xl', elevation: 0 },
    VTextField: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VSelect: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VTextarea: { variant: 'outlined', density: 'comfortable', color: 'primary' },
    VDialog: { maxWidth: 720 }
  }
})
