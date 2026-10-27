<template>
  <div>
    <template v-if="loading">
      <AppPageHeader :title="t('Loading...')" :breadcrumbs="[{ label: t('Employees'), to: '/employees' }]" />
      <AppCard><AppLoader variant="card" /></AppCard>
    </template>

    <template v-else-if="!employee">
      <AppPageHeader :title="t('Not found')" :breadcrumbs="[{ label: t('Employees'), to: '/employees' }]" />
      <AppEmpty :icon="PeopleOutline" :title="t('Employee not found')" />
    </template>

    <template v-else>
      <AppPageHeader
        :title="employee.name"
        :breadcrumbs="[{ label: t('Employees'), to: '/employees' }]"
        :subtitle="t(employee.role)"
      >
        <template #actions>
          <n-button v-if="employee.is_active" type="primary" @click="router.push({ path: '/tasks/new', query: { employee_id: employee.id } })">派发任务</n-button>
          <AppBadge :color="employee.is_active ? 'success' : 'default'" dot>{{ t(employee.is_active ? 'Active' : 'Inactive') }}</AppBadge>
          <n-button
            v-if="employee.is_active"
            ghost
            @click="toggleActive"
          >
            {{ t('Deactivate') }}
          </n-button>
          <n-button
            v-else
            type="primary"
            @click="toggleActive"
          >
            {{ t('Activate') }}
          </n-button>
        </template>
      </AppPageHeader>

      <n-tabs v-model:value="activeTab" type="line">
        <!-- Profile tab -->
        <n-tab-pane name="profile" :tab="t('Profile')">
          <AppCard>
            <n-form
              ref="formRef"
              :model="editForm"
              label-placement="top"
            >
              <n-form-item :label="t('Name')">
                <n-input v-model:value="editForm.name" />
              </n-form-item>
              <n-form-item :label="t('Description')">
                <n-input
                  v-model:value="editForm.description"
                  type="textarea"
                  :autosize="{ minRows: 3, maxRows: 6 }"
                />
              </n-form-item>
              <n-form-item :label="t('Approval Policy')">
                <n-select
                  v-model:value="editForm.approval_policy"
                  :options="policyOptions"
                />
              </n-form-item>
              <n-form-item
                v-if="editForm.approval_policy === 'above_threshold'"
                :label="t('Threshold (USD)')"
              >
                <n-input-number
                  v-model:value="editForm.approval_threshold"
                  :min="0"
                  :precision="2"
                />
              </n-form-item>
              <n-button type="primary" :loading="saving" @click="saveProfile">
                {{ t('Save changes') }}
              </n-button>
            </n-form>
          </AppCard>
        </n-tab-pane>

        <!-- Work Rules tab -->
        <n-tab-pane name="rules" :tab="t('Work Rules')">
          <AppCard>
            <h3 class="section-title">{{ t('Work Rules') }}</h3>
            <p class="section-desc">{{ t('Configure operational constraints and preferences for this employee.') }}</p>
            <pre class="code-block">{{ JSON.stringify(employee.work_rules, null, 2) }}</pre>
          </AppCard>
        </n-tab-pane>

        <!-- Tools tab -->
        <n-tab-pane name="tools" :tab="t('Tools & Permissions')">
          <AppCard>
            <h3 class="section-title">{{ t('Enabled Tools') }}</h3>
            <div v-if="employee.tools.length === 0">
              <AppEmpty :icon="ConstructOutline" :title="t('No tools configured')" :description="t('Tools will be assigned based on role.')" />
            </div>
            <ul v-else class="tools-list" role="list">
              <li v-for="tool in employee.tools" :key="tool" class="tool-item">
                <ConstructOutline class="tool-item__icon" aria-hidden="true" />
                <span>{{ tool }}</span>
              </li>
            </ul>
          </AppCard>
        </n-tab-pane>

        <!-- History tab -->
        <n-tab-pane name="history" :tab="t('Execution History')">
          <AppCard>
            <div class="section-header">
              <h3 class="section-title">{{ t('Recent Tasks') }}</h3>
            </div>
            <template v-if="tasksLoading">
              <AppLoader variant="table" :rows="5" />
            </template>
            <template v-else-if="recentTasks.length === 0">
              <AppEmpty :icon="FlashOutline" :title="t('No task history')" :description="t('Tasks run by this employee will appear here.')" />
            </template>
            <template v-else>
              <n-data-table
                :columns="taskColumns"
                :data="recentTasks"
                :bordered="false"
                size="small"
              />
            </template>
          </AppCard>
        </n-tab-pane>
      </n-tabs>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, reactive, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import {
  NButton, NTabs, NTabPane, NForm, NFormItem, NInput, NSelect,
  NInputNumber, NDataTable, type DataTableColumns, type FormInst,
} from 'naive-ui'
import { PeopleOutline, ConstructOutline, FlashOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import { tasksApi } from '@/api/tasks'
import type { DigitalEmployee, ApprovalPolicy } from '@/types/digitalEmployee'
import type { OperationTask } from '@/types/task'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const saving = ref(false)
const tasksLoading = ref(false)
const activeTab = ref('profile')
const employee = ref<DigitalEmployee | null>(null)
const recentTasks = ref<OperationTask[]>([])
const formRef = ref<FormInst | null>(null)

const editForm = reactive({
  name: '',
  description: '',
  approval_policy: 'always' as ApprovalPolicy,
  approval_threshold: null as number | null,
})

const policyOptions = computed(() => [
  { label: t('Always require approval'), value: 'always' },
  { label: t('Never require approval'), value: 'never' },
  { label: t('Require above threshold'), value: 'above_threshold' },
])

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed',
    cancelled: 'Cancelled', awaiting_approval: 'Awaiting Approval',
  }
  return labels[status] ?? status
}

