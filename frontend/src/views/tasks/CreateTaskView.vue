<template>
  <div>
    <AppPageHeader title="派发数字员工任务" subtitle="选择岗位、明确目标，并设置审批与执行方式。" :breadcrumbs="[{ label: '任务', to: '/tasks' }]" />
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
        <n-form-item label="执行时间">
          <n-select v-model:value="timing" :options="[{label:'立即执行一次',value:'now'},{label:'每天定时执行',value:'daily'},{label:'每周指定日期执行',value:'weekly'}]" :disabled="!!route.query.parent_task_id" />
        </n-form-item>
        <template v-if="timing !== 'now'">
          <n-form-item label="执行时间（北京时间）"><n-time-picker v-model:formatted-value="scheduleTime" format="HH:mm" :clearable="false" /></n-form-item>
          <n-form-item v-if="timing === 'weekly'" label="每周执行日期"><n-select v-model:value="weekdays" multiple :options="weekdayOptions" /></n-form-item>
          <p class="hint">按北京时间定时创建新的执行任务，无需保持页面打开。暂停计划不会取消已生成的任务。服务器停机错过的时间恢复后只补执行一次，避免集中重复执行。每轮沿用下方审批策略。</p>
        </template>
        <n-form-item label="审批策略"><n-switch v-model:value="autoExecute" /> <span style="margin-left:12px">允许全流程自动执行</span></n-form-item>
        <p class="hint">{{ autoExecute ? '已开启：本任务及后续派发任务、视频脚本、成片与文案全部自动通过，生成完成后直接发布至所选账号，不再等待人工审批。会调用付费模型并对外发布，请确认目标与账号。' : '未开启：草稿、视频脚本及成片仍需人工审核。' }}</p>
        <n-form-item label="执行方式"><n-switch v-model:value="executionLoop" /> <span style="margin-left:12px">启用运营闭环</span></n-form-item>
        <n-form-item v-if="executionLoop" label="目标发布账号"><AccountPicker v-model="accountIds" :company-id="auth.currentCompanyId!" /></n-form-item>
        <p class="hint">使用后台配置的大模型（未设置时读取 .env）。闭环按分析→内容方案→视频脚本→生成→成片审核→自动发布→数据复盘推进。视频生成会产生费用；开启全流程自动执行后，无需手动审核脚本和成片。</p>
        <p v-if="route.query.parent_task_id" class="hint">本任务将引用上一项已完成任务的交付结果。</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <n-button attr-type="submit" type="primary" :loading="submitting" :disabled="!employeeId || !title.trim() || !goal.trim() || (timing === 'weekly' && !weekdays.length)">{{ timing === 'now' ? '提交并执行' : '保存定时计划' }}</n-button>
      </n-form>
    </AppCard>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NForm, NFormItem, NSelect, NInput, NButton, NSwitch, NTimePicker } from 'naive-ui'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AccountPicker from '@/components/publishing/AccountPicker.vue'
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
const executionLoop = ref(route.query.execution_loop !== 'false'), accountIds = ref<string[]>(String(route.query.account_ids ?? '').split(',').filter(Boolean))
const autoExecute = ref(route.query.auto_execute === 'true')
const timing = ref<'now' | 'daily' | 'weekly'>(route.query.timing === 'daily' ? 'daily' : 'now'), scheduleTime = ref('09:00')
const weekdays = ref([0, 1, 2, 3, 4])
const weekdayOptions = ['周一','周二','周三','周四','周五','周六','周日'].map((label,value) => ({label,value}))
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
      auto_execute: autoExecute.value, digital_employee_id: selected.value.id, title: title.value.trim(),
      task_type: types[selected.value.role] ?? 'custom',
      input_params: { goal: goal.value.trim(), execution_loop: executionLoop.value, publish_account_ids: accountIds.value },
      ...(timing.value !== 'now' ? { schedule: { frequency: timing.value, time: scheduleTime.value, timezone: 'Asia/Shanghai', weekdays: timing.value === 'weekly' ? weekdays.value : [0, 1, 2, 3, 4, 5, 6] } } : {}),
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
