<template>
  <div>
    <AppPageHeader :title="t('Approvals')" :subtitle="t('Review and action pending approval requests')">
      <template #actions>
        <n-tag v-if="pendingCount > 0" type="warning">
          {{ pendingCount }} {{ t('pending') }}
        </n-tag>
      </template>
    </AppPageHeader>

    <p v-if="error" role="alert" style="color:var(--color-danger)">{{ error }}</p>
    <template v-if="loading">
      <div class="approvals-list">
        <AppCard v-for="i in 4" :key="i">
          <AppLoader variant="card" />
        </AppCard>
      </div>
    </template>

    <template v-else-if="approvals.length === 0">
      <AppEmpty
        :icon="CheckmarkCircleOutline"
        :title="t('No pending approvals')"
        :description="t('All operations are running automatically or nothing needs your review.')"
      />
    </template>

    <template v-else>
      <div class="approvals-list">
        <AppCard
          v-for="approval in approvals"
          :key="approval.id"
          class="approval-card"
        >
          <div class="approval-card__header">
            <div class="approval-card__meta">
              <span class="approval-card__type">{{ approval.operation_type }}</span>
              <AppBadge
                :color="urgencyColor(approval.urgency)"
              >
                {{ t('{urgency} urgency', { urgency: approval.urgency }) }}
              </AppBadge>
              <StatusBadge :status="approval.status" />
            </div>
            <span class="approval-card__time">
              {{ new Date(approval.created_at).toLocaleString() }}
            </span>
          </div>

          <p class="approval-card__desc">{{ approval.description }}</p>
          <div v-if="approval.metadata.platform">
            <p>发布平台：{{ approval.metadata.platform === 'douyin' ? '抖音' : '视频号' }}</p>
            <p>发布标题：{{ approval.metadata.title }}</p><p class="approval-card__desc">正文：{{ approval.metadata.description }}</p>
            <p>通过后将尝试向所选平台真实发布；平台验证或执行结果不明确时需人工处理。</p>
            <n-button v-if="approval.video_project_id" @click="router.push(`/video/${approval.video_project_id}`)">预览待发布成片</n-button>
          </div>

          <div class="approval-card__footer">
            <div class="approval-card__info">
              <span class="approval-card__requester">
                {{ t('Requested by {name}', { name: approval.requester_name }) }}
              </span>
              <span v-if="approval.estimated_cost_usd != null" class="approval-card__cost">
                {{ t('Estimated cost: ${cost}', { cost: approval.estimated_cost_usd.toFixed(4) }) }}
              </span>
            </div>

            <div class="approval-card__actions">
              <n-button v-if="approval.task_id" size="small" @click="router.push(`/tasks/${approval.task_id}`)">查看任务结果</n-button>
            </div>
            <div v-if="approval.status === 'pending'" class="approval-card__actions">
              <n-button
                type="error"
                ghost
                size="small"
                :loading="actionId === approval.id + '_reject'"
                @click="rejectApproval(approval)"
              >
{{ t('Reject') }}              </n-button>
              <n-button
                type="primary"
                size="small"
                :loading="actionId === approval.id + '_approve'"
                @click="approveApproval(approval)"
              >
{{ t('Approve') }}              </n-button>
            </div>
          </div>
        </AppCard>
      </div>
    </template>

    <ConfirmDialog
      v-model:show="showRejectDialog"
      :title="t('Reject approval')"
      :message="t('Reject this {operation} request?', { operation: pendingAction?.operation_type })"
      type="error"
      :confirm-text="t('Reject')"
      :loading="rejectLoading"
      @confirm="confirmReject"
      @cancel="showRejectDialog = false"
    />
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ref, computed, onMounted } from 'vue'
import { NButton, NTag } from 'naive-ui'
import { CheckmarkCircleOutline } from '@vicons/ionicons5'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppEmpty from '@/components/common/AppEmpty.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import StatusBadge from '@/components/common/StatusBadge.vue'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { approvalsApi } from '@/api/approvals'
import type { ApprovalRequest } from '@/types/approval'

const { t } = useI18n()
const router = useRouter()
const authStore = useAuthStore()
const companyId = computed(() => authStore.currentCompanyId!)

const loading = ref(true)
const error = ref('')
const approvals = ref<ApprovalRequest[]>([])
const actionId = ref<string | null>(null)
const showRejectDialog = ref(false)
const rejectLoading = ref(false)
const pendingAction = ref<ApprovalRequest | null>(null)

const pendingCount = computed(
  () => approvals.value.filter((a) => a.status === 'pending').length,
)

function urgencyColor(urgency: string) {
  if (urgency === 'high') return 'danger' as const
  if (urgency === 'medium') return 'warning' as const
  return 'default' as const
}

onMounted(() => loadApprovals())

async function loadApprovals() {
  loading.value = true
  try {
    const res = await approvalsApi.list(companyId.value)
    approvals.value = res.data
  } catch {
    approvals.value = []
  } finally {
    loading.value = false
  }
}

async function approveApproval(approval: ApprovalRequest) {
  if (actionId.value) return
  error.value = ''
  actionId.value = approval.id + '_approve'
  try {
    const res = await approvalsApi.approve(companyId.value, approval.id)
    const idx = approvals.value.findIndex((a) => a.id === approval.id)
    if (idx !== -1) approvals.value[idx] = res.data
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? '审批执行失败，请查看任务状态后重试。'
  } finally {
    actionId.value = null
  }
}

function rejectApproval(approval: ApprovalRequest) {
  pendingAction.value = approval
  showRejectDialog.value = true
}

async function confirmReject() {
  if (!pendingAction.value) return
  rejectLoading.value = true
  try {
    const res = await approvalsApi.reject(companyId.value, pendingAction.value.id)
    const idx = approvals.value.findIndex((a) => a.id === pendingAction.value!.id)
    if (idx !== -1) approvals.value[idx] = res.data
    showRejectDialog.value = false
  } catch (e: any) {
    error.value = e.response?.data?.detail ?? '退回失败，请刷新后重试。'
  } finally {
    rejectLoading.value = false
    pendingAction.value = null
  }
}
</script>

<style scoped>
.approvals-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
}

.approval-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  flex-wrap: wrap;
}

.approval-card__meta {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}

.approval-card__type {
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--text-primary);
  text-transform: capitalize;
}

.approval-card__time {
  font-size: var(--text-xs);
  color: var(--text-muted);
  white-space: nowrap;
}

.approval-card__desc {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
  margin-bottom: var(--space-4);
}

.approval-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-3);
  padding-top: var(--space-3);
  border-top: 1px solid var(--border-default);
  flex-wrap: wrap;
}

.approval-card__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.approval-card__requester {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}

.approval-card__cost {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--text-primary);
  font-variant-numeric: tabular-nums;
}

.approval-card__actions {
  display: flex;
  gap: var(--space-2);
}
</style>
