import apiClient from './client'
import type { Company, CompanyStore, CompanyProduct, CreateCompanyRequest } from '@/types/company'

export interface VideoBrandingSettings {
  enabled: boolean
  text: string
  duration_seconds: number
  font: 'default' | 'sans' | 'serif'
  font_size_percent: number
  position: 'top_left' | 'top_center' | 'top_right' | 'middle_left' | 'middle_center' | 'middle_right' | 'bottom_left' | 'bottom_center' | 'bottom_right'
  margin_x_percent: number
  margin_y_percent: number
}

export const companiesApi = {
  videoBrandingFonts(id: string): Promise<{data: {label: string; value: string}[]}> {
    return apiClient.get(`/companies/${id}/video-branding/fonts`)
  },
  previewVideoBranding(id: string, data: VideoBrandingSettings, aspect: string): Promise<{data: {image_base64: string}}> {
    return apiClient.post(`/companies/${id}/video-branding/preview`, data, {params: {aspect}})
  },
  setVideoBranding(id: string, data: VideoBrandingSettings): Promise<{data: Company}> {
    return apiClient.put(`/companies/${id}/video-branding`, data)
  },
  setDefaultVideoMusic(id:string,data:{music_asset_id:string|null;music_volume:number;selection_mode?:'fixed'|'random'}):Promise<{data:Company}> {
    return apiClient.put(`/companies/${id}/default-video-music`,data)
  },
  setPublishLocation(id: string, data: Record<string, unknown>): Promise<{data: Company}> {
    return apiClient.put(`/companies/${id}/publish-location`, data)
  },
  list(): Promise<{ data: Company[] }> {
    return apiClient.get('/companies')
  },

  get(id: string): Promise<{ data: Company }> {
    return apiClient.get(`/companies/${id}`)
  },

  create(data: CreateCompanyRequest): Promise<{ data: Company }> {
    return apiClient.post('/companies', data)
  },

  update(id: string, data: Partial<CreateCompanyRequest>): Promise<{ data: Company }> {
    return apiClient.put(`/companies/${id}`, data)
  },

  delete(id: string): Promise<void> {
    return apiClient.delete(`/companies/${id}`)
  },

  // Stores
  listStores(companyId: string): Promise<{ data: CompanyStore[] }> {
    return apiClient.get(`/companies/${companyId}/stores`)
  },

  createStore(companyId: string, data: Partial<CompanyStore>): Promise<{ data: CompanyStore }> {
    return apiClient.post(`/companies/${companyId}/stores`, data)
  },

  updateStore(companyId: string, storeId: string, data: Partial<CompanyStore>): Promise<{ data: CompanyStore }> {
    return apiClient.patch(`/companies/${companyId}/stores/${storeId}`, data)
  },

  deleteStore(companyId: string, storeId: string): Promise<void> {
    return apiClient.delete(`/companies/${companyId}/stores/${storeId}`)
  },

  // Products
  listProducts(companyId: string): Promise<{ data: CompanyProduct[] }> {
    return apiClient.get(`/companies/${companyId}/products`)
  },

  createProduct(companyId: string, data: Partial<CompanyProduct>): Promise<{ data: CompanyProduct }> {
    return apiClient.post(`/companies/${companyId}/products`, data)
  },

  updateProduct(companyId: string, productId: string, data: Partial<CompanyProduct>): Promise<{ data: CompanyProduct }> {
    return apiClient.patch(`/companies/${companyId}/products/${productId}`, data)
  },

  deleteProduct(companyId: string, productId: string): Promise<void> {
    return apiClient.delete(`/companies/${companyId}/products/${productId}`)
  },
}
