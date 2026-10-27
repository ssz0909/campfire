<template>
  <span class="app-badge" :class="`app-badge--${color}`" role="status">
    <span v-if="dot" class="app-badge__dot" aria-hidden="true" />
    <slot />
  </span>
</template>

<script setup lang="ts">
interface Props {
  color?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'brand'
  dot?: boolean
}

withDefaults(defineProps<Props>(), {
  color: 'default',
  dot: false,
})
</script>

<style scoped>
.app-badge {
  display: inline-flex;
  align-items: center;
  gap: var(--space-1);
  padding: 2px var(--space-2);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-weight: 600;
  line-height: var(--leading-tight);
  white-space: nowrap;
}

.app-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}

.app-badge--default {
  background: var(--color-neutral-100);
  color: var(--color-neutral-700);
}

.app-badge--success {
  background: oklch(93% 0.08 145);
  color: oklch(38% 0.18 145);
}

.app-badge--warning {
  background: oklch(93% 0.08 80);
  color: oklch(40% 0.18 80);
}

.app-badge--danger {
  background: oklch(93% 0.08 25);
  color: oklch(40% 0.22 25);
}

.app-badge--info {
  background: oklch(93% 0.08 230);
  color: oklch(38% 0.18 230);
}

.app-badge--brand {
  background: var(--color-brand-100);
  color: var(--color-brand-700);
}
</style>
