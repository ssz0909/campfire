<template>
  <div class="app-loader" aria-busy="true" :aria-label="t('Loading content')">
    <template v-if="variant === 'card'">
      <div class="skeleton skeleton--title" />
      <div class="skeleton skeleton--text" />
      <div class="skeleton skeleton--text skeleton--text-short" />
    </template>
    <template v-else-if="variant === 'table'">
      <div v-for="i in rows" :key="i" class="skeleton-row">
        <div class="skeleton skeleton--cell" />
        <div class="skeleton skeleton--cell skeleton--cell-wide" />
        <div class="skeleton skeleton--cell skeleton--cell-narrow" />
        <div class="skeleton skeleton--cell skeleton--cell-narrow" />
      </div>
    </template>
    <template v-else-if="variant === 'stat'">
      <div class="skeleton skeleton--stat-label" />
      <div class="skeleton skeleton--stat-value" />
    </template>
    <template v-else>
      <div class="skeleton skeleton--line" />
    </template>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()

interface Props {
  variant?: 'card' | 'table' | 'stat' | 'line'
  rows?: number
}

withDefaults(defineProps<Props>(), {
  variant: 'line',
  rows: 5,
})
</script>

<style scoped>
@keyframes shimmer {
  0% { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.skeleton {
  background: linear-gradient(
    90deg,
    var(--color-neutral-100) 25%,
    var(--color-neutral-200) 50%,
    var(--color-neutral-100) 75%
  );
  background-size: 800px 100%;
  animation: shimmer 1.4s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

.skeleton--title {
  height: 20px;
  width: 60%;
  margin-bottom: var(--space-3);
}

.skeleton--text {
  height: 14px;
  width: 100%;
  margin-bottom: var(--space-2);
}

.skeleton--text-short {
  width: 75%;
}

.skeleton-row {
  display: flex;
  gap: var(--space-4);
  padding: var(--space-3) 0;
  border-bottom: 1px solid var(--border-default);
}

.skeleton--cell {
  height: 16px;
  flex: 1;
}

.skeleton--cell-wide {
  flex: 2;
}

.skeleton--cell-narrow {
  flex: 0.5;
}

.skeleton--stat-label {
  height: 13px;
  width: 80px;
  margin-bottom: var(--space-2);
}

.skeleton--stat-value {
  height: 32px;
  width: 120px;
}

.skeleton--line {
  height: 16px;
  width: 100%;
}
</style>
