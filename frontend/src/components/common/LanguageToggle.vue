<template>
  <div class="language-toggle" role="group" :aria-label="t('Language')">
    <button
      type="button"
      :aria-pressed="locale === 'zh-CN'"
      :class="{ 'language-toggle__option--active': locale === 'zh-CN' }"
      @click="setLocale('zh-CN')"
    >
      中文
    </button>
    <button
      type="button"
      :aria-pressed="locale === 'en-US'"
      :class="{ 'language-toggle__option--active': locale === 'en-US' }"
      @click="setLocale('en-US')"
    >
      English
    </button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { setLocale as saveLocale, type AppLocale } from '@/i18n'

const { locale: currentLocale, t } = useI18n()
const locale = computed(() => currentLocale.value as AppLocale)

function setLocale(nextLocale: AppLocale) {
  saveLocale(nextLocale)
}
</script>

<style scoped>
.language-toggle {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  background: var(--surface-sunken);
}

.language-toggle button {
  min-height: 30px;
  padding: 0 var(--space-2);
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  font: inherit;
  font-size: var(--text-xs);
}

.language-toggle button:hover {
  color: var(--text-primary);
}

.language-toggle .language-toggle__option--active {
  background: var(--surface-card);
  color: var(--text-primary);
  box-shadow: var(--shadow-sm);
}

.language-toggle button:focus-visible {
  outline: 2px solid var(--color-brand-500);
  outline-offset: 2px;
}
</style>
