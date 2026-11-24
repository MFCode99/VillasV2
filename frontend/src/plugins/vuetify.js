import 'vuetify/styles'
import '../mdi-subset.css'
import { createVuetify } from 'vuetify'
import { defaultSiteTheme } from '../theme'

export default createVuetify({
  theme: {
    defaultTheme: 'villasLight',
    themes: {
      villasLight: {
        dark: false,
        colors: {
          background: defaultSiteTheme.background,
          surface: defaultSiteTheme.surface,
          primary: defaultSiteTheme.primary,
          secondary: defaultSiteTheme.secondary,
          accent: defaultSiteTheme.accent,
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
