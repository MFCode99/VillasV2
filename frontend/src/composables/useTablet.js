import { computed, onMounted, onUnmounted, watchEffect } from 'vue'
import { useDisplay } from 'vuetify'

export function classifyDevice(width, height, touch = false) {
  const shortest = Math.min(Number(width) || 0, Number(height) || 0)
  const longest = Math.max(Number(width) || 0, Number(height) || 0)
  const tablet = shortest >= 600 && longest <= 1440 && Boolean(touch)
  return {
    touch: Boolean(touch),
    tablet,
    portrait: Number(height) >= Number(width),
  }
}

export function useTablet() {
  const display = useDisplay()
  const touch = computed(() => Boolean(
    display.platform.value?.touch
    || (typeof navigator !== 'undefined' && navigator.maxTouchPoints > 0)
    || (typeof window !== 'undefined' && window.matchMedia?.('(pointer: coarse)').matches)
  ))
  const profile = computed(() => classifyDevice(display.width.value, display.height.value, touch.value))
  const isTablet = computed(() => profile.value.tablet)
  const tabletPortrait = computed(() => isTablet.value && profile.value.portrait)
  const tabletLandscape = computed(() => isTablet.value && !profile.value.portrait)

  function exposeProfile() {
    const root = document.documentElement
    root.dataset.touch = String(touch.value)
    root.dataset.device = isTablet.value ? 'tablet' : display.mobile.value ? 'mobile' : 'desktop'
    root.dataset.orientation = profile.value.portrait ? 'portrait' : 'landscape'
  }

  let stop
  onMounted(() => { stop = watchEffect(exposeProfile) })
  onUnmounted(() => stop?.())

  return { ...display, touch, isTablet, tabletPortrait, tabletLandscape }
}
