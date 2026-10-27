<template>
  <AppBadge :color="badgeColor" :dot="dot">{{ label }}</AppBadge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import AppBadge from './AppBadge.vue'

type Color = 'default' | 'success' | 'warning' | 'danger' | 'info' | 'brand'

interface Props {
  status: string
  dot?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  dot: true,
})
const { t } = useI18n()

const statusMap: Record<string, { color: Color; label: string }> = {
  // Task statuses
  pending: { color: 'default', label: 'Pending' },
  running: { color: 'info', label: 'Running' },
  completed: { color: 'success', label: 'Completed' },
  failed: { color: 'danger', label: 'Failed' },
  cancelled: { color: 'default', label: 'Cancelled' },
  awaiting_approval: { color: 'warning', label: 'Awaiting Approval' },
  // Video statuses
  draft: { color: 'default', label: 'Draft' },
  script_ready: { color: 'info', label: 'Script Ready' },
  storyboard_ready: { color: 'brand', label: 'Storyboard Ready' },
  generating: { color: 'info', label: 'Generating' },
  compositing: { color: 'info', label: 'Compositing' },
  // Approval statuses
  approved: { color: 'success', label: 'Approved' },
  rejected: { color: 'danger', label: 'Rejected' },
  expired: { color: 'default', label: 'Expired' },
  // Asset statuses
  processing: { color: 'info', label: 'Processing' },
  ready: { color: 'success', label: 'Ready' },
  // Sync job statuses
  queued: { color: 'default', label: 'Queued' },
  success: { color: 'success', label: 'Success' },
  partial: { color: 'warning', label: 'Partial' },
  // Employee statuses
  active: { color: 'success', label: 'Active' },
  inactive: { color: 'default', label: 'Inactive' },
}

const resolved = computed(
  () => statusMap[props.status] ?? { color: 'default' as Color, label: props.status },
)
const badgeColor = computed(() => resolved.value.color)
const label = computed(() => t(resolved.value.label))
</script>
