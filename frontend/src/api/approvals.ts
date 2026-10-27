import apiClient from './client'
import type { ApprovalRequest } from '@/types/approval'

interface ApprovalResponse {
  id: string; company_id: string; resource_type: string; resource_id: string
  action: string; description: string; requested_by: string
  status: ApprovalRequest['status']; review_note?: string; created_at: string
  details?: Record<string, unknown>
}
function normalize(a: ApprovalResponse): ApprovalRequest {
  return { ...a, task_id: a.resource_type === 'operation_task' ? a.resource_id : a.details?.task_id as string | undefined,
    video_project_id: a.details?.video_project_id as string | undefined,
    operation_type: a.action, requester_id: a.requested_by, requester_name: String(a.details?.employee_name ?? '企业成员'),
    urgency: 'medium', metadata: a.details ?? {}, rejection_reason: a.review_note }
}
export const approvalsApi = {
  async list(companyId: string, params?: { status?: string; page?: number; limit?: number }): Promise<{ data: ApprovalRequest[] }> {
    const response = await apiClient.get<ApprovalResponse[] | { items: ApprovalResponse[] }>(`/companies/${companyId}/approvals`, {
      params: { status: params?.status, page: params?.page, page_size: params?.limit },
    })
    return { data: (Array.isArray(response.data) ? response.data : response.data.items).map(normalize) }
  },

  async get(companyId: string, approvalId: string): Promise<{ data: ApprovalRequest }> {
    const res = await apiClient.get<ApprovalResponse>(`/companies/${companyId}/approvals/${approvalId}`)
    return { data: normalize(res.data) }
  },

  async approve(companyId: string, approvalId: string, note?: string): Promise<{ data: ApprovalRequest }> {
    const res = await apiClient.post<ApprovalResponse>(`/companies/${companyId}/approvals/${approvalId}/approve`, { note }, { timeout:300000 })
    return { data: normalize(res.data) }
  },

  async reject(companyId: string, approvalId: string, reason?: string): Promise<{ data: ApprovalRequest }> {
    const res = await apiClient.post<ApprovalResponse>(`/companies/${companyId}/approvals/${approvalId}/reject`, { note: reason })
    return { data: normalize(res.data) }
  },
}
