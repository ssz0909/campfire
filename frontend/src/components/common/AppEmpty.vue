<template>
  <div class="app-empty" role="status">
    <div v-if="icon" class="app-empty__icon" aria-hidden="true">
      <component :is="icon" />
    </div>
    <p class="app-empty__title">{{ title }}</p>
    <p v-if="description" class="app-empty__description">{{ description }}</p>
    <div v-if="$slots.action" class="app-empty__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

interface Props {
  icon?: Component
  title: string
  description?: string
}

defineProps<Props>()
</script>

<style scoped>
.app-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  padding: var(--space-16) var(--space-8);
  text-align: center;
}

.app-empty__icon {
  font-size: 48px;
  color: var(--text-muted);
  line-height: 1;
}

.app-empty__title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.app-empty__description {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  max-width: 360px;
  line-height: var(--leading-normal);
}

.app-empty__action {
  margin-top: var(--space-2);
}
</style>
