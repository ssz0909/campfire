<template>
  <div>
    <AppPageHeader :title="t('Dashboard')" :subtitle="t('Overview of your AI operations')">
      <template #actions>
        <n-button-group>
          <n-button type="primary" @click="router.push('/tasks/new')">
            <template #icon><FlashOutline /></template>
{{ t('New Task') }}
          </n-button>
          <n-button @click="router.push('/assets')">
            <template #icon><CloudUploadOutline /></template>
{{ t('Upload Asset') }}
          </n-button>
          <n-button @click="router.push('/video/new')">
            <template #icon><VideocamOutline /></template>
{{ t('New Video') }}
          </n-button>
        </n-button-group>
      </template>
    </AppPageHeader>

    <!-- Stats row -->
    <div class="stats-row">
      <template v-if="statsLoading">
        <AppCard v-for="i in 4" :key="i">
          <AppLoader variant="stat" />
        </AppCard>
      </template>
      <template v-else>
        <AppCard v-for="stat in stats" :key="stat.label" class="stat-card">
          <p class="stat-card__label">{{ t(stat.label) }}</p>
          <p class="stat-card__value">{{ stat.value }}</p>
          <StatusBadge v-if="stat.status" :status="stat.status" />
        </AppCard>
      </template>
    </div>

    <div class="dashboard-grid">
      <!-- Recent tasks -->
      <AppCard class="dashboard-grid__main">
        <div class="section-header">
          <h2 class="section-title">{{ t('Recent Tasks') }}</h2>
          <n-button text @click="router.push('/tasks')">{{ t('View all') }}</n-button>
        </div>

        <template v-if="tasksLoading">
          <AppLoader variant="table" :rows="5" />
        </template>
        <template v-else-if="recentTasks.length === 0">
          <AppEmpty
            :icon="FlashOutline"
             :title="t('No tasks yet')"
             :description="t('Create a task to start automating your operations')"
          >
            <template #action>
              <n-button type="primary" @click="router.push('/tasks/new')">{{ t('Create task') }}</n-button>
            </template>
          </AppEmpty>
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

      <!-- Right column -->
      <div class="dashboard-grid__side">
        <!-- Pending approvals -->
        <AppCard>
          <div class="section-header">
            <h2 class="section-title">{{ t('Pending Approvals') }}</h2>
            <n-button text @click="router.push('/approvals')">{{ t('View all') }}</n-button>
          </div>

          <template v-if="approvalsLoading">
            <AppLoader variant="card" />
          </template>
          <template v-else-if="pendingApprovals.length === 0">
            <AppEmpty
              :icon="CheckmarkCircleOutline"
             :title="t('All clear')"
               :description="t('No pending approvals')"
            />
          </template>
          <template v-else>
            <ul class="approval-list" role="list">
              <li
                v-for="approval in pendingApprovals"
                :key="approval.id"
                class="approval-item"
              >
                <div class="approval-item__content">
                  <p class="approval-item__title">{{ approval.operation_type }}</p>
                  <p class="approval-item__desc">{{ approval.description }}</p>
                </div>
                <AppBadge
                  :color="approval.urgency === 'high' ? 'danger' : approval.urgency === 'medium' ? 'warning' : 'default'"
                >
                  {{ t(approval.urgency) }}
                </AppBadge>
              </li>
            </ul>
          </template>
        </AppCard>

        <!-- Employee status -->
        <AppCard>
          <div class="section-header">
            <h2 class="section-title">{{ t('Employees') }}</h2>
            <n-button text @click="router.push('/employees')">{{ t('View all') }}</n-button>
          </div>

          <template v-if="employeesLoading">
            <AppLoader variant="card" />
          </template>
          <template v-else-if="employees.length === 0">
            <AppEmpty
              :icon="PeopleOutline"
               :title="t('No employees')"
               :description="t('Add digital employees to automate tasks')"
            />
          </template>
          <template v-else>
            <ul class="employee-list" role="list">
              <li
                v-for="emp in employees.slice(0, 5)"
                :key="emp.id"
                class="employee-item"
              >
                <div class="employee-item__avatar">
                  {{ emp.name.charAt(0).toUpperCase() }}
                </div>
                <div class="employee-item__info">
                  <p class="employee-item__name">{{ emp.name }}</p>
                  <p class="employee-item__role">{{ t(emp.role) }}</p>
                </div>
                <StatusBadge :status="emp.is_active ? 'active' : 'inactive'" />
              </li>
            </ul>
          </template>
        </AppCard>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, h } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NButtonGroup,
  NDataTable,
  type DataTableColumns,
} from 'naive-ui'
import {
  FlashOutline,
  CloudUploadOutline,
  VideocamOutline,
  CheckmarkCircleOutline,
  PeopleOutline,
} from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { tasksApi } from '@/api/tasks'
import { approvalsApi } from '@/api/approvals'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import { analyticsApi } from '@/api/analytics'
import type { OperationTask } from '@/types/task'
import type { ApprovalRequest } from '@/types/approval'
import type { DigitalEmployee } from '@/types/digitalEmployee'
import type { OverviewStats } from '@/types/analytics'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const statsLoading = ref(true)
const tasksLoading = ref(true)
const approvalsLoading = ref(true)
const employeesLoading = ref(true)

