<template>
  <div>
    <AppPageHeader :title="editing ? '编辑定时任务' : '派发数字员工任务'" :subtitle="editing ? '修改后续定时执行的任务属性。已生成的执行记录不会改变。' : '选择岗位、明确目标，并设置审批与执行方式。'" :breadcrumbs="[{ label: '任务', to: '/tasks' }]" />
    <AppCard>
      <p v-if="loadError" role="alert">{{ loadError }}</p>
      <AppLoader v-if="loading" variant="card" />
      <n-form v-else-if="!loadError" label-placement="top" @submit.prevent="submit" class="task-form">
        <n-form-item label="执行员工">
          <n-select v-model:value="employeeId" :options="employeeOptions" placeholder="选择数字员工" @update:value="taskType = null" />
        </n-form-item>
        <p v-if="selected" class="hint">{{ selected.description }}</p>
        <n-form-item label="任务标题">
          <n-input v-model:value="title" placeholder="例如：本周酒店运营分析" :maxlength="255" />
        </n-form-item>
        <n-form-item label="任务说明"><n-input v-model:value="description" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" :maxlength="2000" placeholder="补充背景或交付约束（选填）" /></n-form-item>
        <n-form-item label="任务目标与要求">
          <n-input v-model:value="goal" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :maxlength="10000" placeholder="说明你要解决的问题、目标客群和交付要求" />
        </n-form-item>
        <n-form-item label="执行时间">
          <n-select v-model:value="timing" :options="timingOptions" :disabled="!!route.query.parent_task_id" />
        </n-form-item>
        <n-form-item label="行业创作模板"><IndustryTemplatePicker v-model="industryOverride" /></n-form-item>
        <n-form-item label="视频生成策略（用于本任务及后续视频制作）"><n-select v-model:value="generationMode" :options="[{label:'质量优先（现有逐镜生成）',value:'quality'},{label:'成本优先（5秒一段，段内1–2镜）',value:'cost'}]" /></n-form-item>
        <p v-if="generationMode === 'cost'" class="hint">15秒视频预计调用3次，每次生成5秒；每段用一张参考图设计同场景1–2个景别，再后期拼接。内部切镜由视频模型执行，需审核效果。</p>
        <n-form-item label="分镜素材使用策略"><n-select v-model:value="reusePolicy" :options="[{label:'优先复用已审核分镜，不足时生成',value:'prefer_reuse'},{label:'全部重新生成',value:'fresh'},{label:'仅使用已有分镜，不调用视频模型',value:'reuse_only'}]" /></n-form-item>
        <n-form-item label="本任务的视频配乐">
          <n-select v-model:value="musicMode" :options="[{label:'跟随工作区设置',value:'workspace'},{label:'从素材库随机选取',value:'random'},{label:'固定一首音乐',value:'fixed'},{label:'不使用配乐（静音）',value:'none'},{label:'保留模型原声，不替换配乐',value:'model'}]" />
        </n-form-item>
        <MusicPicker v-if="musicMode === 'fixed'" :company-id="auth.currentCompanyId!" v-model:music-asset-id="musicAssetId" v-model:music-volume="musicVolume" />
        <n-form-item v-if="musicMode === 'random'" :label="`音乐音量 ${Math.round(musicVolume * 100)}%`"><n-slider :value="Math.round(musicVolume * 100)" :min="0" :max="100" @update:value="musicVolume = $event / 100" /></n-form-item>
        <p class="hint">配乐配置随本任务传递给后续数字员工和视频项目；定时任务每轮沿用该策略。随机模式在每个新视频项目创建时选曲，重试不换曲；静音会移除模型音轨及复用片段中的全部声音。跟随工作区在视频项目创建时读取工作区设置。</p>
        <template v-if="timing !== 'now'">
          <n-form-item :label="`执行时间（${scheduleTimezone}）`"><n-time-picker v-model:formatted-value="scheduleTime" format="HH:mm" :clearable="false" /></n-form-item>
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
        <n-button attr-type="submit" type="primary" :loading="submitting" :disabled="!employeeId || !title.trim() || !goal.trim() || (timing === 'weekly' && !weekdays.length)">{{ editing ? '保存计划修改' : timing === 'now' ? '提交并执行' : '保存定时计划' }}</n-button>
      </n-form>
    </AppCard>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NForm, NFormItem, NSelect, NInput, NButton, NSwitch, NTimePicker, NSlider } from 'naive-ui'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AccountPicker from '@/components/publishing/AccountPicker.vue'
