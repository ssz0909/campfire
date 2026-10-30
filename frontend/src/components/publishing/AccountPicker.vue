<template>
  <n-select :value="modelValue" multiple :options="options" :loading="loading" :disabled="loading || !!error"
    placeholder="选择具体发布账号，可跨平台多选" @update:value="emit('update:modelValue', $event)" />
  <p v-if="error" role="alert">{{ error }} <n-button text @click="load">重新加载</n-button></p>
  <p v-else-if="!loading && !accounts.length" class="hint">尚未添加发布账号，请先前往「平台发布」添加并登录账号。</p>
  <p v-else class="hint">任务将只发布到所选账号；会话过期时该账号需重新登录。</p>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { NSelect, NButton } from 'naive-ui'
import { publishingApi, type PublishingPlatform } from '@/api/publishing'
const props = defineProps<{ companyId: string; modelValue: string[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: string[]] }>()
const accounts = ref<PublishingPlatform[]>([]), loading = ref(false), error = ref('')
const options = computed(() => accounts.value.map(row => ({label: `${row.name}${['authorized','session_saved'].includes(row.status) ? '' : '（需登录）'}`, value: row.id!})))
async function load() {
  const companyId = props.companyId
  loading.value = true; error.value = ''
  try { const rows = await publishingApi.accounts(companyId); if (companyId === props.companyId) accounts.value = rows }
  catch { error.value = '发布账号加载失败，请重试。' }
  finally { loading.value = false }
}
onMounted(load)
watch(() => props.companyId, load)
</script>
<style scoped>.hint{color:var(--text-secondary);font-size:13px;line-height:1.8}</style>
