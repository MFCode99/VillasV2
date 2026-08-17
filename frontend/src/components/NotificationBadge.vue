<script setup>
defineProps({ count: { type: Number, default: 0 } })
</script>

<template>
  <v-badge :model-value="count > 0" :content="count > 99 ? '99+' : count" color="error" floating>
    <slot />
  </v-badge>
</template>
