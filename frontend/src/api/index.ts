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
      // Token 过期或无效，清空本地存储并跳转登录
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      localStorage.removeItem('user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    } else {
      ElMessage.error(msg)
    }
    return Promise.reject(error)
  },
)

export default api
