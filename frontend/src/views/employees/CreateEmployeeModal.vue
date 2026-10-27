<template>
  <n-modal
    v-model:show="visible"
    preset="card"
    :title="t('New Digital Employee')"
    style="max-width: 520px"
    :mask-closable="false"
  >
    <n-form
      ref="formRef"
      :model="form"
      :rules="rules"
      label-placement="top"
    >
      <n-form-item :label="t('Name')" path="name">
        <n-input v-model:value="form.name" :placeholder="t('e.g. Content Creator #1')" />
      </n-form-item>

      <n-form-item :label="t('Role')" path="role">
        <n-select
          v-model:value="form.role"
          :options="roleOptions"
          :placeholder="t('Select a role')"
        />
      </n-form-item>

      <n-form-item :label="t('Description')" path="description">
        <n-input
          v-model:value="form.description"
          type="textarea"
          :placeholder="t('What does this employee do?')"
          :autosize="{ minRows: 2, maxRows: 4 }"
        />
      </n-form-item>

      <n-form-item :label="t('Approval Policy')" path="approval_policy">
        <n-select
          v-model:value="form.approval_policy"
          :options="policyOptions"
        />
      </n-form-item>

      <n-form-item
        v-if="form.approval_policy === 'above_threshold'"
        :label="t('Approval Threshold (USD)')"
        path="approval_threshold"
      >
        <n-input-number
          v-model:value="form.approval_threshold"
          :min="0"
          :precision="2"
          :placeholder="t('e.g. 5.00')"
        />
      </n-form-item>
    </n-form>

    <p v-if="errorMsg" class="create-error" role="alert">{{ errorMsg }}</p>

    <template #footer>
      <div class="modal-footer">
        <n-button @click="visible = false">{{ t('Cancel') }}</n-button>
        <n-button type="primary" :loading="loading" @click="handleSubmit">
          {{ t('Create Employee') }}
        </n-button>
      </div>
    </template>
  </n-modal>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NModal, NForm, NFormItem, NInput, NSelect, NButton, NInputNumber,
  type FormInst, type FormRules,
} from 'naive-ui'
import { useAuthStore } from '@/stores/auth'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import type { EmployeeRole, ApprovalPolicy } from '@/types/digitalEmployee'

interface Props {
  show: boolean
}

const { t } = useI18n()
const props = defineProps<Props>()
const emit = defineEmits<{
  'update:show': [val: boolean]
  created: []
}>()

const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const visible = computed({
  get: () => props.show,
  set: (v) => emit('update:show', v),
})

const formRef = ref<FormInst | null>(null)
const loading = ref(false)
const errorMsg = ref('')

const form = reactive({
  name: '',
  role: null as EmployeeRole | null,
  description: '',
  approval_policy: 'always' as ApprovalPolicy,
  approval_threshold: null as number | null,
})

const rules: FormRules = {
  name: [{ required: true, message: t('Name is required'), trigger: 'blur' }],
  role: [{ required: true, message: t('Role is required'), trigger: 'change' }],
}

const roleOptions = computed(() => [
  { label: t('operations_manager'), value: 'operations_manager' },
  { label: t('content_planner'), value: 'content_planner' },
  { label: t('data_analyst'), value: 'data_analyst' },
  { label: t('operations_assistant'), value: 'operations_assistant' },
  { label: t('Order Processor'), value: 'order_processor' },
  { label: t('Customer Service'), value: 'customer_service' },
  { label: t('Analyst'), value: 'analyst' },
  { label: t('Video Producer'), value: 'video_producer' },
  { label: t('Custom'), value: 'custom' },
])

const policyOptions = computed(() => [
  { label: t('Always require approval'), value: 'always' },
  { label: t('Never require approval'), value: 'never' },
  { label: t('Require approval above cost threshold'), value: 'above_threshold' },
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
    await digitalEmployeesApi.create(companyId.value, {
      name: form.name,
      role: form.role!,
      description: form.description || undefined,
      approval_policy: form.approval_policy,
      approval_threshold: form.approval_threshold ?? undefined,
    })
    emit('created')
  } catch (err: unknown) {
    const e = err as { response?: { data?: { detail?: string } } }
    errorMsg.value = e?.response?.data?.detail ?? t('Failed to create employee')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.create-error {
  font-size: var(--text-sm);
  color: var(--color-danger);
  padding: var(--space-2) var(--space-3);
  background: oklch(93% 0.08 25);
  border-radius: var(--radius-md);
  margin-top: var(--space-2);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
