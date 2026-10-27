import axios, { type AxiosInstance, type InternalAxiosRequestConfig, type AxiosResponse } from 'axios'
import { useAuthStore } from '@/stores/auth'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

const apiClient: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
})

// Request interceptor — attach access token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const authStore = useAuthStore()
    if (authStore.accessToken) {
      config.headers.Authorization = `Bearer ${authStore.accessToken}`
    }
    return config
  },
  (error) => Promise.reject(error),
)

let refreshPromise: Promise<string> | null = null

// Response interceptor — handle 401 refresh and error messages
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error) => {
    const originalRequest = error.config

    const isAuthRequest = ['/auth/login', '/auth/register', '/auth/refresh', '/auth/logout']
      .some((path) => originalRequest?.url?.endsWith(path))

    if (error.response?.status === 401 && originalRequest && !originalRequest._retry && !isAuthRequest) {
      originalRequest._retry = true
      try {
        if (!refreshPromise) {
          refreshPromise = useAuthStore().refreshToken().finally(() => {
            refreshPromise = null
          })
        }
        const token = await refreshPromise
        originalRequest.headers.Authorization = `Bearer ${token}`
      } catch {
        await useAuthStore().logout()
        window.location.href = '/login'
        return Promise.reject(error)
      }
      return apiClient(originalRequest)
    }

    if (error.response?.status === 403) {
      console.warn('Permission denied:', error.config?.url)
    }

    return Promise.reject(error)
  },
)

export default apiClient
