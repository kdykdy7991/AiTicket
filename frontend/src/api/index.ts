import axios from 'axios'
import { ElMessage } from 'element-plus'

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

api.interceptors.response.use(
  response => response.data,
  error => {
    const msg = error.response?.data?.error?.message
      || error.response?.data?.detail
      || '请求失败'
    // 临时调试：打印 404 的请求 URL
    if (error.response?.status === 404) {
      console.error('[404]', error.config?.method?.toUpperCase(), error.config?.baseURL + error.config?.url)
    }
    if (error.response?.status === 401) {
      // Token 过期、被顶下线或无效：清空本地存储并跳转登录
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        // 有具体原因（如"已在其他设备登录"）时提示，避免静默踢出
        const detail = error.response?.data?.detail
        const now = Date.now()
        if (detail && now - lastAuthNotice > 3000) {
          lastAuthNotice = now
          ElMessage.warning(detail)
        }
        window.location.href = '/login'
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default api
