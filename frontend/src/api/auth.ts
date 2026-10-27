import apiClient from './client'
import type { LoginRequest, RegisterRequest, AuthResponse, AccessTokenResponse, User } from '@/types/auth'

export const authApi = {
  login(data: LoginRequest): Promise<{ data: AuthResponse }> {
    return apiClient.post('/auth/login', data)
  },

  register(data: RegisterRequest): Promise<{ data: AuthResponse }> {
    return apiClient.post('/auth/register', data)
  },

  refresh(refreshToken: string): Promise<{ data: AccessTokenResponse }> {
    return apiClient.post('/auth/refresh', { refresh_token: refreshToken })
  },

  logout(): Promise<void> {
    return apiClient.post('/auth/logout')
  },

  getMe(): Promise<{ data: User }> {
    return apiClient.get('/auth/me')
  },
}
