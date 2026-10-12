import api from './index'
import type { LoginPayload, LoginResponse } from '@/types'

interface BackendUserInfo {
  id: number
  username: string
  name: string
  role: string
  group_id: number | null
  is_group_leader: boolean
}

interface BackendLoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
  user: BackendUserInfo
}

export interface CasdoorConfig {
  enabled: boolean
  authorization_endpoint?: string
  client_id?: string
  redirect_origins?: string[]
}

export interface CasdoorExchange {
  code: string
  code_verifier: string
  nonce: string
  redirect_uri: string
}

/** 把后端字段映射到前端 User 类型 */
function adaptUser(u: BackendUserInfo) {
  return {
    id: u.id,
    email: u.username,                                          // 用 username 充当 email 字段
    firstname: u.name,
    lastname: '',
    role: { id: 0, name: u.role as 'admin' | 'agent' | 'customer', permissions: [] },
    active: true,
    // 额外字段：用于权限判断（受理按钮、批量操作等）
    group_id: u.group_id,
    is_group_leader: u.is_group_leader,
  }
}

export const authApi = {
  async casdoorConfig(): Promise<CasdoorConfig> {
    return api.get<unknown, CasdoorConfig>('/auth/casdoor/config')
  },

  async casdoorLogin(body: CasdoorExchange): Promise<LoginResponse> {
    const res = await api.post<unknown, BackendLoginResponse>('/auth/casdoor/exchange', body)
    return { access_token: res.access_token, refresh_token: res.refresh_token, token_type: res.token_type, expires_in: res.expires_in, user: adaptUser(res.user) as any }
  },

  async casdoorLink(body: CasdoorExchange): Promise<void> {
    await api.post('/auth/casdoor/link', body)
  },

  async casdoorChallenge(verifier: string): Promise<string> {
    const result = await api.post<unknown, { challenge: string }>('/auth/casdoor/challenge', { code_verifier: verifier })
    return result.challenge
  },

  async login(payload: LoginPayload): Promise<LoginResponse> {
    // 兼容前端旧 payload：{ email, password } → { username, password }
    const body = {
      username: (payload as any).username || (payload as any).email,
      password: payload.password,
    }
    const res = await api.post<unknown, BackendLoginResponse>('/auth/login', body)
    return {
      access_token: res.access_token,
      refresh_token: res.refresh_token,
      token_type: res.token_type,
      expires_in: res.expires_in,
      user: adaptUser(res.user) as any,
    }
  },

  async refresh(refreshToken: string): Promise<LoginResponse> {
    const res = await api.post<unknown, BackendLoginResponse>('/auth/refresh', {
      refresh_token: refreshToken,
    })
    return {
      access_token: res.access_token,
      refresh_token: res.refresh_token,
      token_type: res.token_type,
      expires_in: res.expires_in,
      user: adaptUser(res.user) as any,
    }
  },

  async logout(): Promise<void> {
    try { await api.post('/auth/logout') } catch { /* 忽略 */ }
  },

  async changePassword(oldPassword: string, newPassword: string): Promise<void> {
    await api.post('/auth/change-password', {
      old_password: oldPassword,
      new_password: newPassword,
    })
  },
}
