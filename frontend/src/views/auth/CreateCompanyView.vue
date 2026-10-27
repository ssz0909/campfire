<template>
  <div class="create-company">
    <div class="create-company__locale"><LanguageToggle /></div>
    <div class="create-company__inner">
      <div class="create-company__header">
        <div class="brand">
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none" aria-hidden="true">
            <rect width="32" height="32" rx="8" fill="currentColor" style="color: var(--color-brand-500)" />
            <path d="M8 16C8 11.582 11.582 8 16 8s8 3.582 8 8-3.582 8-8 8-8-3.582-8-8z" fill="white" fill-opacity="0.3" />
            <path d="M13 16a3 3 0 1 1 6 0 3 3 0 0 1-6 0z" fill="white" />
          </svg>
          <span class="brand-name">营火AI</span>
        </div>
        <h1 class="create-company__title">{{ t('Create your workspace') }}</h1>
        <p class="create-company__subtitle">{{ t('Tell us about your company to get started') }}</p>
      </div>

      <div class="create-company__card">
        <n-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-placement="top"
        >
          <n-form-item :label="t('Company name')" path="name">
            <n-input v-model:value="form.name" :placeholder="t('Acme Corp')" />
          </n-form-item>

          <n-form-item :label="t('Industry')" path="industry">
            <n-select
              v-model:value="form.industry"
              :placeholder="t('Select industry')"
              :options="industryOptions"
              clearable
            />
          </n-form-item>

          <n-form-item :label="t('Website')" path="website">
            <n-input v-model:value="form.website" placeholder="https://example.com" />
          </n-form-item>

          <n-form-item :label="t('Description')" path="description">
            <n-input
              v-model:value="form.description"
              type="textarea"
              :placeholder="t('What does your company do?')"
              :autosize="{ minRows: 2, maxRows: 4 }"
            />
          </n-form-item>

          <n-form-item>
            <n-button
              type="primary"
              block
              :loading="loading"
              @click="handleSubmit"
            >
              {{ t('Create workspace') }}
            </n-button>
          </n-form-item>
        </n-form>

        <p v-if="errorMsg" class="create-company__error" role="alert">{{ errorMsg }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive, computed } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, NSelect, type FormInst, type FormRules } from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { companiesApi } from '@/api/companies'
import LanguageToggle from '@/components/common/LanguageToggle.vue'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  name: '',
  industry: null as string | null,
  website: '',
  description: '',
})

const rules: FormRules = {
  name: [
    { required: true, message: t('Company name is required'), trigger: 'blur' },
    { min: 2, message: t('Name must be at least 2 characters'), trigger: 'blur' },
  ],
}

const industryOptions = computed(() => [
  { label: t('E-commerce'), value: 'ecommerce' },
  { label: t('Retail'), value: 'retail' },
  { label: t('Technology'), value: 'technology' },
  { label: t('Healthcare'), value: 'healthcare' },
  { label: t('Finance'), value: 'finance' },
  { label: t('Education'), value: 'education' },
  { label: t('Media & Entertainment'), value: 'media' },
  { label: t('Real Estate'), value: 'real_estate' },
  { label: t('Other'), value: 'other' },
])

async function handleSubmit() {
  errorMsg.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const res = await companiesApi.create({
      name: form.name,
      industry: form.industry ?? undefined,
      website: form.website || undefined,
      description: form.description || undefined,
    })
    await authStore.fetchCompanies()
    authStore.selectCompany(res.data.id)
    router.push('/dashboard')
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorMsg.value = e?.response?.data?.detail ?? 'Failed to create company. Please try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.create-company {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--surface-page);
  padding: var(--space-6);
}

.create-company__inner {
  width: 100%;
  max-width: 480px;
}

.create-company__header {
  text-align: center;
  margin-bottom: var(--space-6);
}

.brand {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
}

.brand-name {
  font-size: var(--text-xl);
  font-weight: 700;
  color: var(--text-primary);
}

.create-company__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.create-company__subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

.create-company__card {
  background: var(--surface-card);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-xl);
  padding: var(--space-8);
  box-shadow: var(--shadow-md);
}

.create-company__error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: oklch(93% 0.08 25);
  border-radius: var(--radius-md);
  text-align: center;
}
</style>
