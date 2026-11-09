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
    <n-tabs v-model:value="activeTab" type="segment" class="task-tabs" @update:value="changeFilter">
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
      <div v-if="total > 0" class="pagination-row"><span>共 {{ total }} 条</span><n-pagination v-if="total > pageSize" v-model:page="page" :page-size="pageSize" :item-count="total" @update:page="loadTasks" /></div>
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NTabs, NTab, NDataTable, NPagination, type DataTableColumns } from 'naive-ui'
import { AddOutline, FlashOutline, RefreshOutline, CloseOutline, CreateOutline, PlayOutline } from '@vicons/ionicons5'
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
const route = useRoute()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const activeTab = ref(route.query.tab === 'schedules' ? 'schedules' : 'all')
const runningNow = ref<string | null>(null)
const loading = ref(false)
const tasks = ref<OperationTask[]>([])
const error = ref('')
const page = ref(1), total = ref(0), pageSize = 20
let requestVersion = 0

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
      if (!schedule) return row.input_params?.manual_schedule_run ? '计划手动执行实例' : row.input_params?.schedule_template_id ? '定时执行实例' : '单次任务'
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
      h('div', { style: 'display:flex;gap:8px;flex-wrap:wrap' }, [
        row.input_params?.schedule && ['scheduled', 'paused'].includes(row.status)
          ? h(NButton, { size: 'small', onClick: (e: Event) => { e.stopPropagation(); router.push(`/tasks/new?edit_schedule_id=${row.id}`) } },
              { icon: () => h(CreateOutline), default: () => '编辑' })
          : null,
        row.input_params?.schedule && ['scheduled', 'paused'].includes(row.status)
          ? h(NButton, { size: 'small', type: 'primary', secondary: true, loading: runningNow.value === row.id, disabled: runningNow.value !== null, onClick: (e: Event) => { e.stopPropagation(); runNow(row) } },
              { icon: () => h(PlayOutline), default: () => '立刻执行' })
          : null,
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
function changeFilter() { page.value = 1; loadTasks() }

async function loadTasks() {
  const request = ++requestVersion
  loading.value = true
  error.value = ''
  try {
    const params = { page: page.value, limit: pageSize, ...(activeTab.value !== 'all' ? { status: activeTab.value } : {}) }
    const res = await tasksApi.list(companyId.value, params)
    if (request !== requestVersion) return
    total.value = res.total
    if (page.value > Math.max(1, Math.ceil(res.total / pageSize))) { page.value = Math.max(1, Math.ceil(res.total / pageSize)); await loadTasks(); return }
    tasks.value = res.data
  } catch {
    if (request !== requestVersion) return
    tasks.value = []
    error.value = '任务列表加载失败，请刷新重试。'
  } finally {
    if (request === requestVersion) loading.value = false
  }
}

async function toggleSchedule(task: OperationTask) {
  try {
    await tasksApi.setScheduleEnabled(companyId.value, task.id, task.status !== 'scheduled')
    await loadTasks()
  } catch { error.value = '定时计划更新失败，请重试。' }
}

async function runNow(task: OperationTask) {
  if (runningNow.value) return
  runningNow.value = task.id
  try {
    const result = await tasksApi.runScheduleNow(companyId.value, task.id)
    await loadTasks()
    await router.push(`/tasks/${result.data.id}`)
  } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '立即执行失败，请重试。' }
  finally { runningNow.value = null }
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
.pagination-row { display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-top:16px; color:var(--text-secondary); }
</style>
