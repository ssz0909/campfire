<template>
  <div>
    <AppPageHeader :title="t('Connectors')" :subtitle="t('Connect external services and data sources')" />

    <AppLoader v-if="loading" variant="card" />

    <AppCard v-else-if="forbidden">
      <AppEmpty
        :icon="LockClosedOutline"
        :title="t('Permission denied')"
        :description="t('You do not have permission to view or manage connectors. Ask a company admin for access.')"
      />
    </AppCard>

    <AppCard v-else-if="loadError">
      <AppEmpty :icon="AlertCircleOutline" :title="t('Could not load the connector')" :description="loadError">
        <template #action>
          <n-button @click="loadAll">{{ t('Retry') }}</n-button>
        </template>
      </AppEmpty>
    </AppCard>

    <div v-else-if="connector" class="connector-stack">
      <AppCard class="connector-card">
        <!-- (a) status header -->
        <div class="connector-card__header">
          <div class="connector-card__icon">
            <BusinessOutline aria-hidden="true" />
          </div>
          <div class="connector-card__info">
            <h3 class="connector-card__name">{{ t('Hotel order connector') }}</h3>
            <p class="connector-card__desc">{{ t('Sync hotel orders from your order platform store') }}</p>
            <p v-if="connector.hotel_name || connector.room_count != null" class="connector-card__meta">
              <span v-if="connector.hotel_name">{{ connector.hotel_name }}</span>
              <span v-if="connector.room_count != null">{{ t('{n} rooms', { n: connector.room_count }) }}</span>
            </p>
          </div>
          <AppBadge :color="statusColor" dot>{{ statusLabel }}</AppBadge>
        </div>

        <!-- (b) credentials form -->
        <div class="connector-card__actions" style="margin-bottom: 16px">
          <n-button type="primary" @click="showDddLogin = true">{{ connector.web_session_active ? '重新登录订单来了' : '账号密码连接订单来了' }}</n-button>
            <n-button v-if="connector.web_session_active" secondary type="error" :loading="loggingOut" @click="logoutHotel">退出订单来了</n-button>
          <span v-if="connector.connection_mode === 'web'" class="muted">Web 会话已加密保存 · 数据来自所选门店</span>
        </div>
        <n-form v-if="connector.connection_mode !== 'web'" label-placement="top" class="connector-card__form" @submit.prevent="save">
          <n-form-item
            :label="t('Hotel number')"
            :validation-status="hotelNumError ? 'error' : undefined"
            :feedback="hotelNumError ?? undefined"
          >
            <n-input-number
              v-model:value="form.hotelNum"
              :show-button="false"
              :min="1"
              :precision="0"
              :placeholder="t('Enter the hotel number')"
              :aria-label="t('Hotel number')"
              style="width: 100%"
              @update:value="hotelNumError = null"
            />
          </n-form-item>
          <n-form-item
            :label="t('Access Token')"
            :validation-status="tokenError ? 'error' : undefined"
            :feedback="tokenError ?? tokenHint"
          >
            <div class="token-field-row">
              <n-input
                v-model:value="form.token"
                type="password"
                show-password-on="mousedown"
                :placeholder="tokenPlaceholder"
                :aria-label="t('Access Token')"
                autocomplete="off"
                style="flex: 1"
                @update:value="tokenError = null"
              />
              <n-button
                secondary
                size="small"
                style="flex-shrink: 0; white-space: nowrap"
                @click="showDddLogin = true"
              >
                账号登录并选择门店
              </n-button>
            </div>
          </n-form-item>
        </n-form>

        <DingdandaoLoginModal
          :show="showDddLogin"
          :company-id="companyId"
          @close="showDddLogin = false"
          @success="onDddLoginSuccess"
        />

        <p v-if="saveError" class="notice notice--fail" role="alert">{{ saveError }}</p>
        <p v-else-if="saveSuccess" class="notice notice--ok" role="status">{{ t('Connector settings saved.') }}</p>

        <div class="connector-card__actions">
          <div class="connector-card__sync-status">
            <span v-if="connector.last_connect_at" class="muted">
              {{ t('Last connected: {time}', { time: formatDateTime(connector.last_connect_at, locale) }) }}
            </span>
          </div>
          <div class="connector-card__buttons">
            <!-- (c) test connection -->
            <n-button :loading="testing" :disabled="!connector.configured || saving" @click="testConnection">
              {{ t('Test connection') }}
            </n-button>
            <n-button v-if="connector.connection_mode !== 'web'" type="primary" :loading="saving" :disabled="testing" @click="save">
              {{ t('Save') }}
            </n-button>
          </div>
        </div>

        <div v-if="testing" class="notice notice--info" role="status">
          {{ t('Contacting the platform, this may take a few seconds...') }}
        </div>
        <div
          v-else-if="testResult"
          :class="['notice', testResult.connected ? 'notice--ok' : 'notice--fail']"
          :role="testResult.connected ? 'status' : 'alert'"
        >
          <p>{{ testResult.message }}</p>
          <p v-if="testResult.connected && hasTestDetails" class="notice__details">
            <span v-if="testResult.hotel_name">{{ testResult.hotel_name }}</span>
            <span v-if="testResult.room_type_count != null">
              {{ t('{n} room types', { n: testResult.room_type_count }) }}
            </span>
            <span v-if="testResult.room_count != null">{{ t('{n} rooms', { n: testResult.room_count }) }}</span>
          </p>
        </div>
        <p v-else-if="testError" class="notice notice--fail" role="alert">{{ testError }}</p>

        <n-divider />

        <!-- (d) sync panel -->
        <section class="sync-panel" :aria-label="t('Order sync')">
          <h4 class="section-title">{{ t('Order sync') }}</h4>
          <div class="sync-panel__controls">
            <n-date-picker
              v-model:value="syncRange"
              type="daterange"
              :is-date-disabled="isDateDisabled"
              :clearable="false"
              :disabled="!connector.configured"
              :aria-label="t('Sync date range')"
            />
            <n-button
              type="primary"
              :loading="starting"
              :disabled="!connector.configured || jobActive || !syncRange"
              @click="startSync"
            >
              {{ t('Sync orders') }}
            </n-button>
          </div>
          <p class="muted">{{ connector.connection_mode === 'web' ? 'Web 连接器可按历史日期查询，实际可用范围以平台返回为准；数据分析员可按任务区间自动补同步。' : t('Only orders from the last 90 days can be synced.') }}</p>
          <p v-if="!connector.configured" class="muted">{{ t('Save the hotel number and token before syncing.') }}</p>
          <p v-if="syncError" class="notice notice--fail" role="alert">{{ syncError }}</p>

          <div v-if="latestJob" class="job">
            <div class="job__head">
              <StatusBadge :status="latestJob.status" />
              <span v-if="latestJob.begin_date && latestJob.end_date" class="muted">
                {{ latestJob.begin_date }} – {{ latestJob.end_date }}
              </span>
              <span v-if="jobActive" class="muted">{{ t('Syncing, refreshing every 2 seconds...') }}</span>
            </div>
            <n-progress
              v-if="jobActive && latestJob.orders_found > 0"
              type="line"
              :percentage="jobPercent"
              :show-indicator="false"
              :height="6"
            />
            <dl class="job__counts">
              <div>
                <dt>{{ t('Found') }}</dt>
                <dd>{{ latestJob.orders_found }}</dd>
              </div>
              <div>
                <dt>{{ t('Synced') }}</dt>
                <dd>{{ latestJob.orders_synced }}</dd>
              </div>
              <div>
                <dt>{{ t('Failed') }}</dt>
                <dd>{{ latestJob.orders_failed }}</dd>
              </div>
            </dl>
            <p v-if="latestJob.error" class="notice notice--fail" role="alert">{{ latestJob.error }}</p>
          </div>

          <div class="last-sync">
            <template v-if="connector.last_sync_at">
              <span class="muted">
                {{ t('Last sync: {time}', { time: formatDateTime(connector.last_sync_at, locale) }) }}
              </span>
              <StatusBadge v-if="connector.last_sync_status" :status="connector.last_sync_status" />
              <span v-if="connector.last_sync_stats" class="muted">
                {{ t('Found {found} · Synced {synced} · Failed {failed}', connector.last_sync_stats) }}
              </span>
            </template>
            <span v-else class="muted">{{ t('Never synced') }}</span>
          </div>
          <p v-if="connector.last_sync_error" class="notice notice--fail" role="alert">
            {{ connector.last_sync_error }}
          </p>
        </section>

        <n-divider />

        <!-- (f) push note -->
        <p class="push-note">
          <InformationCircleOutline aria-hidden="true" />
          <span v-if="connector.connection_mode === 'web'">Web 连接支持手动同步和数据分析任务补同步；会话过期后请重新登录。订单金额与财务实收分别展示。</span>
          <span v-else>{{ t('New orders also arrive automatically through platform push callbacks. No setup is needed here.') }}</span>
        </p>
      </AppCard>

      <!-- (e) synced orders -->
      <AppCard>
        <h4 class="section-title">{{ t('Synced orders') }}</h4>
        <AppLoader v-if="ordersLoading && !orders.length" variant="table" :rows="4" />
        <p v-else-if="ordersError" class="notice notice--fail" role="alert">{{ ordersError }}</p>
        <AppEmpty
          v-else-if="!orders.length"
          :icon="DocumentTextOutline"
          :title="t('No synced orders yet. Configure the connector and sync first.')"
        />
        <n-data-table
          v-else
          remote
          size="small"
          :bordered="false"
          :columns="orderColumns"
          :data="orders"
          :loading="ordersLoading"
          :pagination="pagination"
          :row-key="(row: HotelOrder) => row.order_num"
          :scroll-x="900"
        />
      </AppCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, h, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  NButton,
  NDataTable,
  NDatePicker,
  NDivider,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NProgress,
  type DataTableColumns,
} from 'naive-ui'
import {
  AlertCircleOutline,
  BusinessOutline,
  DocumentTextOutline,
  InformationCircleOutline,
  LockClosedOutline,
} from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import DingdandaoLoginModal from '@/components/DingdandaoLoginModal.vue'
import { useAuthStore } from '@/stores/auth'
import { connectorsApi } from '@/api/connectors'
import { apiErrorDetail, apiErrorStatus, formatDateTime, formatMoney, EMPTY_VALUE } from '@/utils/format'
import type {
  ConnectorStatus,
  HotelConnector,
  HotelOrder,
  HotelSyncJob,
  HotelTestResult,
} from '@/types/connector'

