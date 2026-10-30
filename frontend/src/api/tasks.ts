import apiClient from './client'
import type { OperationTask, CreateTaskRequest } from '@/types/task'
function normalize(task: OperationTask): OperationTask {
  return { ...task, employee_id: task.digital_employee_id,
    logs: task.execution_log ?? [], cost_usd: task.actual_cost_cents == null ? undefined : task.actual_cost_cents / 100 }
}
export interface ExecutionSnapshot { enabled: boolean; root_id: string; status: string; publish_platforms: string[]; publish_account_ids?: string[]; publish_accounts?: {id: string; label: string}[]; next_step: string; notice: string; stages: {kind: string; id: string; title: string; status: string; error?: string; platform?: string; account_label?: string; feedback_due_at?: string; feedback_state?: string; approval_id?: string}[] }
export const tasksApi = {
  async setScheduleEnabled(companyId: string, taskId: string, enabled: boolean) {
    const res = await apiClient.put<OperationTask>(`/companies/${companyId}/tasks/${taskId}/schedule`, { enabled })
    return { data: normalize(res.data) }
  },
  execution(companyId: string, id: string) { return apiClient.get<ExecutionSnapshot>(`/companies/${companyId}/tasks/${id}/execution`) },
  continueExecution(companyId: string, id: string, publish_platforms: string[], publish_account_ids?: string[]) { return apiClient.post<ExecutionSnapshot>(`/companies/${companyId}/tasks/${id}/execution/continue`, { publish_platforms, publish_account_ids }, {timeout:180000}) },
  async create(companyId: string, data: CreateTaskRequest) {
    const res = await apiClient.post<OperationTask>(`/companies/${companyId}/tasks`, data, { timeout:150000 })
    return { data: normalize(res.data) }
  },
  async list(companyId: string, params?: { status?: string; page?: number; limit?: number; schedule_template_id?: string }) {
    const res = await apiClient.get<{ items: OperationTask[] }>(`/companies/${companyId}/tasks`, {
      params: { status: params?.status, page: params?.page, page_size: params?.limit, schedule_template_id: params?.schedule_template_id },
    })
    return { data: res.data.items.map(normalize) }
  },
  async get(companyId: string, taskId: string) {
    const res = await apiClient.get<OperationTask>(`/companies/${companyId}/tasks/${taskId}`)
    return { data: normalize(res.data) }
  },
  async cancel(companyId: string, taskId: string) {
    const res = await apiClient.post<OperationTask>(`/companies/${companyId}/tasks/${taskId}/cancel`)
    return { data: normalize(res.data) }
  },
  async retry(companyId: string, taskId: string) {
    const res = await apiClient.post<OperationTask>(`/companies/${companyId}/tasks/${taskId}/retry`)
    return { data: normalize(res.data) }
  },
}
