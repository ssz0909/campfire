export interface OverviewStats {
  active_tasks: number
  pending_approvals: number
  videos_this_month: number
  total_cost_this_month_usd: number
  active_employees: number
  tasks_completed_today: number
  total_tasks: number
  completed_tasks: number
  timezone: string
}

export type OrderAnalyticsStatus = 'OK' | 'NO_DATA' | 'NOT_CONNECTED'

export interface OrderKpis {
  date_from?: string
  date_to?: string
  total_orders: number
  cancelled_orders: number
  cancellation_rate: number | null
  active_orders: number
  room_nights: number
  revenue: number
  average_room_nightly_rate: number | null
  average_order_value: number | null
  occupancy_rate: number | null
  occupancy_note?: string | null
  average_lead_time_days: number | null
  orders_by_status: Record<string, number>
}

export interface OrderMetrics {
  status: OrderAnalyticsStatus
  message?: string | null
  last_sync_at?: string | null
  metrics: OrderKpis | null
  definitions?: Record<string, string>
}

export interface OrderMetricsParams {
  date_from?: string
  date_to?: string
}

export interface ContentMetrics {
  posts_created: number
  videos_created: number
  images_generated: number
  words_generated: number
  period: string
}

export interface WorkMetricRow {
 job_id:string; task_id:string|null; task_title:string|null; video_project_id:string; title:string
 platform:string; account_label:string; provider_post_id:string|null; published_at:string
 views:number|null;likes:number|null;comments:number|null;shares:number|null
 captured_at:string|null;sync_status:string;sync_message:string|null;duplicate:boolean
}
export interface WorkMetricsSummary {
 items:WorkMetricRow[];total:number;published_works:number;synced_works:number;can_sync:boolean
 totals:Record<'views'|'likes'|'comments'|'shares',number|null>
 platforms:{platform:string;published:number;synced:number;views:number|null}[]
 accounts:{account_id:string;label:string;status?:string;message?:string;completed_at?:string}[]
 note:string
}