const { t, locale } = useI18n()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const PAGE_SIZE = 20
const POLL_INTERVAL_MS = 2000
const MAX_SYNC_DAYS_BACK = 90

const loading = ref(true)
const forbidden = ref(false)
const loadError = ref<string | null>(null)
const connector = ref<HotelConnector | null>(null)

// Form
const form = reactive<{ hotelNum: number | null; token: string }>({ hotelNum: null, token: '' })
const hotelNumError = ref<string | null>(null)
const tokenError = ref<string | null>(null)
const saving = ref(false)
const saveError = ref<string | null>(null)
const saveSuccess = ref(false)

// Dingdandao web login modal
const showDddLogin = ref(false)
const loggingOut = ref(false)

async function logoutHotel() {
  if (loggingOut.value) return
  loggingOut.value = true
  try {
    await connectorsApi.logoutHotel(companyId.value)
    await loadAll()
  } finally {
    loggingOut.value = false
  }
}

async function onDddLoginSuccess() {
  showDddLogin.value = false
  form.token = ''
  await loadAll()
}

// Test
const testing = ref(false)
const testResult = ref<HotelTestResult | null>(null)
const testError = ref<string | null>(null)

// Sync
const jobs = ref<HotelSyncJob[]>([])
const starting = ref(false)
const syncError = ref<string | null>(null)
let pollTimer: ReturnType<typeof setInterval> | null = null
let pollInFlight = false

