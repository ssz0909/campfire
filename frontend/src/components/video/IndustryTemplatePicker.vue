<template>
  <div class="industry-picker">
    <n-select :value="modelValue" :options="industryOptions" :loading="industriesLoading" clearable
      placeholder="跟随工作区行业" @update:value="$emit('update:modelValue', $event)" />
    <p v-if="industryError" role="alert">{{ industryError }}</p>
    <p v-else>本次模板：{{ effective?.name || '通用' }}<span v-if="effective"> · v{{ effective.version }}</span>。{{ modelValue ? '本任务覆盖工作区行业。' : '未指定时跟随工作区；未配置或已停用时使用通用模板。' }}企业资料、素材事实与任务要求优先。</p>
  </div>
</template>
<script setup lang="ts">
import {computed} from 'vue'
import {NSelect} from 'naive-ui'
import {useIndustryCatalog} from '@/composables/useIndustryCatalog'
import {useAuthStore} from '@/stores/auth'
const props = defineProps<{modelValue: string | null}>()
defineEmits<{'update:modelValue': [value: string | null]}>()
const auth = useAuthStore()
const {industries, industryOptions, industriesLoading, industryError} = useIndustryCatalog()
const aliases: Record<string, string> = {hotel:'travel', tourism:'travel', 酒店:'travel', 酒旅:'travel', 景区:'travel', 酒店与民宿:'travel'}
const effective = computed(() => {
  const requested = props.modelValue || auth.currentCompany?.industry || 'generic'
  return industries.value.find(i => i.code === (aliases[requested] || requested)) || industries.value.find(i => i.code === 'generic')
})
</script>
<style scoped>
.industry-picker {width:100%}.industry-picker p {font-size:12px;color:var(--text-secondary);line-height:1.7;margin-top:8px}
</style>
