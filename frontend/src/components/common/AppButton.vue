<template>
  <n-button
    v-bind="buttonProps"
    :class="['app-button', `app-button--${variant}`]"
  >
    <template v-if="$slots.icon" #icon>
      <slot name="icon" />
    </template>
    <slot />
  </n-button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { NButton } from 'naive-ui'
import type { ButtonProps } from 'naive-ui'

interface Props {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: ButtonProps['size']
  disabled?: boolean
  loading?: boolean
  block?: boolean
  type?: ButtonProps['type']
}

const props = withDefaults(defineProps<Props>(), {
  variant: 'secondary',
  size: 'medium',
  disabled: false,
  loading: false,
  block: false,
})

const buttonProps = computed((): ButtonProps => {
  const map: Record<string, ButtonProps['type']> = {
    primary: 'primary',
    secondary: 'default',
    ghost: 'default',
    danger: 'error',
  }
  return {
    type: props.type ?? map[props.variant],
    size: props.size,
    disabled: props.disabled,
    loading: props.loading,
    block: props.block,
    ghost: props.variant === 'ghost',
  }
})
</script>
