<template>
  <n-input v-bind="inputProps" v-model:value="model">
    <template v-if="$slots.prefix" #prefix>
      <slot name="prefix" />
    </template>
    <template v-if="$slots.suffix" #suffix>
      <slot name="suffix" />
    </template>
  </n-input>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NInput } from 'naive-ui'
import type { InputProps } from 'naive-ui'

interface Props {
  modelValue?: string
  placeholder?: string
  type?: InputProps['type']
  disabled?: boolean
  readonly?: boolean
  size?: InputProps['size']
  status?: InputProps['status']
  clearable?: boolean
  showPasswordOn?: InputProps['showPasswordOn']
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: '',
  type: 'text',
  disabled: false,
  readonly: false,
  size: 'medium',
  clearable: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

const model = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val),
})

const inputProps = computed((): InputProps => ({
  placeholder: props.placeholder,
  type: props.type,
  disabled: props.disabled,
  readonly: props.readonly,
  size: props.size,
  status: props.status,
  clearable: props.clearable,
  showPasswordOn: props.showPasswordOn,
}))
</script>
