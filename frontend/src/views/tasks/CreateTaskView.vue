<template>
  <div>
    <AppPageHeader title="派发数字员工任务" subtitle="选择岗位、明确目标，生成草稿后由你审核确认。" :breadcrumbs="[{ label: '任务', to: '/tasks' }]" />
    <AppCard>
      <p v-if="loadError" role="alert">{{ loadError }}</p>
      <AppLoader v-if="loading" variant="card" />
      <n-form v-else label-placement="top" @submit.prevent="submit" class="task-form">
        <n-form-item label="执行员工">
          <n-select v-model:value="employeeId" :options="employeeOptions" placeholder="选择数字员工" />
        </n-form-item>
        <p v-if="selected" class="hint">{{ selected.description }}</p>
        <n-form-item label="任务标题">
          <n-input v-model:value="title" placeholder="例如：本周酒店运营分析" :maxlength="255" />
        </n-form-item>
        <n-form-item label="任务目标与要求">
          <n-input v-model:value="goal" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :maxlength="10000" placeholder="说明你要解决的问题、目标客群和交付要求" />
        </n-form-item>
        <n-form-item label="执行方式"><n-switch v-model:value="executionLoop" /> <span style="margin-left:12px">启用运营闭环</span></n-form-item>
        <n-form-item v-if="executionLoop" label="目标发布平台"><n-select v-model:value="targets" multiple :options="[{label:'抖音',value:'douyin'},{label:'视频号',value:'wechat_channels'}]" placeholder="可同时选择，也可在总任务完成后补选" /></n-form-item>
        <p class="hint">使用 .env 中配置的大模型。闭环按分析→内容方案→视频脚本→生成→成片审核→发布审批→数据复盘推进。脚本审批会启动视频生成并产生费用；真实发布另需确认。未配置模型时仅生成规则草稿。</p>
        <p v-if="route.query.parent_task_id" class="hint">本任务将引用上一项已完成任务的交付结果。</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <n-button attr-type="submit" type="primary" :loading="submitting" :disabled="!employeeId || !title.trim() || !goal.trim()">提交并执行</n-button>
      </n-form>
    </AppCard>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NForm, NFormItem, NSelect, NInput, NButton, NSwitch } from 'naive-ui'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import { useAuthStore } from '@/stores/auth'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import { tasksApi } from '@/api/tasks'
import type { DigitalEmployee } from '@/types/digitalEmployee'
import type { TaskType } from '@/types/task'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const employees = ref<DigitalEmployee[]>([]), employeeId = ref<string | null>(null)
const title = ref(String(route.query.title ?? '')), goal = ref(String(route.query.goal ?? ''))
const loading = ref(true), submitting = ref(false), error = ref(''), loadError = ref('')
const selected = computed(() => employees.value.find(e => e.id === employeeId.value))
const executionLoop = ref(true), targets = ref<string[]>([])
const employeeOptions = computed(() => employees.value.map(e => ({ label: e.name + (e.is_active ? '' : '（已停用）'), value: e.id, disabled: !e.is_active })))
const types: Record<string, TaskType> = { operations_manager: 'business_analysis', content_planner: 'marketing_planning', video_producer: 'video_generation', data_analyst: 'business_analysis', operations_assistant: 'daily_report' }
onMounted(async () => {
  try {
    employees.value = (await digitalEmployeesApi.list(auth.currentCompanyId!)).data
    const match = employees.value.find(e => e.id === route.query.employee_id || e.role === route.query.role)
    if (match?.is_active) employeeId.value = match.id
  } catch { loadError.value = '员工加载失败，请刷新重试。' }
  finally { loading.value = false }
})
async function submit() {
  if (!selected.value || !title.value.trim() || !goal.value.trim() || submitting.value) return
  submitting.value = true; error.value = ''
  try {
    const res = await tasksApi.create(auth.currentCompanyId!, {
      digital_employee_id: selected.value.id, title: title.value.trim(),
      task_type: types[selected.value.role] ?? 'custom',
      input_params: { goal: goal.value.trim(), execution_loop: executionLoop.value, publish_platforms: targets.value },
      ...(route.query.parent_task_id ? { parent_task_id: String(route.query.parent_task_id) } : {}),
    })
    await router.push(`/tasks/${res.data.id}`)
  } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '任务提交失败，请重试。' }
  finally { submitting.value = false }
}
</script>
<style scoped>
.task-form { max-width: 800px; }
.hint { color: var(--text-secondary); font-size: var(--text-sm); line-height: 1.8; margin: 0 0 20px; }
.error { color: var(--color-danger); margin-bottom: 16px; }
</style>
