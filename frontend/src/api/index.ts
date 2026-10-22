import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'
import { ElMessage } from 'element-plus'

// silent: 调用方自行处理错误（例如 404 表示“暂无该数据”），不弹全局提示
declare module 'axios' {
  interface AxiosRequestConfig {
    silent?: boolean
    _authRetried?: boolean
  }
}

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// 被顶下线时的 401 提示去重：避免同一时间多个请求各弹一条
let lastAuthNotice = 0
let refreshPromise: Promise<string> | null = null
let redirectingToLogin = false
const SESSION_CHANGED = 'SESSION_CHANGED'

interface RefreshResponse {
  access_token: string
  refresh_token: string
}

function refreshAccessToken(): Promise<string> {
  if (!refreshPromise) {
    const refreshToken = localStorage.getItem('refresh_token')
    if (!refreshToken) return Promise.reject(new Error('没有刷新凭证'))
    // 使用独立 axios 请求，避免刷新接口的 401 再次进入本拦截器。
    refreshPromise = axios.post<RefreshResponse>('/api/v1/auth/refresh', {
      refresh_token: refreshToken,
    }).then(({ data }) => {
      if (localStorage.getItem('refresh_token') !== refreshToken) {
        throw new Error(SESSION_CHANGED)
      }
      localStorage.setItem('access_token', data.access_token)
      localStorage.setItem('refresh_token', data.refresh_token)
      return data.access_token
    }).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

function clearSessionAndRedirect(detail?: string) {
  if (redirectingToLogin) return
  redirectingToLogin = true
  localStorage.removeItem('access_token')
  localStorage.removeItem('refresh_token')
  localStorage.removeItem('user')
  if (window.location.pathname === '/login') return
  const now = Date.now()
  if (detail && now - lastAuthNotice > 3000) {
    lastAuthNotice = now
    sessionStorage.setItem('auth_notice', detail)
    ElMessage.warning(detail)
  }
  window.location.href = '/login'
}

api.interceptors.response.use(
  response => response.data,
  async (error: AxiosError<{ detail?: string; error?: { message?: string } }>) => {
    const silent = error.config?.silent === true
    const msg = error.response?.data?.error?.message
      || error.response?.data?.detail
      || '请求失败'
    // 临时调试：打印 404 的请求 URL
    if (error.response?.status === 404 && !silent) {
      console.error('[404]', error.config?.method?.toUpperCase(), `${error.config?.baseURL || ''}${error.config?.url || ''}`)
    }
    if (error.response?.status === 401) {
      const config = error.config as InternalAxiosRequestConfig & { _authRetried?: boolean }
      const authEndpoint = config?.url?.startsWith('/auth/login')
        || config?.url?.startsWith('/auth/casdoor/')
        || config?.url?.startsWith('/auth/refresh')
      if (config && !config._authRetried && !authEndpoint) {
        config._authRetried = true
        try {
          // 并发请求可能已由另一条请求刷新；优先复用刚更新的令牌。
          const currentToken = localStorage.getItem('access_token')
          const sentToken = config.headers?.Authorization?.toString().replace(/^Bearer\s+/i, '')
          const token = currentToken && currentToken !== sentToken
            ? currentToken
            : await refreshAccessToken()
          config.headers.set('Authorization', `Bearer ${token}`)
          return api(config)
        } catch (refreshError) {
          // 刷新期间用户主动退出或切换账号，不要清除新会话。
          if (refreshError instanceof Error && refreshError.message === SESSION_CHANGED) {
            return Promise.reject(refreshError)
          }
          const refreshDetail = axios.isAxiosError(refreshError)
            ? refreshError.response?.data?.detail
            : undefined
          clearSessionAndRedirect(refreshDetail || error.response?.data?.detail || '登录状态已过期，请重新登录')
          return Promise.reject(refreshError)
        }
      }
      if (!authEndpoint) clearSessionAndRedirect(error.response?.data?.detail || '登录状态已过期，请重新登录')
    } else if (!silent) {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default api
