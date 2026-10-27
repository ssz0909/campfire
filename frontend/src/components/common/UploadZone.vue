<template>
  <div
    class="upload-zone"
    :class="{
      'upload-zone--dragging': isDragging,
      'upload-zone--disabled': disabled,
    }"
    role="button"
    tabindex="0"
    :aria-label="ariaLabel"
    @click="openFilePicker"
    @keydown.enter="openFilePicker"
    @keydown.space.prevent="openFilePicker"
    @dragenter.prevent="isDragging = true"
    @dragleave.prevent="isDragging = false"
    @dragover.prevent
    @drop.prevent="handleDrop"
  >
    <input
      ref="inputRef"
      type="file"
      class="upload-zone__input"
      :accept="accept"
      :multiple="multiple"
      aria-hidden="true"
      tabindex="-1"
      @change="handleChange"
    />
    <div class="upload-zone__content">
      <CloudUploadOutline class="upload-zone__icon" aria-hidden="true" />
      <p class="upload-zone__title">
        {{ isDragging ? 'Drop files here' : title }}
      </p>
      <p class="upload-zone__hint">{{ hint }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { CloudUploadOutline } from '@vicons/ionicons5'

interface Props {
  accept?: string
  multiple?: boolean
  disabled?: boolean
  title?: string
  hint?: string
}

const props = withDefaults(defineProps<Props>(), {
  accept: '*',
  multiple: false,
  disabled: false,
  title: 'Click or drag files to upload',
  hint: 'Supports images, videos, and documents',
})

const emit = defineEmits<{
  files: [files: File[]]
}>()

const isDragging = ref(false)
const inputRef = ref<HTMLInputElement | null>(null)

const ariaLabel = `${props.title}. ${props.hint}`

function openFilePicker() {
  if (!props.disabled) inputRef.value?.click()
}

function handleChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) {
    emit('files', Array.from(target.files))
    target.value = ''
  }
}

function handleDrop(e: DragEvent) {
  isDragging.value = false
  if (props.disabled || !e.dataTransfer) return
  emit('files', Array.from(e.dataTransfer.files))
}
</script>

<style scoped>
.upload-zone {
  border: 2px dashed var(--border-strong);
  border-radius: var(--radius-lg);
  padding: var(--space-12) var(--space-8);
  text-align: center;
  cursor: pointer;
  transition:
    border-color var(--duration-normal) var(--ease-standard),
    background var(--duration-normal) var(--ease-standard);
}

.upload-zone:hover,
.upload-zone:focus-visible {
  border-color: var(--color-brand-400);
  background: var(--color-brand-50);
}

.upload-zone--dragging {
  border-color: var(--color-brand-500);
  background: var(--color-brand-50);
}

.upload-zone--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.upload-zone__input {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.upload-zone__content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-2);
  pointer-events: none;
}

.upload-zone__icon {
  width: 28px;
  height: 28px;
  font-size: 28px;
  color: var(--text-muted);
}

.upload-zone__title {
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--text-primary);
}

.upload-zone__hint {
  font-size: var(--text-sm);
  color: var(--text-secondary);
}
</style>