import IndustryTemplatePicker from '@/components/video/IndustryTemplatePicker.vue'
import MusicPicker from '@/components/video/MusicPicker.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import { useAuthStore } from '@/stores/auth'
import { digitalEmployeesApi } from '@/api/digitalEmployees'
import { tasksApi } from '@/api/tasks'
import type { DigitalEmployee } from '@/types/digitalEmployee'
import type { TaskType } from '@/types/task'
const route = useRoute(), router = useRouter(), auth = useAuthStore()
const editing = computed(() => !!route.query.edit_schedule_id)
const timingOptions = computed(() => [
  ...(!editing.value ? [{label:'立即执行一次',value:'now'}] : []),
  {label:'每天定时执行',value:'daily'}, {label:'每周指定日期执行',value:'weekly'},
])
const employees = ref<DigitalEmployee[]>([]), employeeId = ref<string | null>(null)
const title = ref(String(route.query.title ?? '')), goal = ref(String(route.query.goal ?? ''))
const description = ref(''), taskType = ref<TaskType | null>(null)
const loading = ref(true), submitting = ref(false), error = ref(''), loadError = ref('')
const selected = computed(() => employees.value.find(e => e.id === employeeId.value))
const executionLoop = ref(route.query.execution_loop !== 'false'), accountIds = ref<string[]>(String(route.query.account_ids ?? '').split(',').filter(Boolean))
const autoExecute = ref(route.query.auto_execute === 'true')
const generationMode = ref<'quality' | 'cost'>('quality')
const industryOverride = ref<string|null>(null)
const reusePolicy = ref<'fresh' | 'prefer_reuse' | 'reuse_only'>('prefer_reuse')
const musicMode = ref<'workspace' | 'fixed' | 'random' | 'none' | 'model'>('workspace')
const musicAssetId = ref<string | null>(null), musicVolume = ref(0.25)
const timing = ref<'now' | 'daily' | 'weekly'>(route.query.timing === 'daily' ? 'daily' : 'now'), scheduleTime = ref('09:00')
const scheduleTimezone = ref('Asia/Shanghai')
const weekdays = ref([0, 1, 2, 3, 4])
const weekdayOptions = ['周一','周二','周三','周四','周五','周六','周日'].map((label,value) => ({label,value}))
const employeeOptions = computed(() => employees.value.map(e => ({ label: e.name + (e.is_active ? '' : '（已停用）'), value: e.id, disabled: !e.is_active })))
const types: Record<string, TaskType> = { operations_manager: 'business_analysis', content_planner: 'marketing_planning', video_producer: 'video_generation', data_analyst: 'business_analysis', operations_assistant: 'daily_report' }
onMounted(async () => {
  try {
    employees.value = (await digitalEmployeesApi.list(auth.currentCompanyId!)).data
    if (editing.value) {
      const task = (await tasksApi.get(auth.currentCompanyId!, String(route.query.edit_schedule_id))).data
      const params = task.input_params, schedule = params.schedule as any
      if (!schedule) throw new Error('此任务已不是定时计划')
      employeeId.value = task.digital_employee_id ?? null; title.value = task.title; goal.value = String(params.goal ?? '')
      description.value = task.description ?? ''; taskType.value = task.task_type; industryOverride.value = (params.industry_override as string | null) ?? null
      executionLoop.value = Boolean(params.execution_loop); accountIds.value = (params.publish_account_ids as string[] | undefined) ?? []
      autoExecute.value = Boolean(params.auto_execute); generationMode.value = (params.generation_mode as 'quality' | 'cost') ?? 'quality'
      reusePolicy.value = (params.reuse_policy as 'fresh' | 'prefer_reuse' | 'reuse_only') ?? 'prefer_reuse'
      const music = params.video_music as {selection_mode?: typeof musicMode.value; music_asset_id?: string | null; music_volume?: number} | undefined
      musicMode.value = music?.selection_mode ?? (params.music_disabled ? 'none' : params.music_asset_id ? 'fixed' : 'music_asset_id' in params ? 'model' : 'workspace')
      musicAssetId.value = music?.music_asset_id ?? (params.music_asset_id as string | null) ?? null
      musicVolume.value = music?.music_volume ?? (params.music_volume as number) ?? 0.25
      timing.value = schedule.frequency; scheduleTime.value = schedule.time ?? '09:00'; weekdays.value = schedule.weekdays ?? [0,1,2,3,4]
      scheduleTimezone.value = schedule.timezone ?? 'Asia/Shanghai'
    } else {
    const match = employees.value.find(e => e.id === route.query.employee_id || e.role === route.query.role)
    if (match?.is_active) employeeId.value = match.id
    }
  } catch { loadError.value = editing.value ? '定时计划加载失败，请返回任务列表重试。' : '员工加载失败，请刷新重试。' }
  finally { loading.value = false }
})
async function submit() {
  if (!selected.value || !title.value.trim() || !goal.value.trim() || submitting.value) return
  if (musicMode.value === 'fixed' && !musicAssetId.value) { error.value = '固定配乐需要选择音频素材。'; return }
  submitting.value = true; error.value = ''
  try {
    const payload = {
      auto_execute: autoExecute.value, digital_employee_id: selected.value.id, title: title.value.trim(),
      task_type: editing.value && taskType.value ? taskType.value : types[selected.value.role] ?? 'custom',
      description: description.value.trim() || null,
      input_params: { goal: goal.value.trim(), industry_override: industryOverride.value, execution_loop: executionLoop.value, publish_account_ids: accountIds.value, generation_mode: generationMode.value, reuse_policy: reusePolicy.value,
        video_music: {selection_mode:musicMode.value, music_asset_id:musicMode.value === 'fixed' ? musicAssetId.value : null, music_volume:musicVolume.value} },
      schedule: { frequency: timing.value === 'now' ? 'daily' as const : timing.value, time: scheduleTime.value, timezone: scheduleTimezone.value, weekdays: timing.value === 'weekly' ? weekdays.value : [0, 1, 2, 3, 4, 5, 6] },
      ...(route.query.parent_task_id ? { parent_task_id: String(route.query.parent_task_id) } : {}),
    }
    if (editing.value) {
      await tasksApi.updateSchedule(auth.currentCompanyId!, String(route.query.edit_schedule_id), payload)
      await router.push('/tasks?tab=schedules')
    } else {
      const res = await tasksApi.create(auth.currentCompanyId!, { ...payload, ...(timing.value === 'now' ? { schedule: undefined } : {}) })
      await router.push(`/tasks/${res.data.id}`)
    }
  } catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '任务提交失败，请重试。' }
  finally { submitting.value = false }
}
</script>
<style scoped>
.task-form { max-width: 800px; }
.hint { color: var(--text-secondary); font-size: var(--text-sm); line-height: 1.8; margin: 0 0 20px; }
.error { color: var(--color-danger); margin-bottom: 16px; }
</style>
