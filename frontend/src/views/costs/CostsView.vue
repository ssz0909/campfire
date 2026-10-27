<template>
  <div>
    <AppPageHeader :title="t('Costs')" :subtitle="t('Usage and spending overview')">
      <template #actions>
        <n-select
          v-model:value="period"
          :options="periodOptions"
          style="width: 160px"
          @update:value="loadCosts"
        />
      </template>
    </AppPageHeader>

    <!-- Usage bars -->
    <AppCard class="usage-card">
      <h2 class="section-title">{{ t('Usage Summary') }}</h2>
      <template v-if="summaryLoading">
        <AppLoader variant="card" />
      </template>
      <template v-else-if="usage">
        <div class="usage-bars">
          <div class="usage-bar-item">
            <div class="usage-bar-item__labels">
               <span class="usage-bar-item__label">{{ t('Tasks') }}</span>
              <span class="usage-bar-item__value">
                {{ usage.tasks_used }} / {{ usage.tasks_quota }}
              </span>
            </div>
          <div class="usage-bar" role="progressbar" :aria-label="t('Tasks')" :aria-valuenow="taskPct" aria-valuemin="0" aria-valuemax="100">
              <div class="usage-bar__fill" :style="{ width: `${taskPct}%` }" :class="{ 'usage-bar__fill--warn': taskPct > 80 }" />
            </div>
          </div>

          <div class="usage-bar-item">
            <div class="usage-bar-item__labels">
               <span class="usage-bar-item__label">{{ t('Videos') }}</span>
              <span class="usage-bar-item__value">
                {{ usage.videos_used }} / {{ usage.videos_quota }}
              </span>
            </div>
            <div class="usage-bar" role="progressbar" :aria-label="t('Videos')" :aria-valuenow="videoPct" aria-valuemin="0" aria-valuemax="100">
              <div class="usage-bar__fill" :style="{ width: `${videoPct}%` }" :class="{ 'usage-bar__fill--warn': videoPct > 80 }" />
            </div>
          </div>

          <div class="usage-bar-item">
            <div class="usage-bar-item__labels">
               <span class="usage-bar-item__label">{{ t('Storage') }}</span>
              <span class="usage-bar-item__value">
                {{ usage.storage_used_gb.toFixed(2) }} GB / {{ usage.storage_quota_gb }} GB
              </span>
            </div>
            <div class="usage-bar" role="progressbar" :aria-label="t('Storage')" :aria-valuenow="storagePct" aria-valuemin="0" aria-valuemax="100">
              <div class="usage-bar__fill" :style="{ width: `${storagePct}%` }" :class="{ 'usage-bar__fill--warn': storagePct > 80 }" />
            </div>
          </div>
        </div>

        <div class="usage-spend">
           <span class="usage-spend__label">{{ t('Current period spend') }}</span>
          <span class="usage-spend__value">
            ${{ usage.current_period_cost_usd.toFixed(2) }}
            <span v-if="usage.budget_usd" class="usage-spend__budget">
              {{ t('of {budget} budget', { budget: `$${usage.budget_usd.toFixed(2)}` }) }}
            </span>
          </span>
        </div>
      </template>
    </AppCard>

    <!-- Cost breakdown (CSS bar chart) -->
    <AppCard style="margin-top: var(--space-4)">
      <h2 class="section-title">{{ t('Cost by Period') }}</h2>
      <template v-if="costsLoading">
        <AppLoader variant="table" :rows="4" />
      </template>
      <template v-else-if="costs.length === 0">
        <AppEmpty :icon="CardOutline" :title="t('No cost records')" :description="t('Cost records appear after your first billing period.')" />
      </template>
      <template v-else>
        <!-- Simple CSS bar chart -->
         <div class="cost-chart" :aria-label="t('Cost per period bar chart')">
          <div
            v-for="record in costs.slice(0, 8)"
            :key="record.id"
            class="cost-chart__bar-group"
          >
            <div
              class="cost-chart__bar"
              :style="{ height: `${barHeight(record.total_cost_usd)}px` }"
              :aria-label="t('Cost for period {period}: ${cost}', { period: formatPeriod(record.period_start), cost: record.total_cost_usd.toFixed(2) })"
              role="img"
            />
            <span class="cost-chart__label">{{ formatPeriod(record.period_start) }}</span>
          </div>
        </div>

        <!-- Cost table -->
        <n-data-table
          :columns="costColumns"
          :data="costs"
          :bordered="false"
          size="small"
          style="margin-top: var(--space-6)"
        />
      </template>
    </AppCard>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted, h } from 'vue'