const overviewStats = ref<OverviewStats | null>(null)
const recentTasks = ref<OperationTask[]>([])
const pendingApprovals = ref<ApprovalRequest[]>([])
const employees = ref<DigitalEmployee[]>([])

const stats = computed(() => [
  {
    label: 'Active Tasks',
    value: overviewStats.value?.active_tasks ?? 0,
  },
  {
    label: 'Pending Approvals',
    value: overviewStats.value?.pending_approvals ?? 0,
    status: (overviewStats.value?.pending_approvals ?? 0) > 0 ? 'awaiting_approval' : undefined,
  },
  {
    label: 'Videos This Month',
    value: overviewStats.value?.videos_this_month ?? 0,
  },
  {
    label: 'Cost This Month',
    value: `$${(overviewStats.value?.total_cost_this_month_usd ?? 0).toFixed(2)}`,
  },
])

const taskColumns = computed<DataTableColumns<OperationTask>>(() => [
  { title: t('Title'), key: 'title', ellipsis: true },
  {
    title: t('Type'),
    key: 'task_type',
    render: (row) => t(row.task_type),
  },
  {
    title: t('Status'),
    key: 'status',
    render: (row) => h(StatusBadge, { status: row.status }),
  },
  {
    title: t('Cost'),
    key: 'cost_usd',
    render: (row) => (row.cost_usd ? `$${row.cost_usd.toFixed(4)}` : '—'),
  },
  {
    title: t('Created'),
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleDateString(),
  },
])

onMounted(async () => {
  await Promise.allSettled([
    loadStats(),
    loadTasks(),
    loadApprovals(),
    loadEmployees(),
  ])
})

async function loadStats() {
  try {
    const res = await analyticsApi.overview(companyId.value)
    overviewStats.value = res.data
  } catch {
    // use defaults
  } finally {
    statsLoading.value = false
  }
}

async function loadTasks() {
  try {
    const res = await tasksApi.list(companyId.value, { limit: 10 })
    recentTasks.value = res.data
  } catch {
    recentTasks.value = []
  } finally {
    tasksLoading.value = false
  }
}

async function loadApprovals() {
  try {
    const res = await approvalsApi.list(companyId.value, { status: 'pending', limit: 5 })
    pendingApprovals.value = res.data
  } catch {
    pendingApprovals.value = []
  } finally {
    approvalsLoading.value = false
  }
}

async function loadEmployees() {
  try {
    const res = await digitalEmployeesApi.list(companyId.value)
    employees.value = res.data
  } catch {
    employees.value = []
  } finally {
    employeesLoading.value = false
  }
}
</script>

<style scoped>
.stats-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

@media (max-width: 900px) {
  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 500px) {
  .stats-row {
    grid-template-columns: 1fr;
  }
}

.stat-card {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.stat-card__label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.stat-card__value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
  letter-spacing: -0.02em;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: var(--space-6);
}

@media (max-width: 1024px) {
  .dashboard-grid {
    grid-template-columns: 1fr;
  }
}

.dashboard-grid__side {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-4);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.approval-list,
.employee-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  list-style: none;
}

.approval-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-3);
  background: var(--surface-sunken);
  border-radius: var(--radius-md);
}

.approval-item__content {
  flex: 1;
  overflow: hidden;
}

.approval-item__title {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  text-transform: capitalize;
}

.approval-item__desc {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.employee-item {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.employee-item__avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-brand-100);
  color: var(--color-brand-600);
  font-size: var(--text-sm);
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.employee-item__info {
  flex: 1;
  overflow: hidden;
}

.employee-item__name {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
}

.employee-item__role {
  font-size: var(--text-xs);
  color: var(--text-secondary);
  text-transform: capitalize;
}
</style>
