<template>
  <AuthLayout>
    <div class="register">
      <div class="register__header">
        <h1 class="register__title">{{ t('Create an account') }}</h1>
        <p class="register__subtitle">{{ t('Get started with AI-powered operations') }}</p>
      </div>

      <n-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-placement="top"
        @submit.prevent="handleSubmit"
      >
        <n-form-item :label="t('Full name')" path="full_name">
          <n-input
            v-model:value="form.full_name"
            :placeholder="t('Jane Smith')"
            autocomplete="name"
          />
        </n-form-item>

        <n-form-item :label="t('Email')" path="email">
          <n-input
            v-model:value="form.email"
            placeholder="you@company.com"
            autocomplete="email"
          />
        </n-form-item>

        <n-form-item :label="t('Password')" path="password">
          <n-input
            v-model:value="form.password"
            type="password"
            :placeholder="t('At least 8 characters')"
            show-password-on="mousedown"
            autocomplete="new-password"
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
            {{ t('Create account') }}
          </n-button>
        </n-form-item>
      </n-form>

      <p v-if="errorMsg" class="register__error" role="alert">{{ errorMsg }}</p>

      <p class="register__footer">
        {{ t('Already have an account?') }}
        <router-link to="/login">{{ t('Sign in') }}</router-link>
      </p>
    </div>
  </AuthLayout>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { NForm, NFormItem, NInput, NButton, type FormInst, type FormRules } from 'naive-ui'
import AuthLayout from '@/layouts/AuthLayout.vue'
import { useAuthStore } from '@/stores/auth'
import { authApi } from '@/api/auth'

const router = useRouter()
const authStore = useAuthStore()

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  full_name: '',
  email: '',
  password: '',
})

const rules: FormRules = {
  full_name: [
    { required: true, message: t('Full name is required'), trigger: 'blur' },
    { min: 2, message: t('Name must be at least 2 characters'), trigger: 'blur' },
  ],
  email: [
    { required: true, message: t('Email is required'), trigger: 'blur' },
    { type: 'email', message: t('Enter a valid email address'), trigger: 'blur' },
  ],
  password: [
    { required: true, message: t('Password is required'), trigger: 'blur' },
    { min: 8, message: t('Password must be at least 8 characters'), trigger: 'blur' },
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
    const res = await authApi.register(form)
    authStore.accessToken = res.data.access_token  // accessed via pinia store ref directly
    localStorage.setItem('refresh_token', res.data.refresh_token)
    await authStore.fetchUser()
    router.push('/companies/new')
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorMsg.value = e?.response?.data?.detail ?? t('Registration failed. Please try again.')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.register__header {
  margin-bottom: var(--space-6);
  text-align: center;
}

.register__title {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
}

.register__subtitle {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-1);
}

.register__error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  text-align: center;
  margin-top: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background: oklch(93% 0.08 25);
  border-radius: var(--radius-md);
}

.register__footer {
  text-align: center;
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: var(--space-4);
}
</style>
