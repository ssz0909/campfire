<template>
  <n-modal
    v-model:show="visible"
    preset="dialog"
    :title="title"
    :type="type"
    :positive-text="confirmText"
    :negative-text="cancelText"
    :loading="loading"
    @positive-click="handleConfirm"
    @negative-click="handleCancel"
  >
    <p class="confirm-dialog__content">{{ message }}</p>
  </n-modal>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NModal } from 'naive-ui'

interface Props {
  show: boolean
  title?: string
  message: string
  type?: 'default' | 'warning' | 'error'
  confirmText?: string
  cancelText?: string
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: 'Confirm',
  type: 'warning',
  confirmText: 'Confirm',
  cancelText: 'Cancel',
  loading: false,
})

const emit = defineEmits<{
  'update:show': [value: boolean]
  confirm: []
  cancel: []
}>()

const visible = computed({
  get: () => props.show,
  set: (val) => emit('update:show', val),
})

function handleConfirm() {
  emit('confirm')
}

function handleCancel() {
  emit('cancel')
  visible.value = false
}
</script>

<style scoped>
.confirm-dialog__content {
  font-size: var(--text-sm);
  color: var(--text-secondary);
  line-height: var(--leading-normal);
}
</style>
