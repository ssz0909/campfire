<template>
  <AuthLayout>
    <div class="login">
      <div class="login__header">
        <h1 class="login__title">{{ t('Welcome back') }}</h1>
        <p class="login__subtitle">{{ t('Sign in to your account to continue') }}</p>
      </div>

      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        @submit.prevent="handleSubmit"
      >
        <n-form-item :label="t('Email')" path="email">
          <n-input
            v-model:value="form.email"
            type="text"
            placeholder="you@company.com"
            autocomplete="email"
            :input-props="{ 'aria-label': t('Email address') }"
          />
        </n-form-item>

        <n-form-item :label="t('Password')" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            placeholder="••••••••"
            show-password-on="mousedown"
            autocomplete="current-password"
            :input-props="{ 'aria-label': t('Password') }"
            @keydown.enter="handleSubmit"
          />
        </n-form-item>

        <n-form-item>
          <n-button
            type="primary"
            block
            :loading="loading"
            attr-type="submit"
            @click="handleSubmit"
          >
            {{ t('Sign in') }}
          </n-button>
        </n-form-item>
      </n-form>

      <p v-if="errorMsg" class="login__error" role="alert">{{ errorMsg }}</p>

      <p class="login__footer">
        {{ t("Don't have an account?") }}
        <router-link to="/register">{{ t('Create one') }}</router-link>
      </p>
    </div>
  </AuthLayout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, type FormInst, type FormRules } from 'naive-ui'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  email: '',
  password: '',
})

const rules: FormRules = {
  email: [
    { required: true, message: t('Email is required'), trigger: 'blur' },
    { type: 'email', message: t('Enter a valid email address'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('Password is required'), trigger: 'blur' },
    { min: 6, message: t('Password must be at least 6 characters'), trigger: 'blur' },
  ],
}

async function handleSubmit() {
  errorMsg.value = ''
  try {
    await formRef.value?.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    await authStore.login(form.email, form.password)
    if (authStore.user?.is_platform_admin && authStore.companies.length === 0) {
      router.push('/admin')
    } else if (authStore.companies.length === 0) {
      router.push('/companies/new')
    } else if (authStore.currentCompanyId) {
      const redirect = route.query.redirect as string | undefined
      router.push(redirect ?? '/dashboard')
    } else {
      router.push('/companies')
    }
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: string } } }
    errorMsg.value = e?.response?.status && e.response.status >= 500
      ? t('The service is temporarily unavailable. Please try again.')
      : e?.response?.data?.detail ?? t('Invalid email or password. Please try again.')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login__header {
  margin-bottom: var(--space-6);
  text-align: center;
}

.login__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.login__subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

.login__error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  text-align: center;
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: oklch(93% 0.08 25);
  border-radius: var(--radius-md);
}

.login__footer {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-4);
}
</style>
