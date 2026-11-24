<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  document: { type: Object, required: true },
  pageNumber: { type: Number, required: true },
})

const host = ref(null)
const canvas = ref(null)
const visible = ref(false)
const rendering = ref(false)
const rendered = ref(false)
const failed = ref(false)
let observer = null
let resizeObserver = null
let renderTask = null
let page = null
let renderVersion = 0
let lastWidth = 0
let resizeFrame = 0

function cancelRender() {
  renderVersion += 1
  rendering.value = false
  if (renderTask) {
    try { renderTask.cancel() } catch {}
    renderTask = null
  }
  if (page) {
    try { page.cleanup() } catch {}
    page = null
  }
}

async function renderPage(force = false) {
  if (!visible.value || !host.value || !canvas.value || rendering.value) return
  const availableWidth = Math.floor(host.value.clientWidth)
  if (!availableWidth || (!force && rendered.value && Math.abs(availableWidth - lastWidth) < 24)) return

  cancelRender()
  const version = renderVersion
  rendering.value = true
  failed.value = false
  try {
    page = await props.document.getPage(props.pageNumber)
    if (version !== renderVersion) return
    const baseViewport = page.getViewport({ scale: 1 })
    const viewport = page.getViewport({ scale: availableWidth / baseViewport.width })
    const outputScale = Math.min(window.devicePixelRatio || 1, 1.75)
    const target = canvas.value
    const context = target.getContext('2d', { alpha: false })
    target.width = Math.max(1, Math.floor(viewport.width * outputScale))
    target.height = Math.max(1, Math.floor(viewport.height * outputScale))
    target.style.width = `${Math.floor(viewport.width)}px`
    target.style.height = `${Math.floor(viewport.height)}px`
    renderTask = page.render({
      canvasContext: context,
      viewport,
      transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
    })
    await renderTask.promise
    if (version !== renderVersion) return
    lastWidth = availableWidth
    rendered.value = true
  } catch (error) {
    if (error?.name !== 'RenderingCancelledException' && version === renderVersion) failed.value = true
  } finally {
    if (version === renderVersion) {
      rendering.value = false
      renderTask = null
      if (page) {
        try { page.cleanup() } catch {}
        page = null
      }
    }
  }
}

function observe() {
  observer = new IntersectionObserver(entries => {
    if (!entries.some(entry => entry.isIntersecting)) return
    visible.value = true
    observer?.disconnect()
    renderPage()
  }, { rootMargin: '700px 0px' })
  observer.observe(host.value)

  resizeObserver = new ResizeObserver(() => {
    cancelAnimationFrame(resizeFrame)
    resizeFrame = requestAnimationFrame(() => renderPage(true))
  })
  resizeObserver.observe(host.value)
}

watch(() => props.document, async () => {
  cancelRender()
  rendered.value = false
  failed.value = false
  lastWidth = 0
  await nextTick()
  if (visible.value) renderPage(true)
})

onMounted(observe)
onBeforeUnmount(() => {
  observer?.disconnect()
  resizeObserver?.disconnect()
  cancelAnimationFrame(resizeFrame)
  cancelRender()
})
</script>

<template>
  <article ref="host" class="pdf-page" :aria-label="`Página ${pageNumber} da pré-visualização do PDF`">
    <canvas ref="canvas" :class="{ 'is-visible': rendered }" />
    <div v-if="!rendered && !failed" class="pdf-page-placeholder" role="status">
      <v-progress-circular v-if="visible" indeterminate color="secondary" size="34" width="3" />
      <span>Página {{ pageNumber }}</span>
    </div>
    <v-alert v-if="failed" type="warning" variant="tonal" density="compact" class="ma-4">
      Não foi possível mostrar a página {{ pageNumber }}.
    </v-alert>
  </article>
</template>

<style scoped>
.pdf-page { aspect-ratio: 210 / 297; position: relative; overflow: hidden; border-radius: 8px; background: white; box-shadow: 0 10px 30px rgba(23, 36, 61, .14); }
canvas { display: block; max-width: 100%; opacity: 0; transition: opacity .15s ease; }
canvas.is-visible { opacity: 1; }
.pdf-page-placeholder { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 12px; color: #657087; background: linear-gradient(135deg, #fff, #f7f8fa); font-size: .82rem; }
@media (prefers-reduced-motion: reduce) { canvas { transition: none; } }
</style>
