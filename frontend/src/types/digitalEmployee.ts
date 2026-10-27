export type EmployeeRole =
  | 'operations_manager'
  | 'content_planner'
  | 'data_analyst'
  | 'operations_assistant'
  | 'content_creator'
  | 'order_processor'
  | 'customer_service'
  | 'analyst'
  | 'video_producer'
  | 'custom'

export type ApprovalPolicy = 'always' | 'never' | 'above_threshold'

export interface DigitalEmployee {
  id: string
  company_id: string
  name: string
  role: EmployeeRole
  description?: string
  avatar_url?: string
  is_active: boolean
  approval_policy: ApprovalPolicy
  approval_threshold?: number
  tools: string[]
  work_rules: Record<string, unknown>
  last_run_at?: string
  total_tasks_completed?: number
  total_cost_usd?: number
  created_at: string
  updated_at: string
}
