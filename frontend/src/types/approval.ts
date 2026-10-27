export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'expired'

export interface ApprovalRequest {
  id: string
  company_id: string
  task_id?: string
  video_project_id?: string
  operation_type: string
  description: string
  requester_id: string
  requester_name: string
  approver_id?: string
  status: ApprovalStatus
  estimated_cost_usd?: number
  urgency: 'low' | 'medium' | 'high'
  metadata: Record<string, unknown>
  approved_at?: string
  rejected_at?: string
  rejection_reason?: string
  expires_at?: string
  created_at: string
}
