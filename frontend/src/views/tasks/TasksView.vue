<template>
  <div>
    <AppPageHeader :title="t('Tasks')" :subtitle="t('Monitor and manage AI operation tasks')">
      <template #actions>
        <n-button type="primary" @click="router.push('/tasks/new')">
          <template #icon><AddOutline /></template>
          {{ t('New Task') }}
        </n-button>
      </template>
    </AppPageHeader>

    <!-- Status filter tabs -->
    <n-tabs v-model:value="activeTab" type="segment" class="task-tabs" @update:value="loadTasks">
      <n-tab name="all">{{ t('All') }}</n-tab>
      <n-tab name="schedules">定时计划</n-tab>
      <n-tab name="running">{{ t('Running') }}</n-tab>
      <n-tab name="pending">{{ t('Pending') }}</n-tab>
      <n-tab name="waiting_approval">待审批</n-tab>
      <n-tab name="queued">排队中</n-tab>
      <n-tab name="completed">{{ t('Completed') }}</n-tab>
      <n-tab name="failed">{{ t('Failed') }}</n-tab>
    </n-tabs>

    <AppCard style="margin-top: var(--space-4)">
      <p v-if="error" role="alert">{{ error }}</p>
      <template v-if="loading">
        <AppLoader variant="table" :rows="8" />
      </template>
      <template v-else-if="tasks.length === 0">
        <AppEmpty
          :icon="FlashOutline"
          :title="t('No tasks found')"
          :description="activeTab === 'all' ? t('Create your first task to get started') : t('No {status} tasks', { status: t(activeTab.charAt(0).toUpperCase() + activeTab.slice(1)) })"
        >
          <template v-if="activeTab === 'all'" #action>
            <n-button type="primary" @click="router.push('/employees')">
              {{ t('Browse employees') }}
            </n-button>
          </template>
        </AppEmpty>
      </template>
      <template v-else>
        <n-data-table
          :scroll-x="1100"
          :columns="columns"
          :data="tasks"
          :bordered="false"
          :row-props="rowProps"
        />
      </template>
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { NButton, NTabs, NTab, NDataTable, type DataTableColumns } from 'naive-ui'
import { AddOutline, FlashOutline, RefreshOutline, CloseOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { tasksApi } from '@/api/tasks'
import type { OperationTask, TaskSchedule } from '@/types/task'

const { t, locale } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const activeTab = ref('all')
const loading = ref(false)
const tasks = ref<OperationTask[]>([])
const error = ref('')

const columns = computed<DataTableColumns<OperationTask>>(() => [
  {
    title: t('Title'),
    key: 'title',
    ellipsis: { tooltip: true },
  },
  {
    title: t('Type'),
    key: 'task_type',
    render: (row) => row.task_type.replace(/_/g, ' '),
  },
  {
    title: '定时 / 下次执行',
    key: 'schedule',
    render: row => {
      const schedule = row.input_params?.schedule as TaskSchedule | undefined
      if (!schedule) return row.input_params?.schedule_template_id ? '定时执行实例' : '单次任务'
      return `${schedule.frequency === 'daily' ? '每天' : '每周'} ${schedule.time} · ${row.status === 'scheduled' && schedule.next_run_at ? new Date(schedule.next_run_at).toLocaleString(locale.value) : '已暂停'}`
    },
  },
  {
    title: t('Status'),
    key: 'status',
    render: (row) => h(AppBadge, { color: statusColor(row.status), dot: true }, { default: () => t(statusLabel(row.status)) }),
  },
  {
    title: t('Cost'),
    key: 'cost_usd',
    render: (row) => (row.cost_usd != null ? `$${row.cost_usd.toFixed(4)}` : '—'),
  },
  {
    title: t('Created'),
    key: 'created_at',
    render: (row) => new Date(row.created_at).toLocaleString(locale.value),
  },
  {
    title: t('Actions'),
    key: 'actions',
    render: (row) =>
      h('div', { style: 'display:flex;gap:8px' }, [
        row.input_params?.schedule
          ? h(NButton, { size: 'small', onClick: (e: Event) => { e.stopPropagation(); toggleSchedule(row) } },
              { default: () => row.status === 'scheduled' ? '暂停计划' : '恢复计划' })
          : null,
        row.status === 'failed'
          ? h(NButton, { size: 'small', onClick: (e: Event) => { e.stopPropagation(); retryTask(row) } },
              { icon: () => h(RefreshOutline), default: () => t('Retry') })
          : null,
        ['running', 'pending', 'queued', 'waiting_approval'].includes(row.status)
          ? h(NButton, { size: 'small', type: 'error', ghost: true, onClick: (e: Event) => { e.stopPropagation(); cancelTask(row) } },
              { icon: () => h(CloseOutline), default: () => t('Cancel') })
          : null,
      ]),
  },
])

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: 'Pending', running: 'Running', completed: 'Completed', failed: 'Failed',
    scheduled: '定时执行中', paused: '计划已暂停',
    cancelled: 'Cancelled', waiting_approval: '待审批', queued: '排队中',
  }
  return labels[status] ?? status
}

function statusColor(status: string): 'info' | 'success' | 'danger' | 'warning' | 'default' {
  const colors: Record<string, 'info' | 'success' | 'danger' | 'warning' | 'default'> = {
    running: 'info', completed: 'success', failed: 'danger', waiting_approval: 'warning',
  }
  return colors[status] ?? 'default'
}

function rowProps(row: OperationTask) {
  return {
    style: 'cursor:pointer',
    onClick: () => router.push(`/tasks/${row.id}`),
  }
}

onMounted(() => loadTasks())

async function loadTasks() {
  loading.value = true
  error.value = ''
  try {
    const params = activeTab.value !== 'all' ? { status: activeTab.value } : {}
    const res = await tasksApi.list(companyId.value, params)
    tasks.value = res.data
  } catch {
    tasks.value = []
    error.value = '任务列表加载失败，请刷新重试。'
  } finally {
    loading.value = false
  }
}

async function toggleSchedule(task: OperationTask) {
  try {
    await tasksApi.setScheduleEnabled(companyId.value, task.id, task.status !== 'scheduled')
    await loadTasks()
  } catch { error.value = '定时计划更新失败，请重试。' }
}

async function retryTask(task: OperationTask) {
  await tasksApi.retry(companyId.value, task.id)
  await loadTasks()
}

async function cancelTask(task: OperationTask) {
  await tasksApi.cancel(companyId.value, task.id)
  await loadTasks()
}
</script>

<style scoped>
.task-tabs {
  margin-bottom: 0;
}
</style>
