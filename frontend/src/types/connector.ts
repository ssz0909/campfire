export type ConnectorStatus = 'unconfigured' | 'configured' | 'connected' | 'error'

export type SyncJobStatus = 'queued' | 'running' | 'success' | 'partial' | 'failed'

export interface SyncStats {
  found: number
  synced: number
  failed: number
}

export interface HotelConnector {
  connection_mode?: 'web' | 'open_api'
  web_session_active?: boolean
  configured: boolean
  status: ConnectorStatus
  hotel_num: number | null
  hotel_name: string | null
  room_count: number | null
  auth_access_token: string | null
  token_mode?: 'auto' | 'manual' | 'none' | 'web'
  token_expires_at?: string | null
  auto_token_available?: boolean
  last_connect_at: string | null
  last_sync_at: string | null
  last_sync_status: string | null
  last_sync_error: string | null
  last_sync_stats: SyncStats | null
}

export interface HotelConnectorSaveRequest {
  hotel_num: number
  auth_access_token?: string
}

export interface HotelTestResult {
  connected: boolean
  status: ConnectorStatus
  message: string
  hotel_name?: string | null
  room_type_count?: number | null
  room_count?: number | null
  code?: string | null
}

export interface HotelSyncRequest {
  begin_date?: string
  end_date?: string
}

export interface HotelSyncJob {
  id: string
  status: SyncJobStatus
  begin_date: string | null
  end_date: string | null
  orders_found: number
  orders_synced: number
  orders_failed: number
  error: string | null
  created_at?: string | null
  started_at?: string | null
  finished_at?: string | null
}

export interface HotelOrder {
  order_num: string
  status: string
  status_label: string | null
  channel_name: string | null
  order_amount?: number | null
  source?: string
  actual_amount: number | null
  paid_amount: number | null
  currency: string | null
  room_count: number | null
  room_nights: number | null
  order_created_at: string | null
  check_in_at: string | null
  check_out_at: string | null
  synced_at: string | null
}

export interface HotelOrderList {
  orders: HotelOrder[]
  count: number
}

export interface HotelOrderQuery {
  status?: string
  limit?: number
  offset?: number
}