// Orders
const orders = ref<HotelOrder[]>([])
const ordersTotal = ref(0)
const ordersPage = ref(1)
const ordersLoading = ref(false)
const ordersError = ref<string | null>(null)

function daysAgo(n: number): number {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() - n)
  return d.getTime()
}

function toYmd(ts: number): string {
  const d = new Date(ts)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

const syncRange = ref<[number, number] | null>([daysAgo(30), daysAgo(0)])

function isDateDisabled(ts: number): boolean {
  return (connector.value?.connection_mode !== 'web' && ts < daysAgo(MAX_SYNC_DAYS_BACK)) || ts > daysAgo(0)
}

const statusColor = computed<'default' | 'info' | 'success' | 'danger'>(() => {
  const map: Record<ConnectorStatus, 'default' | 'info' | 'success' | 'danger'> = {
    unconfigured: 'default',
    configured: 'info',
    connected: 'success',
    error: 'danger',
  }
  return map[connector.value?.status ?? 'unconfigured'] ?? 'default'
})

const statusLabel = computed(() => {
  const map: Record<ConnectorStatus, string> = {
    unconfigured: 'Not configured',
    configured: 'Configured',
    connected: 'Connected',
    error: 'Error',
  }
  const status = connector.value?.status ?? 'unconfigured'
  return t(map[status] ?? status)
})

const tokenHint = computed(() => {
  const c = connector.value
  if (!c) return undefined
  if (c.token_mode === 'auto') {
    return c.token_expires_at
      ? t('Token is managed automatically and renews itself. Current token expires: {time}', {
          time: formatDateTime(c.token_expires_at, locale.value),
        })
      : t('Token is managed automatically and renews itself.')
  }
  if (c.token_mode === 'manual') return t('Leave blank to keep the current token.')
  return c.auto_token_available
    ? t('Optional. Leave blank to obtain the token automatically.')
    : t('Enter the access token')
})

const tokenPlaceholder = computed(() =>
  connector.value?.configured && connector.value.auth_access_token
    ? connector.value.auth_access_token
    : t('Enter the access token'),
)

const hasTestDetails = computed(() => {
  const r = testResult.value
  return !!r && (!!r.hotel_name || r.room_type_count != null || r.room_count != null)
})

const latestJob = computed(() => jobs.value[0] ?? null)
const jobActive = computed(() => latestJob.value?.status === 'queued' || latestJob.value?.status === 'running')
const jobPercent = computed(() => {
  const j = latestJob.value
  if (!j || j.orders_found <= 0) return 0
  return Math.min(100, Math.round(((j.orders_synced + j.orders_failed) / j.orders_found) * 100))
})

function errorText(error: unknown, fallback: string, conflict?: string): string {
  const status = apiErrorStatus(error)
  if (status === 403) return t('You do not have permission to perform this action.')
  const detail = apiErrorDetail(error)
  if (status === 409) return detail ?? conflict ?? fallback
  if (status === 422) return detail ?? t('Please check the values you entered.')
  if (status == null) return t('Could not reach the server. Check your network and try again.')
  return detail ?? fallback
}

function applyConnector(data: HotelConnector) {
  connector.value = data
  form.hotelNum = data.hotel_num
  form.token = ''
}

async function loadConnector() {
  const res = await connectorsApi.getHotel(companyId.value)
  applyConnector(res.data)
}

async function loadAll() {
  loading.value = true
  loadError.value = null
  forbidden.value = false
  try {
    await loadConnector()
    await Promise.all([loadJobs(), connector.value?.configured ? loadOrders() : Promise.resolve()])
  } catch (e) {
    if (apiErrorStatus(e) === 403) forbidden.value = true
    else loadError.value = errorText(e, t('Failed to load connector settings.'))
  } finally {
    loading.value = false
  }
}

async function save() {
  if (saving.value) return
  hotelNumError.value = null
  tokenError.value = null
  saveError.value = null
  saveSuccess.value = false

  const hotelNum = form.hotelNum
  const token = form.token.trim()
  if (hotelNum == null || !Number.isInteger(hotelNum) || hotelNum <= 0) {
    hotelNumError.value = t('Enter a valid hotel number (positive integer).')
  }
  if (hotelNumError.value || tokenError.value || hotelNum == null) return

  saving.value = true
  try {
    const res = await connectorsApi.saveHotel(companyId.value, {
      hotel_num: hotelNum,
      ...(token ? { auth_access_token: token } : {}),
    })
    applyConnector(res.data)
    testResult.value = null
    testError.value = null
    saveSuccess.value = true
  } catch (e) {
    saveError.value = errorText(
      e,
      t('Failed to save connector settings.'),
      t('This store is already bound to another company.'),
    )
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testing.value = true
  testResult.value = null
  testError.value = null
  try {
    const res = await connectorsApi.testHotel(companyId.value)
    testResult.value = res.data
    await loadConnector().catch(() => undefined)
  } catch (e) {
    testError.value = errorText(e, t('Connection test failed.'))
  } finally {
    testing.value = false
  }
}

async function startSync() {
  if (!syncRange.value) return
  const [from, to] = syncRange.value
  starting.value = true
  syncError.value = null
  try {
    const res = await connectorsApi.syncHotel(companyId.value, {
      begin_date: toYmd(Math.min(from, to)),
      end_date: toYmd(Math.max(from, to)),
    })
    jobs.value = [res.data, ...jobs.value.filter((j) => j.id !== res.data.id)]
    startPolling()
  } catch (e) {
    syncError.value = errorText(
      e,
      t('Failed to start sync.'),
      t('Sync is unavailable: the connector is not configured or a sync is already running.'),
    )
  } finally {
    starting.value = false
  }
}

async function loadJobs() {
  const wasActive = jobActive.value
  const res = await connectorsApi.listSyncJobs(companyId.value, 10)
  jobs.value = res.data
  if (jobActive.value) {
    startPolling()
  } else {
    stopPolling()
    if (wasActive) {
      await Promise.all([loadConnector().catch(() => undefined), loadOrders()])
    }
  }
}

function startPolling() {
  if (pollTimer) return
  pollTimer = setInterval(async () => {
    if (pollInFlight) return
    pollInFlight = true
    try {
      await loadJobs()
    } catch {
      // keep polling; transient failures should not break progress display
    } finally {
      pollInFlight = false
    }
  }, POLL_INTERVAL_MS)
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
}

async function loadOrders() {
  ordersLoading.value = true
  ordersError.value = null
  try {
    const res = await connectorsApi.listOrders(companyId.value, {
      limit: PAGE_SIZE,
      offset: (ordersPage.value - 1) * PAGE_SIZE,
    })
    orders.value = res.data.orders
    ordersTotal.value = res.data.count
  } catch (e) {
    ordersError.value = errorText(e, t('Failed to load synced orders.'))
  } finally {
    ordersLoading.value = false
  }
}

function changePage(page: number) {
  ordersPage.value = page
  loadOrders()
}

const pagination = computed(() => ({
  page: ordersPage.value,
  pageSize: PAGE_SIZE,
  itemCount: ordersTotal.value,
  onUpdatePage: changePage,
}))

const orderColumns = computed<DataTableColumns<HotelOrder>>(() => [
  { title: t('Order number'), key: 'order_num', width: 170 },
  {
    title: t('Order status'),
    key: 'status_label',
    width: 110,
    render: (row) => h(AppBadge, null, () => row.status_label || row.status),
  },
  { title: t('Channel'), key: 'channel_name', render: (row) => row.channel_name || EMPTY_VALUE },
  {
    title: t('Amount'),
    key: 'actual_amount',
    align: 'right',
    render: (row) => formatMoney(row.actual_amount, row.currency),
  },
  {
    title: t('Room nights'),
    key: 'room_nights',
    align: 'right',
    render: (row) => (row.room_nights == null ? EMPTY_VALUE : String(row.room_nights)),
  },
  {
    title: t('Created'),
    key: 'order_created_at',
    width: 170,
    render: (row) => formatDateTime(row.order_created_at, locale.value),
  },
  {
    title: t('Check-in'),
    key: 'check_in_at',
    width: 170,
    render: (row) => formatDateTime(row.check_in_at, locale.value),
  },
])

onMounted(loadAll)
onBeforeUnmount(stopPolling)
</script>

<style scoped>
.connector-stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  max-width: 960px;
}

.connector-card__header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
}

