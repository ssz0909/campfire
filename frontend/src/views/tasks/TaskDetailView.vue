<template>
  <div>
    <AppPageHeader :title="task?.title ?? '任务详情'" :breadcrumbs="[{ label: '任务', to: '/tasks' }]">
      <template v-if="task" #actions>
        <AppBadge :color="task.status === 'completed' ? 'success' : task.status === 'failed' ? 'danger' : 'info'">{{ taskLabels[task.status] ?? task.status }}</AppBadge>
        <n-button v-if="schedule" :loading="busy" @click="toggleSchedule">{{ task.status === 'scheduled' ? '暂停计划' : '恢复计划' }}</n-button>
        <n-button v-if="!schedule && task.digital_employee_id" @click="createSchedule">创建定时计划</n-button>
        <n-button v-if="canCancel" :loading="busy" @click="cancel">取消任务</n-button>
        <n-button v-if="!schedule && ['failed', 'cancelled'].includes(task.status)" :loading="busy" @click="retry">重新执行</n-button>
        <n-button v-if="task.status === 'failed'" @click="revise">修改目标后重建</n-button>
        <n-button v-if="task.output?.report_markdown" @click="download">下载结果</n-button>
        <n-button v-if="task.status === 'completed'" @click="router.push({ path: '/publishing', query: { task_id: task.id, title: task.title } })">发布到平台</n-button>
      </template>
    </AppPageHeader>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <AppLoader v-if="loading" variant="card" />
    <template v-else-if="task">
      <AppCard>
        <p>{{ task.output?.employee_name ?? '数字员工' }} · {{ taskLabels[task.status] }} <span v-if="!schedule">· {{ task.progress }}%</span></p>
        <p class="hint">目标：{{ task.input_params?.goal ?? task.title }}</p>
        <p v-if="execution?.publish_accounts?.length" class="hint">发布账号：{{ execution.publish_accounts.map(row => row.label).join('、') }}</p>
        <p v-if="task.output?.mode_label" class="hint">{{ task.output.mode_label }} · {{ task.output.notice }}</p>
        <p v-if="task.error_message" class="error">{{ task.error_message }}</p>
      </AppCard>
      <AppCard v-if="schedule" class="block">
        <h2>定时计划</h2>
        <p>{{ schedule.frequency === 'daily' ? '每天' : '每周 ' + schedule.weekdays.map(day => ['周一','周二','周三','周四','周五','周六','周日'][day]).join('、') }} {{ schedule.time }}（{{ schedule.timezone }}）</p>
        <p v-if="task.status === 'scheduled' && schedule.next_run_at">下次执行：{{ new Date(schedule.next_run_at).toLocaleString() }}</p>
        <p v-if="schedule.last_run_at">最近调度：{{ new Date(schedule.last_run_at).toLocaleString() }}</p>
        <p v-if="schedule.last_error" class="error">{{ schedule.last_error }}</p>
        <p class="hint">每轮独立记录，仍需按现有流程审核。停机期间错过的执行只补一次；暂停计划不影响已经启动的任务。</p>
        <h2>最近执行记录</h2>
        <p v-if="!scheduleRuns.length" class="hint">尚未触发执行。</p>
        <div v-for="run in scheduleRuns" :key="run.id" class="loop-stage">
          <n-button text @click="router.push(`/tasks/${run.id}`)">{{ new Date(run.created_at).toLocaleString() }} · {{ taskLabels[run.status] }}</n-button>
        </div>
      </AppCard>
      <p v-if="task.input_params?.schedule_template_id" class="hint"><n-button text @click="router.push(`/tasks/${task!.input_params.schedule_template_id}`)">查看来源定时计划</n-button></p>
      <AppCard v-if="execution && (execution.enabled || !task.parent_task_id)" class="block">
        <h2>运营执行闭环 · {{ execution.status === 'not_started' ? '未启动' : loopLabels[execution.status] || execution.status }}</h2>
        <p class="hint">{{ execution.notice }}</p><p>{{ execution.next_step }}</p>
        <template v-if="!task.parent_task_id && task.status === 'completed'">
          <AccountPicker v-model="accountIds" :company-id="auth.currentCompanyId!" />
          <div class="actions"><n-button type="primary" :loading="busy" @click="continueExecution">{{ execution.enabled ? '继续 / 修复执行流程' : '启动执行闭环' }}</n-button></div>
          <p class="hint">逐阶段审批后自动继续。视频脚本审批会调用视频模型并产生费用，真实发布需另行审核具体成片和文案。</p>
        </template>
        <div v-for="stage in execution.stages" :key="stage.kind + stage.id" class="loop-stage">
          <strong>{{ stage.title }}</strong> · {{ stageLabel(stage.status) }} {{ stage.platform === 'douyin' ? '抖音' : stage.platform === 'wechat_channels' ? '视频号' : '' }} {{ stage.account_label || '' }}
          <p v-if="stage.error" class="error">{{ stage.error }}</p>
          <p v-if="stage.feedback_due_at" class="hint">数据回流：{{ stage.feedback_state || '等待采集' }} · {{ new Date(stage.feedback_due_at).toLocaleString() }}</p>
          <n-button size="small" @click="router.push(stage.kind === 'task' ? `/tasks/${stage.id}` : stage.kind === 'video' ? `/video/${stage.id}` : '/publishing')">查看阶段</n-button>
          <n-button v-if="stage.approval_id" size="small" @click="router.push('/approvals')">审核发布内容</n-button>
        </div>
        <n-button v-if="task.id !== execution.root_id" @click="router.push(`/tasks/${execution.root_id}`)">查看总任务</n-button>
      </AppCard>
      <AppCard v-if="task.output" class="block">
        <template v-if="task.output.sections?.length">
          <section v-for="(section, i) in task.output.sections" :key="i" class="report-section">
            <h2>{{ section.title }}</h2><p class="report-content">{{ section.content }}</p>
          </section>
        </template>
        <pre v-else>{{ JSON.stringify(task.output, null, 2) }}</pre>
        <details v-if="task.output.data_sources"><summary>查看数据来源快照</summary><pre>{{ JSON.stringify(task.output.data_sources, null, 2) }}</pre></details>
      </AppCard>
      <AppCard v-if="task.status === 'waiting_approval'" class="block">
        <h2>审批任务草稿</h2>
        <p class="hint">通过后自动派发后续岗位任务。视频脚本通过后会启动视频模型生成并产生服务商费用；生成视频仍需另行审核后发布。</p>
        <n-input v-model:value="reviewNote" type="textarea" placeholder="审批意见（退回时必填）" :maxlength="2000" />
        <div class="actions"><n-button type="error" ghost :loading="busy" @click="review(false)">退回修改</n-button><n-button type="primary" :loading="busy" @click="review(true)">通过并完成任务</n-button></div>
      </AppCard>
      <AppCard v-if="task.output?.review" class="block"><h2>审批结果</h2><p>{{ task.output.review.status === 'approved' ? '已通过' : '已退回' }}：{{ task.output.review.note || '无补充意见' }}</p></AppCard>
      <AppCard v-if="task.output?.handoff_task_ids?.length" class="block">
        <h2>已自动派发的任务</h2>
        <div class="actions"><n-button v-for="(id, i) in task.output.handoff_task_ids" :key="id" @click="router.push(`/tasks/${id}`)">查看下游任务 {{ i + 1 }}</n-button></div>
      </AppCard>
      <AppCard v-if="task.output?.handoff_skipped?.length" class="block"><p v-for="item in task.output.handoff_skipped" :key="item.role">{{ item.role }}：{{ item.reason }}</p></AppCard>
      <AppCard v-if="task.status === 'completed' && task.output?.next_actions?.length && !task.output?.handoff_task_ids?.length" class="block">
        <h2>继续下一步工作</h2><p class="hint">将已确认的结果交给下一位数字员工；点击后可编辑目标再提交。</p>
        <div class="actions"><n-button v-for="(action, i) in task.output.next_actions" :key="i" @click="handoff(action)">{{ action.title }}</n-button></div>
      </AppCard>
      <AppCard v-if="task.status === 'completed' && task.output?.delivery === 'video_script'" class="block">
        <h2>制作视频文件</h2><p class="hint">脚本通过后自动创建视频项目。打开项目查看生成进度、预览或配置错误。</p>
        <n-button @click="router.push(task.output.video_project_id ? `/video/${task.output.video_project_id}` : '/video/new')">查看视频项目</n-button>
      </AppCard>
      <AppCard class="block"><h2>执行记录</h2>
        <p v-if="!task.logs.length" class="hint">等待执行记录…</p>
        <p v-for="(entry, i) in task.logs" :key="i" class="log">{{ new Date(entry.timestamp).toLocaleString() }} · {{ entry.message }}</p>
      </AppCard>
    </template>
    <AppCard v-else>任务不存在或无权访问。<n-button @click="load">重试加载</n-button></AppCard>
  </div>