function statusColor(status: string): 'info' | 'success' | 'danger' | 'warning' | 'default' {
  const colors: Record<string, 'info' | 'success' | 'danger' | 'warning' | 'default'> = {
    running: 'info', completed: 'success', failed: 'danger', awaiting_approval: 'warning',
  }
  return colors[status] ?? 'default'
}

const taskColumns = computed<DataTableColumns<OperationTask>>(() => [
  { title: t('Title'), key: 'title', ellipsis: true },
  {
    title: t('Status'),
    key: 'status',
    render: (row) => h(AppBadge, { color: statusColor(row.status), dot: true }, { default: () => t(statusLabel(row.status)) }),
  },
  {
    title: t('Cost'),
    key: 'cost_usd',
    render: (row) => (row.cost_usd ? `$${row.cost_usd.toFixed(4)}` : '—'),
  },
  {
    title: t('Date'),
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleString(locale.value),
  },
])

onMounted(async () => {
  try {
    const res = await digitalEmployeesApi.get(companyId.value, route.params.id as string)
    employee.value = res.data
    editForm.name = res.data.name
    editForm.description = res.data.description ?? ''
    editForm.approval_policy = res.data.approval_policy
    editForm.approval_threshold = res.data.approval_threshold ?? null
  } finally {
    loading.value = false
  }
  tasksLoading.value = true
  try {
    const tasksRes = await tasksApi.list(companyId.value, { limit: 20 })
    recentTasks.value = tasksRes.data.filter((t) => t.employee_id === route.params.id)
  } finally {
    tasksLoading.value = false
  }
})

async function saveProfile() {
  saving.value = true
  try {
    const res = await digitalEmployeesApi.update(companyId.value, employee.value!.id, {
      name: editForm.name,
      description: editForm.description,
      approval_policy: editForm.approval_policy,
      approval_threshold: editForm.approval_threshold ?? undefined,
    })
    employee.value = res.data
  } finally {
    saving.value = false
  }
}

async function toggleActive() {
  if (!employee.value) return
  const res = employee.value.is_active
    ? await digitalEmployeesApi.deactivate(companyId.value, employee.value.id)
    : await digitalEmployeesApi.activate(companyId.value, employee.value.id)
  employee.value = res.data
}
</script>

<style scoped>
.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-2);
}

.section-desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-4);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.code-block {
  background: var(--surface-sunken);
  border-radius: var(--radius-md);
  padding: var(--space-4);
  font-size: var(--text-xs);
  overflow-x: auto;
  color: var(--text-primary);
  line-height: var(--leading-loose);
  margin-top: var(--space-4);
}

.tools-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  list-style: none;
}

.tool-item {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  background: var(--surface-sunken);
  border-radius: var(--radius-md);
  font-size: var(--text-sm);
  color: var(--text-primary);
}

.tool-item__icon {
  font-size: 16px;
  color: var(--text-muted);
}
</style>
