<script setup>
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const props = defineProps({
  groups: { type: Array, default: () => [] },
  comfortable: { type: Boolean, default: false },
  dark: { type: Boolean, default: false },
  embedded: { type: Boolean, default: false },
})
const emit = defineEmits(['navigate'])
const route = useRoute()
const router = useRouter()
const opened = ref([])

function exactActive(to) {
  return route.fullPath === router.resolve(to).fullPath
}
function groupActive(group) {
  if (exactActive(group.to) || group.children.some(child => exactActive(child.to))) return true
  const target = router.resolve(group.to)
  if (!route.path.startsWith(`${target.path}/`)) return false
  return !target.query.categoria || route.query.categoria === target.query.categoria
}
const activeGroup = computed(() => props.groups.find(group => groupActive(group))?.key || null)
watch(activeGroup, value => { if (value) opened.value = [value] }, { immediate: true })
</script>

<template>
  <v-list v-model:opened="opened" nav :density="comfortable ? 'comfortable' : 'compact'" open-strategy="single" class="catalog-navigation" :class="{ 'is-comfortable': comfortable, 'is-dark': dark, 'is-embedded': embedded }" aria-label="Categorias dos catálogos">
    <template v-for="group in groups" :key="group.key">
      <v-list-group v-if="group.children.length" :value="group.key">
        <template #activator="{ props: activatorProps }">
          <v-list-item v-bind="activatorProps" :prepend-icon="group.icon" :title="group.title" :active="groupActive(group)" :color="dark ? 'secondary' : 'primary'" rounded="lg" class="catalog-group">
            <template #append>
              <v-icon class="catalog-chevron" size="18">{{ opened.includes(group.key) ? 'mdi-chevron-up' : 'mdi-chevron-down' }}</v-icon>
            </template>
          </v-list-item>
        </template>
        <div class="catalog-children">
          <v-list-item :to="group.to" :active="exactActive(group.to)" :title="group.allTitle || 'Ver todos'" :aria-label="group.allTitle || 'Ver todos'" :color="dark ? 'secondary' : 'primary'" rounded="lg" class="catalog-child catalog-child-all" @click="emit('navigate')">
            <template #prepend><v-icon size="16">mdi-view-grid-outline</v-icon></template>
          </v-list-item>
          <v-list-item v-for="child in group.children" :key="child.key" :to="child.to" :active="exactActive(child.to)" :title="child.title" :aria-label="child.title" :color="dark ? 'secondary' : 'primary'" rounded="lg" class="catalog-child" @click="emit('navigate')">
            <template #prepend><v-icon size="16" aria-hidden="true">{{ child.icon || 'mdi-tag-outline' }}</v-icon></template>
          </v-list-item>
        </div>
      </v-list-group>
      <v-list-item v-else :to="group.to" :active="groupActive(group)" :prepend-icon="group.icon" :title="group.title" :color="dark ? 'secondary' : 'primary'" rounded="lg" class="catalog-group" @click="emit('navigate')" />
    </template>
  </v-list>
</template>

<style scoped>
.catalog-navigation { background: transparent; padding: 0; }
.catalog-group { font-weight: 720; margin: 4px 0; min-height: 46px; }
.catalog-group :deep(.v-list-item__prepend) { margin-inline-end: 10px; }
.catalog-group :deep(.v-list-item__prepend > .v-icon) { background: rgba(var(--v-theme-on-surface), .075); border-radius: 9px; height: 30px; opacity: .9; width: 30px; }
.catalog-group :deep(.v-list-item__append) { gap: 6px; }
.catalog-group :deep(.v-list-item__append > .v-icon:last-child:not(.catalog-chevron)) { display: none; }
.catalog-chevron { opacity: .68; }
.catalog-children { border-left: 1px solid rgba(var(--v-theme-on-surface), .14); margin: 4px 0 10px 22px; padding-left: 8px; }
.catalog-child { margin: 2px 0; min-height: 40px; padding-inline: 8px !important; }
.catalog-child :deep(.v-list-item__content) { min-width: 0; }
.catalog-child :deep(.v-list-item__prepend) { margin-inline-end: 9px; width: 18px; }
.catalog-child :deep(.v-list-item__prepend .v-icon) { opacity: .56; }
.catalog-child :deep(.v-list-item-title) { font-size: .8rem; line-height: 1.3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog-child-all :deep(.v-list-item-title) { font-weight: 650; }
.catalog-child.v-list-item--active { font-weight: 700; }
.catalog-child.v-list-item--active :deep(.v-list-item__prepend .v-icon) { opacity: 1; }
.catalog-navigation.is-comfortable .catalog-group { min-height: 50px; }
.catalog-navigation.is-comfortable .catalog-child { min-height: 46px; }
.catalog-navigation.is-dark { color: rgba(255, 255, 255, .9); }
.catalog-navigation.is-dark .catalog-group :deep(.v-list-item__prepend > .v-icon) { background: rgba(255, 255, 255, .1); }
.catalog-navigation.is-dark .catalog-children { border-left-color: rgba(255, 255, 255, .18); }
.catalog-navigation.is-embedded :deep(.v-list-item--active) { background: rgba(var(--v-theme-secondary), .16); }
@media (prefers-reduced-motion: reduce) {
  .catalog-navigation :deep(*) { scroll-behavior: auto !important; transition-duration: .01ms !important; }
}
</style>
