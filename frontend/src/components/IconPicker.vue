<script setup>
import { computed, ref } from 'vue'
import { contentIcons } from '../constants/contentIcons'

const props = defineProps({ modelValue: { type: String, default: '' }, label: { type: String, default: 'Ícone' } })
const emit = defineEmits(['update:modelValue'])
const dialog = ref(false)
const search = ref('')
const visibleIcons = computed(() => {
  const query = search.value.trim().toLowerCase()
  return query ? contentIcons.filter(icon => icon.includes(query)) : contentIcons
})
function choose(icon) { emit('update:modelValue', icon); dialog.value = false; search.value = '' }
</script>

<template>
  <div class="icon-picker">
    <div class="icon-picker-field" role="button" tabindex="0" :aria-label="`Escolher ${label.toLowerCase()}`" @click="dialog = true" @keydown.enter="dialog = true" @keydown.space.prevent="dialog = true">
      <v-avatar color="primary" variant="tonal" size="48"><v-icon size="27">{{ modelValue || 'mdi-shape-outline' }}</v-icon></v-avatar>
      <div class="flex-grow-1"><div class="text-caption text-medium-emphasis">{{ label }}</div><div class="font-weight-bold">Escolher na galeria</div></div>
      <v-icon>mdi-chevron-right</v-icon>
    </div>
    <v-dialog v-model="dialog" max-width="720">
      <v-card>
        <v-card-title class="pa-6 pb-2">Escolher ícone</v-card-title>
        <v-card-subtitle class="px-6">Selecione a imagem que identifica esta área no site.</v-card-subtitle>
        <v-card-text class="pa-6">
          <v-text-field v-model="search" clearable hide-details label="Pesquisar ícones" prepend-inner-icon="mdi-magnify" class="mb-5" />
          <div class="icon-grid">
            <v-tooltip v-for="icon in visibleIcons" :key="icon" :text="icon.replace('mdi-', '').replaceAll('-', ' ')">
              <template #activator="{ props: tooltipProps }"><v-btn v-bind="tooltipProps" :color="modelValue === icon ? 'primary' : undefined" :variant="modelValue === icon ? 'flat' : 'tonal'" class="icon-option" :aria-label="icon" @click="choose(icon)"><v-icon size="28">{{ icon }}</v-icon></v-btn></template>
            </v-tooltip>
          </div>
          <div v-if="!visibleIcons.length" class="text-center text-medium-emphasis py-8">Nenhum ícone encontrado.</div>
        </v-card-text>
        <v-card-actions class="px-6 pb-6"><v-spacer /><v-btn variant="text" @click="dialog = false">Cancelar</v-btn></v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<style scoped>
.icon-picker-field { align-items: center; border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity)); border-radius: 12px; cursor: pointer; display: flex; gap: 14px; min-height: 64px; padding: 8px 14px; transition: border-color .2s, background .2s; }
.icon-picker-field:hover, .icon-picker-field:focus-visible { background: rgba(var(--v-theme-primary), .04); border-color: rgb(var(--v-theme-primary)); outline: none; }
.icon-grid { display: grid; gap: 10px; grid-template-columns: repeat(8, minmax(0, 1fr)); }
.icon-option { height: 54px !important; min-width: 0 !important; width: 100%; }
@media (max-width: 600px) { .icon-grid { grid-template-columns: repeat(5, minmax(0, 1fr)); } }
</style>
