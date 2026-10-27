export type TaskStatus = 'pending' | 'queued' | 'running' | 'waiting_approval' | 'waiting_external' | 'waiting_retry' | 'partial' | 'completed' | 'failed' | 'cancelled'
export type TaskType = 'business_analysis' | 'marketing_planning' | 'video_generation' | 'asset_analysis' | 'daily_report' | 'custom'
export interface TaskLogEntry {
  id?: string
  level: 'info' | 'warning' | 'error' | 'debug'
  message: string
  timestamp: string
}
export interface TaskOutput {
  title?: string
  mode_label?: string
  employee_name?: string
  approval_id?: string
  report_markdown?: string
  sections?: { title: string; content: string }[]
  data_sources?: Record<string, unknown>
  next_actions?: { role: string; title: string; goal: string }[]
  handoff_task_ids?: string[]
  handoff_skipped?: { role: string; reason: string }[]
  video_project_id?: string
  notice?: string
  review?: { status: string; note?: string }
  [key: string]: unknown
}
export interface OperationTask {
  parent_task_id?: string
  id: string
  company_id: string
  digital_employee_id?: string
  employee_id?: string
  title: string
  task_type: TaskType
  status: TaskStatus
  progress: number
  input_params: Record<string, unknown>
  output?: TaskOutput
  error_message?: string
  cost_usd?: number
  actual_cost_cents?: number
  started_at?: string
  completed_at?: string
  logs: TaskLogEntry[]
  execution_log?: TaskLogEntry[]
  created_by: string
  created_at: string
  updated_at: string
}
export interface CreateTaskRequest {
  parent_task_id?: string
  digital_employee_id: string
  title: string
  task_type: TaskType
  input_params: Record<string, unknown>
}
export const taskLabels: Record<string, string> = {
  pending: '待执行', queued: '排队中', running: '执行中', waiting_approval: '待审批',
  waiting_external: '等待外部处理', waiting_retry: '等待重试', partial: '部分完成',
  completed: '已完成', failed: '失败或被退回', cancelled: '已取消',
}
