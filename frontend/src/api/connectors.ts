import apiClient from './client'
import type {
  HotelConnector,
  HotelConnectorSaveRequest,
  HotelOrderList,
  HotelOrderQuery,
  HotelSyncJob,
  HotelSyncRequest,
  HotelTestResult,
} from '@/types/connector'

const base = (companyId: string) => `/companies/${companyId}/connectors/hotel`

export interface DddLoginRequest {
  phone: string
  password: string
  sms_captcha?: string
}

export interface DddStore {id: string; ntw_num: string; name: string | null; version: string | null}
export interface DddLoginResult {verification_required: boolean; stores: DddStore[]}

export const connectorsApi = {
  dddSelectStore(companyId: string, ntw_id: string): Promise<{data: HotelConnector}> {
    return apiClient.post(`${base(companyId)}/ddd-store`, {ntw_id})
  },
  getHotel(companyId: string): Promise<{ data: HotelConnector }> {
    return apiClient.get(base(companyId))
  },

  dddLogin(companyId: string, body: DddLoginRequest): Promise<{ data: DddLoginResult }> {
    return apiClient.post(`${base(companyId)}/ddd-login`, body)
  },

  saveHotel(companyId: string, body: HotelConnectorSaveRequest): Promise<{ data: HotelConnector }> {
    return apiClient.post(base(companyId), body)
  },

  testHotel(companyId: string): Promise<{ data: HotelTestResult }> {
    // Real platform call; allow more time than the default client timeout
    return apiClient.post(`${base(companyId)}/test`, undefined, { timeout: 60000 })
  },

  logoutHotel(companyId: string): Promise<{ data: { configured: boolean; status: string } }> {
    return apiClient.post(`${base(companyId)}/logout`)
  },

  syncHotel(companyId: string, body: HotelSyncRequest): Promise<{ data: HotelSyncJob }> {
    return apiClient.post(`${base(companyId)}/sync`, body)
  },

  listSyncJobs(companyId: string, limit = 10): Promise<{ data: HotelSyncJob[] }> {
    return apiClient.get(`${base(companyId)}/sync-jobs`, { params: { limit } })
  },

  listOrders(companyId: string, params?: HotelOrderQuery): Promise<{ data: HotelOrderList }> {
    return apiClient.get(`${base(companyId)}/orders`, { params })
  },
}
