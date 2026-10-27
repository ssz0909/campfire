<template>
  <div class="app-card" :class="{ 'app-card--hoverable': hoverable }">
    <slot />
  </div>
</template>

<script setup lang="ts">
interface Props {
  hoverable?: boolean
}

withDefaults(defineProps<Props>(), {
  hoverable: false,
})
</script>

<style scoped>
.app-card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: var(--space-6);
}

.app-card--hoverable {
  cursor: pointer;
  transition: box-shadow var(--duration-normal) var(--ease-standard),
    border-color var(--duration-normal) var(--ease-standard);
}

.app-card--hoverable:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-strong);
}
</style>