</template>
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { NButton, NInput } from 'naive-ui'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppCard from '@/components/common/AppCard.vue'
import AccountPicker from '@/components/publishing/AccountPicker.vue'
import AppLoader from '@/components/common/AppLoader.vue'
import AppBadge from '@/components/common/AppBadge.vue'
import { useAuthStore } from '@/stores/auth'
import { tasksApi, type ExecutionSnapshot } from '@/api/tasks'
import { approvalsApi } from '@/api/approvals'
import { taskLabels, type OperationTask, type TaskSchedule } from '@/types/task'
const auth = useAuthStore(), route = useRoute(), router = useRouter()
const task = ref<OperationTask | null>(null), loading = ref(true), busy = ref(false), error = ref(''), reviewNote = ref('')
const execution = ref<ExecutionSnapshot | null>(null), accountIds = ref<string[]>([])
const schedule = computed(() => task.value?.input_params?.schedule as TaskSchedule | undefined)
const scheduleRuns = ref<OperationTask[]>([])
function toggleSchedule() { if (task.value) act(() => tasksApi.setScheduleEnabled(auth.currentCompanyId!, task.value!.id, task.value!.status !== 'scheduled')) }
let targetsLoadedFor = ''
const loopLabels: Record<string,string> = {completed:'已闭环',in_progress:'执行中',blocked:'待处理',waiting_approval:'待审批',cancelled:'已停止',pending_review:'待成片审核',published:'已发布',manual_required:'需人工确认',login_required:'需重新登录',rejected:'已退回'}
function stageLabel(status: string) { return ({pending:'待执行',queued:'排队中',running:'执行中',completed:'阶段已完成',waiting_external:'等待外部结果',failed:'失败',cancelled:'已取消'} as Record<string,string>)[status] || loopLabels[status] || status }
async function continueExecution() { if (task.value) await act(() => tasksApi.continueExecution(auth.currentCompanyId!, task.value!.id, [], accountIds.value)) }
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
const canCancel = computed(() => task.value && (['pending','queued','running','waiting_approval','waiting_external'].includes(task.value.status) || (execution.value?.enabled && !task.value.parent_task_id && task.value.status === 'completed' && execution.value.status !== 'completed')))
async function load() {
  clearTimeout(timer)
  const id = route.params.id as string
  try {
    const res = await tasksApi.get(auth.currentCompanyId!, id)
    if (disposed || route.params.id !== id) return
    task.value = res.data; error.value = ''
    if (res.data.input_params?.schedule) {
      execution.value = null
      const runs = await tasksApi.list(auth.currentCompanyId!, {schedule_template_id: id, limit: 20})
      if (disposed || route.params.id !== id) return
      scheduleRuns.value = runs.data
      if (res.data.status === 'scheduled') timer = setTimeout(load, 15000)
      return
    }
    const loop = await tasksApi.execution(auth.currentCompanyId!, id)
    if (disposed || route.params.id !== id) return
    execution.value = loop.data
    if (targetsLoadedFor !== id) { accountIds.value = [...(loop.data.publish_account_ids ?? [])]; targetsLoadedFor = id }
    if (['pending','queued','running','waiting_external','waiting_approval'].includes(res.data.status) || (loop.data.enabled && !['completed','cancelled'].includes(loop.data.status))) timer = setTimeout(load, 5000)
  } catch { if (!disposed) error.value = '任务加载失败，请刷新或重试。' }
  finally { if (!disposed) loading.value = false }
}
onMounted(load)
watch(() => route.params.id, () => { task.value = null; execution.value = null; loading.value = true; load() })
onBeforeUnmount(() => { disposed = true; clearTimeout(timer) })
async function act(fn: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''
  try { await fn(); await load() }
  catch (e: any) { error.value = typeof e.response?.data?.detail === 'string' ? e.response.data.detail : '操作失败，请重试。' }
  finally { busy.value = false }
}
function cancel() { if (task.value) act(() => tasksApi.cancel(auth.currentCompanyId!, task.value!.id)) }
function retry() { if (task.value) act(() => tasksApi.retry(auth.currentCompanyId!, task.value!.id)) }
function review(approved: boolean) {
  const id = task.value?.output?.approval_id
  if (!id) return
  if (!approved && !reviewNote.value.trim()) { error.value = '请填写退回原因。'; return }
  act(() => approved ? approvalsApi.approve(auth.currentCompanyId!, id, reviewNote.value) : approvalsApi.reject(auth.currentCompanyId!, id, reviewNote.value))
}
function revise() {
  router.push({ path: '/tasks/new', query: { employee_id: task.value?.digital_employee_id, title: task.value?.title, goal: String(task.value?.input_params?.goal ?? '') + '\n修改要求：' + (task.value?.error_message ?? '') } })
}
function createSchedule() {
  router.push({ path: '/tasks/new', query: { employee_id: task.value?.digital_employee_id,
    title: task.value?.title, goal: String(task.value?.input_params?.goal ?? ''), timing: 'daily',
    execution_loop: String(task.value?.input_params?.execution_loop ?? false),
    account_ids: (task.value?.input_params?.publish_account_ids as string[] | undefined)?.join(',') ?? '' } })
}
function handoff(action: { role: string; title: string; goal: string }) {
  router.push({ path: '/tasks/new', query: { ...action, parent_task_id: task.value!.id } })
}
function download() {
  if (!task.value?.output?.report_markdown) return
  const blob = new Blob([task.value.output.report_markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob), link = document.createElement('a')
  link.href = url; link.download = '任务结果.md'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<style scoped>
.block { margin-top: 20px; }
.loop-stage { padding: 14px 0; border-bottom: 1px solid var(--border-default); }
h2 { font-size: 18px; margin: 0 0 12px; }
.report-section { margin-bottom: 28px; }
.report-content { white-space: pre-wrap; line-height: 1.9; overflow-wrap: anywhere; }
.hint { color: var(--text-secondary); line-height: 1.8; margin: 10px 0; }
.error { color: var(--color-danger); margin: 12px 0; }
.actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 16px; }
.log { font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
pre { overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
summary { cursor: pointer; margin-bottom: 12px; }
</style>