.connector-card__icon {
  width: 44px;
  height: 44px;
  border-radius: var(--radius-md);
  background: var(--color-brand-50);
  color: var(--color-brand-500);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 22px;
  flex-shrink: 0;
}

.connector-card__info {
  flex: 1;
}

.connector-card__name {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
}

.connector-card__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  margin-top: 2px;
}

.connector-card__meta {
  display: flex;
  gap: var(--space-3);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  margin-top: var(--space-1);
}

.connector-card__form {
  margin-bottom: var(--space-3);
}

.connector-card__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  flex-wrap: wrap;
}

.connector-card__buttons {
  display: flex;
  gap: var(--space-2);
}

.section-title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--space-3);
}

.muted {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.notice {
  font-size: var(--text-sm);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  margin-top: var(--space-3);
}

.notice__details {
  display: flex;
  gap: var(--space-3);
  margin-top: var(--space-1);
  font-weight: 600;
}

.notice--ok {
  background: oklch(93% 0.08 145);
  color: oklch(38% 0.18 145);
}

.notice--fail {
  background: oklch(93% 0.08 25);
  color: oklch(40% 0.22 25);
}

.notice--info {
  background: oklch(93% 0.08 230);
  color: oklch(38% 0.18 230);
}

.sync-panel__controls {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}

.job {
  margin-top: var(--space-4);
  padding: var(--space-3) var(--space-4);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
}

.job__head {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-bottom: var(--space-2);
}

.job__counts {
  display: flex;
  gap: var(--space-8);
  margin-top: var(--space-2);
}

.job__counts dt {
  font-size: var(--text-xs);
  color: var(--text-muted);
}

.job__counts dd {
  font-size: var(--text-xl, 20px);
  font-weight: 700;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.last-sync {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  flex-wrap: wrap;
  margin-top: var(--space-4);
}

.push-note {
  display: flex;
  align-items: flex-start;
  gap: var(--space-2);
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.push-note svg {
  width: 18px;
  height: 18px;
  flex-shrink: 0;
  margin-top: 1px;
}

.token-field-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
</style>
