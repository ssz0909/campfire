export interface User {
  id: string
  email: string
  full_name: string
  avatar_url?: string
  is_active: boolean
  is_platform_admin: boolean
  created_at: string
  updated_at: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface RegisterRequest {
  email: string
  password: string
  full_name: string
}

export interface AccessTokenResponse {
  access_token: string
  token_type: string
}

export interface AuthResponse extends AccessTokenResponse {
  refresh_token: string
  user: User
}

export interface TokenPayload {
  sub: string
  email: string
  exp: number
  iat: number
}
