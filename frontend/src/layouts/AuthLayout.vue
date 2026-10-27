<template>
  <div class="auth-layout">
    <div class="auth-layout__locale"><LanguageToggle /></div>
    <div class="auth-layout__inner">
      <div class="auth-layout__brand" aria-label="营火AI platform">
        <div class="auth-layout__logo">
          <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" class="auth-layout__logo-bg" />
            <path d="M8 16C8 11.582 11.582 8 16 8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8z" fill="white" fill-opacity="0.3" />
            <path d="M13 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" fill="white" />
          </svg>
        </div>
        <div class="auth-layout__brand-copy"><span class="auth-layout__brand-name">营火AI</span><small>AI运营平台 · Always on, Always Growing</small></div>
      </div>
      <div class="auth-layout__card">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import LanguageToggle from '@/components/common/LanguageToggle.vue'
</script>

<style scoped>
.auth-layout {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background-color: var(--surface-page);
  padding: var(--space-6);
}

.auth-layout__locale {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
}

.auth-layout__inner {
  width: 100%;
  max-width: 440px;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
}

.auth-layout__brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
}

.auth-layout__logo {
  color: var(--color-brand-500);
}

.auth-layout__brand-copy { display: flex; flex-direction: column; gap: 2px; }

.auth-layout__brand-copy small { font-size: 10px; color: var(--text-secondary); letter-spacing: .02em; }

.auth-layout__brand-name {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.auth-layout__card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-md);
}
</style>
