import apiClient from './client'
import type { Company, CompanyStore, CompanyProduct, CreateCompanyRequest } from '@/types/company'

export const companiesApi = {
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
    return apiClient.patch(`/companies/${id}`, data)
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
