<template>
  <div class="company-select">
    <div class="company-select__locale"><LanguageToggle /></div>
    <div class="company-select__header">
      <div class="brand">
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <rect width="32" height="32" rx="8" fill="currentColor" class="brand-logo-color" />
          <path d="M8 16C8 11.582 11.582 8 16 8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8z" fill="white" fill-opacity="0.3" />
          <path d="M13 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" fill="white" />
        </svg>
        <span class="brand-name">营火AI</span>
      </div>
      <h1 class="company-select__title">{{ t('Select a workspace') }}</h1>
      <p class="company-select__subtitle">{{ t('Choose the company you want to work in') }}</p>
    </div>

    <div v-if="loading" class="company-select__grid">
      <div v-for="i in 3" :key="i" class="company-card company-card--skeleton">
        <AppLoader variant="card" />
      </div>
    </div>

    <div v-else class="company-select__grid">
      <button
        v-for="company in authStore.companies"
        :key="company.id"
        class="company-card"
        @click="selectCompany(company.id)"
      >
        <div class="company-card__avatar">
          {{ company.name.charAt(0).toUpperCase() }}
        </div>
        <div class="company-card__info">
          <p class="company-card__name">{{ company.name }}</p>
          <p v-if="company.industry" class="company-card__industry">{{ company.industry }}</p>
        </div>
        <ChevronForwardOutline class="company-card__arrow" aria-hidden="true" />
      </button>

      <router-link to="/companies/new" class="company-card company-card--new">
        <div class="company-card__avatar company-card__avatar--new">
          <AddOutline aria-hidden="true" />
        </div>
        <div class="company-card__info">
          <p class="company-card__name">{{ t('Create new company') }}</p>
          <p class="company-card__industry">{{ t('Set up a new workspace') }}</p>
        </div>
        <ChevronForwardOutline class="company-card__arrow" aria-hidden="true" />
      </router-link>
    </div>

    <div class="company-select__footer">
      <button class="logout-btn" @click="handleLogout">{{ t('Sign out') }}</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronForwardOutline, AddOutline } from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'
import AppLoader from '@/components/common/AppLoader.vue'
import LanguageToggle from '@/components/common/LanguageToggle.vue'

const router = useRouter()
const authStore = useAuthStore()
const loading = ref(false)

onMounted(async () => {
  if (authStore.companies.length === 0) {
    loading.value = true
    try {
      await authStore.fetchCompanies()
    } finally {
      loading.value = false
    }
  }
})

function selectCompany(id: string) {
  authStore.selectCompany(id)
  router.push('/dashboard')
}

async function handleLogout() {
  await authStore.logout()
  router.push('/login')
}
</script>

<style scoped>
.company-select {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: var(--space-6);
  background: var(--surface-page);
}

.company-select__locale {
  position: fixed;
  top: var(--space-4);
  right: var(--space-4);
}

.company-select__header {
  text-align: center;
  margin-bottom: var(--space-8);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-bottom: var(--space-6);
  color: var(--color-brand-500);
}

.brand-name {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.company-select__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.company-select__subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

.company-select__grid {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  width: 100%;
  max-width: 480px;
}

.company-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3) var(--space-4);
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  cursor: pointer;
  text-align: left;
  text-decoration: none;
  color: inherit;
  transition:
    box-shadow var(--duration-fast),
    border-color var(--duration-fast);
  min-height: 60px;
}

.company-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--border-strong);
}

.company-card--skeleton {
  cursor: default;
}

.company-card__avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-md);
  background: var(--color-brand-500);
  color: var(--text-on-brand);
  font-size: var(--text-base);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.company-card__avatar--new {
  background: var(--color-neutral-100);
  color: var(--text-muted);
  font-size: 16px;
}

.company-card__avatar--new > svg {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
}

.company-card__info {
  flex: 1;
  overflow: hidden;
}

.company-card__name {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.company-card__industry {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: 2px;
}

.company-card__arrow {
  width: 16px;
  height: 16px;
  font-size: 16px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.company-select__footer {
  margin-top: var(--space-8);
}

.logout-btn {
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: var(--text-sm);
  cursor: pointer;
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
}

.logout-btn:hover {
  color: var(--text-primary);
  background: var(--surface-sunken);
}
</style>
