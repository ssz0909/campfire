<template>
  <div>
    <AppPageHeader :title="t('Analytics')" :subtitle="t('Operational metrics and insights')" />

    <div class="analytics-grid">
      <!-- Overview stats -->
      <div class="stats-row">
        <AppCard v-for="stat in overviewStats" :key="stat.label" class="stat-card">
          <template v-if="statsLoading">
            <AppLoader variant="stat" />
          </template>
          <template v-else>
            <p class="stat-card__label">{{ t(stat.label) }}</p>
            <p class="stat-card__value">{{ stat.value }}</p>
          </template>
        </AppCard>
      </div>

      <!-- Task completion -->
      <AppCard class="full-width">
        <h2 class="section-title">{{ t('Task Completion') }}</h2>
        <template v-if="statsLoading">
          <AppLoader variant="table" :rows="3" />
        </template>
        <template v-else>
          <div class="metric-row">
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Completed') }}</span>
              <span class="metric-item__value metric-item__value--success">
                {{ taskStats.completed ?? '—' }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Running') }}</span>
              <span class="metric-item__value metric-item__value--info">
                {{ taskStats.running ?? '—' }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Failed') }}</span>
              <span class="metric-item__value metric-item__value--danger">
                {{ taskStats.failed ?? '—' }}
              </span>
            </div>
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Avg Duration') }}</span>
              <span class="metric-item__value">
                {{ taskStats.avg_duration_seconds != null
                   ? `${taskStats.avg_duration_seconds}s`
                   : '—' }}
              </span>
            </div>
          </div>
        </template>
      </AppCard>

      <!-- Order metrics -->
      <AppCard>
        <h2 class="section-title">{{ t('Order Metrics') }}</h2>
        <template v-if="ordersLoading">
          <AppLoader variant="table" :rows="3" />
        </template>
        <template v-else-if="ordersError">
          <AppEmpty :icon="CartOutline" :title="t('Data not available')" :description="ordersError" />
        </template>
        <template v-else-if="!orderMetrics || orderMetrics.status === 'NOT_CONNECTED'">
          <AppEmpty
            :icon="CartOutline"
            :title="t('Hotel connector not set up')"
            :description="orderMetrics?.message || t('Connect a store to see order metrics')"
          >
            <template #action>
              <router-link to="/connectors">{{ t('Set up a connector') }}</router-link>
            </template>
          </AppEmpty>
        </template>
        <template v-else-if="orderMetrics.status === 'NO_DATA'">
          <AppEmpty
            :icon="CartOutline"
            :title="t('Data not available')"
            :description="orderMetrics.message || t('Insufficient data')"
          />
          <p v-if="orderMetrics.last_sync_at" class="order-meta">
            {{ t('Last sync: {time}', { time: formatDateTime(orderMetrics.last_sync_at, locale) }) }}
          </p>
        </template>
        <template v-else-if="orderMetrics.metrics">
          <div class="metric-row">
            <div v-for="kpi in orderKpis" :key="kpi.key" class="metric-item">
              <span class="metric-item__label">{{ kpi.label }}</span>
              <span :class="['metric-item__value', { 'metric-item__value--insufficient': kpi.value === null }]">
                {{ kpi.value ?? t('Insufficient data') }}
              </span>
              <span v-if="kpi.note" class="metric-item__note">{{ kpi.note }}</span>
            </div>
          </div>
          <p v-if="orderMetrics.last_sync_at" class="order-meta">
            {{ t('Last sync: {time}', { time: formatDateTime(orderMetrics.last_sync_at, locale) }) }}
          </p>
          <details v-if="definitionEntries.length" class="definitions">
            <summary>{{ t('Definitions') }}</summary>
            <dl>
              <div v-for="[key, text] in definitionEntries" :key="key">
                <dt>{{ definitionLabel(key) }}</dt>
                <dd>{{ text }}</dd>
              </div>
            </dl>
          </details>
        </template>
      </AppCard>

      <!-- Content metrics -->
      <AppCard>
        <h2 class="section-title">{{ t('Content Output') }}</h2>
        <template v-if="contentLoading">
          <AppLoader variant="table" :rows="3" />
        </template>
        <template v-else-if="!contentMetrics">
          <AppEmpty
            :icon="DocumentTextOutline"
            :title="t('Data not available')"
            :description="t('Run content generation tasks to see output metrics')"
          />
        </template>
        <template v-else>
          <div class="metric-row">
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Posts Created') }}</span>
              <span class="metric-item__value">{{ contentMetrics.posts_created }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Videos Created') }}</span>
              <span class="metric-item__value">{{ contentMetrics.videos_created }}</span>
            </div>
            <div class="metric-item">
              <span class="metric-item__label">{{ t('Words Generated') }}</span>
              <span class="metric-item__value">{{ contentMetrics.words_generated.toLocaleString() }}</span>
            </div>
          </div>
        </template>
      </AppCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import { CartOutline, DocumentTextOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import { useAuthStore } from '@/stores/auth'
import { analyticsApi } from '@/api/analytics'
import { formatDateTime, formatMoney, formatPercent } from '@/utils/format'
import type { OrderMetrics, ContentMetrics } from '@/types/analytics'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const statsLoading = ref(true)
const ordersLoading = ref(true)
const ordersError = ref<string | null>(null)
const contentLoading = ref(true)

const overview = ref<Record<string, number>>({})
const taskStats = ref<Record<string, number>>({})
const orderMetrics = ref<OrderMetrics | null>(null)
const contentMetrics = ref<ContentMetrics | null>(null)

const overviewStats = computed(() => [
  { label: t('Active Tasks'), value: overview.value.active_tasks ?? '—' },
  { label: t('Active Employees'), value: overview.value.active_employees ?? '—' },
  { label: t('Videos This Month'), value: overview.value.videos_this_month ?? '—' },
  { label: t('Completed Today'), value: overview.value.tasks_completed_today ?? '—' },
])

interface Kpi {
  key: string
  label: string
  value: string | null
  note?: string
}

const orderKpis = computed<Kpi[]>(() => {
  const m = orderMetrics.value?.metrics
  if (!m) return []
  const num = (v: number | null | undefined) => (v == null ? null : v.toLocaleString())
  const pct = (v: number | null | undefined) => (v == null ? null : formatPercent(v))
  // The analytics contract carries no currency, so none is assumed or displayed.
  const money = (v: number | null | undefined) => (v == null ? null : formatMoney(v))
  return [
    { key: 'total_orders', label: t('Total Orders'), value: num(m.total_orders) },
    { key: 'cancellation_rate', label: t('Cancellation rate'), value: pct(m.cancellation_rate) },
    { key: 'room_nights', label: t('Room nights'), value: num(m.room_nights) },
    { key: 'revenue', label: t('Revenue'), value: money(m.revenue) },
    { key: 'adr', label: t('ADR (avg. nightly rate)'), value: money(m.average_room_nightly_rate) },
    {
      key: 'occupancy_rate',
      label: t('Occupancy rate'),
      value: pct(m.occupancy_rate),
      note: m.occupancy_rate == null ? (m.occupancy_note ?? undefined) : undefined,
    },
    {
      key: 'lead_time',
      label: t('Avg. lead time'),
      value:
        m.average_lead_time_days == null
          ? null
          : t('{n} days', { n: Math.round(m.average_lead_time_days * 10) / 10 }),
    },
  ]
})

const definitionEntries = computed(() => Object.entries(orderMetrics.value?.definitions ?? {}))

function definitionLabel(key: string): string {
  const labels: Record<string, string> = {
    scope: t('Scope'),
    revenue: t('Revenue'),
    room_nights: t('Room nights'),
    average_room_nightly_rate: t('ADR (avg. nightly rate)'),
    occupancy_rate: t('Occupancy rate'),
    cancellation_rate: t('Cancellation rate'),
    average_lead_time_days: t('Avg. lead time'),
  }
  return labels[key] ?? key
}

onMounted(async () => {
  await Promise.allSettled([
    loadOverview(),
    loadTaskStats(),
    loadOrders(),
    loadContent(),
  ])
})

async function loadOverview() {
  try {
    const res = await analyticsApi.overview(companyId.value)
    overview.value = res.data as unknown as Record<string, number>
  } catch {
    // defaults
  } finally {
    statsLoading.value = false
  }
}

async function loadTaskStats() {
  try {
    const res = await analyticsApi.tasks(companyId.value)
    taskStats.value = res.data as unknown as Record<string, number>
  } catch {
    // defaults
  }
}

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = null
  try {
    const res = await analyticsApi.orders(companyId.value)
    orderMetrics.value = res.data
  } catch (e) {
    orderMetrics.value = null
    const status = (e as { response?: { status?: number } })?.response?.status
    ordersError.value =
      status === 403
        ? t('You do not have permission to view order analytics.')
        : t('Could not load order metrics.')
  } finally {
    ordersLoading.value = false
  }
}

async function loadContent() {
  contentLoading.value = true
  try {
    const res = await analyticsApi.content(companyId.value)
    contentMetrics.value = res.data
  } catch {
    contentMetrics.value = null
  } finally {
    contentLoading.value = false
  }
}
</script>

<style scoped>
.analytics-grid {
  display: grid;
  gap: var(--space-4);
  grid-template-columns: repeat(2, 1fr);
}

.stats-row {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-4);
}

@media (max-width: 900px) {
  .analytics-grid {
    grid-template-columns: 1fr;
  }

  .stats-row {
    grid-template-columns: repeat(2, 1fr);
  }
}

.full-width {
  grid-column: 1 / -1;
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
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-4);
}

.section-notice {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-bottom: var(--space-4);
}

.metric-row {
  display: flex;
  gap: var(--space-8);
  flex-wrap: wrap;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.metric-item__label {
  font-size: var(--text-xs);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.metric-item__value {
  font-size: var(--text-2xl);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.metric-item__value--insufficient {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-muted);
}

.metric-item__note {
  font-size: var(--text-xs);
  color: var(--text-muted);
  max-width: 220px;
}

.order-meta {
  margin-top: var(--space-4);
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.definitions {
  margin-top: var(--space-3);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.definitions summary {
  cursor: pointer;
  font-weight: 600;
}

.definitions dl {
  margin-top: var(--space-2);
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.definitions dt {
  font-weight: 600;
  color: var(--text-primary);
}

.metric-item__value--success { color: var(--color-success); }
.metric-item__value--info    { color: var(--color-info); }
.metric-item__value--danger  { color: var(--color-danger); }
</style>