import { NSelect, NDataTable, type DataTableColumns } from 'naive-ui'
import { CardOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import { useAuthStore } from '@/stores/auth'
import { costsApi } from '@/api/costs'
import type { CostRecord, UsageSummary } from '@/types/cost'

const { t } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const summaryLoading = ref(true)
const costsLoading = ref(true)
const period = ref('current')
const usage = ref<UsageSummary | null>(null)
const costs = ref<CostRecord[]>([])

const periodOptions = computed(() => [
  { label: t('Current Period'), value: 'current' },
  { label: t('Last 3 Months'), value: '3m' },
  { label: t('Last 6 Months'), value: '6m' },
])

const taskPct = computed(() =>
  usage.value ? Math.min(100, (usage.value.tasks_used / usage.value.tasks_quota) * 100) : 0,
)
const videoPct = computed(() =>
  usage.value ? Math.min(100, (usage.value.videos_used / usage.value.videos_quota) * 100) : 0,
)
const storagePct = computed(() =>
  usage.value ? Math.min(100, (usage.value.storage_used_gb / usage.value.storage_quota_gb) * 100) : 0,
)

const maxCost = computed(() =>
  Math.max(...costs.value.map((c) => c.total_cost_usd), 0.01),
)

function barHeight(cost: number) {
  return Math.max(4, (cost / maxCost.value) * 120)
}

function formatPeriod(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getFullYear().toString().slice(2)}`
}

const costColumns = computed<DataTableColumns<CostRecord>>(() => [
  {
    title: t('Period'),
    key: 'period_start',
    render: (row) => formatPeriod(row.period_start),
  },
  {
    title: t('Tasks'),
    key: 'task_cost_usd',
    render: (row) => `$${row.task_cost_usd.toFixed(4)}`,
  },
  {
    title: t('Videos'),
    key: 'video_cost_usd',
    render: (row) => `$${row.video_cost_usd.toFixed(4)}`,
  },
  {
    title: t('Models'),
    key: 'model_cost_usd',
    render: (row) => `$${row.model_cost_usd.toFixed(4)}`,
  },
  {
    title: t('Storage'),
    key: 'storage_cost_usd',
    render: (row) => `$${row.storage_cost_usd.toFixed(4)}`,
  },
  {
    title: t('Total'),
    key: 'total_cost_usd',
    render: (row) => h('strong', `$${row.total_cost_usd.toFixed(4)}`),
  },
])

onMounted(async () => {
  await Promise.allSettled([loadSummary(), loadCosts()])
})

async function loadSummary() {
  summaryLoading.value = true
  try {
    const res = await costsApi.usage(companyId.value)
    usage.value = res.data
  } catch {
    usage.value = null
  } finally {
    summaryLoading.value = false
  }
}

async function loadCosts() {
  costsLoading.value = true
  try {
    const res = await costsApi.list(companyId.value)
    costs.value = res.data
  } catch {
    costs.value = []
  } finally {
    costsLoading.value = false
  }
}
</script>

<style scoped>
.usage-card {
  margin-bottom: var(--space-4);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}

.usage-bars {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.usage-bar-item__labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: var(--space-1);
}

.usage-bar-item__label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.usage-bar-item__value {
  font-size: var(--text-sm);
  font-weight: 500;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.usage-bar {
  height: 8px;
  background: var(--color-neutral-100);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.usage-bar__fill {
  height: 100%;
  background: var(--color-brand-500);
  border-radius: var(--radius-sm);
  transition: width var(--duration-slow) var(--ease-standard);
}

.usage-bar__fill--warn {
  background: var(--color-warning);
}

.usage-spend {
  display: flex;
  align-items: baseline;
  gap: var(--space-3);
  margin-top: var(--space-6);
  padding-top: var(--space-4);
  border-top: 1px solid var(--border-default);
}

.usage-spend__label {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.usage-spend__value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.usage-spend__budget {
  font-size: var(--text-sm);
  font-weight: 400;
  color: var(--text-muted);
}

.cost-chart {
  display: flex;
  align-items: flex-end;
  gap: var(--space-3);
  height: 140px;
  padding: var(--space-2) 0;
}

.cost-chart__bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-1);
  flex: 1;
}

.cost-chart__bar {
  width: 100%;
  background: var(--color-brand-300);
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  transition: background var(--duration-fast);
  min-height: 4px;
}

.cost-chart__bar:hover {
  background: var(--color-brand-500);
}

.cost-chart__label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}
</style>
