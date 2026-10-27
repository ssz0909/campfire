<template>
  <div class="page-header">
    <div class="page-header__left">
      <n-breadcrumb v-if="breadcrumbs && breadcrumbs.length" class="page-header__breadcrumb">
        <n-breadcrumb-item
          v-for="crumb in breadcrumbs"
          :key="crumb.label"
          :href="crumb.to ? undefined : undefined"
          @click="crumb.to ? router.push(crumb.to) : undefined"
        >
          {{ crumb.label }}
        </n-breadcrumb-item>
      </n-breadcrumb>
      <h1 class="page-header__title">{{ title }}</h1>
      <p v-if="subtitle" class="page-header__subtitle">{{ subtitle }}</p>
    </div>
    <div v-if="$slots.actions" class="page-header__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { NBreadcrumb, NBreadcrumbItem } from 'naive-ui'

interface Breadcrumb {
  label: string
  to?: string
}

interface Props {
  title: string
  subtitle?: string
  breadcrumbs?: Breadcrumb[]
}

defineProps<Props>()
const router = useRouter()
</script>

<style scoped>
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-6);
  flex-wrap: wrap;
}

.page-header__left {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.page-header__breadcrumb {
  margin-bottom: var(--space-1);
}

.page-header__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  line-height: var(--leading-tight);
  letter-spacing: -0.02em;
}

.page-header__subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}

.page-header__actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}
</style>
