export interface CostRecord {
  id: string
  company_id: string
  period_start: string
  period_end: string
  task_cost_usd: number
  video_cost_usd: number
  model_cost_usd: number
  storage_cost_usd: number
  total_cost_usd: number
  task_count: number
  video_count: number
  created_at: string
}

export interface UsageSummary {
  tasks_used: number
  tasks_quota: number
  videos_used: number
  videos_quota: number
  storage_used_gb: number
  storage_quota_gb: number
  current_period_cost_usd: number
  budget_usd?: number
}

export interface QuotaInfo {
  tasks_quota: number
  videos_quota: number
  storage_quota_gb: number
  members_quota: number
  employees_quota: number
}
