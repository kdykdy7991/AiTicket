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

/** responseType 为 blob 的请求（附件预览/下载）出错时后端返回的仍是 JSON，
 *  先还原出来，否则用户只能看到笼统的「请求失败」。 */
async function normalizeErrorBody(data: unknown): Promise<any> {
  if (!(data instanceof Blob) || !data.type.includes('json')) return data
  try {
    return JSON.parse(await data.text())
  } catch {
    return data
  }
}

api.interceptors.response.use(
  response => response.data,
  async error => {
    const body = await normalizeErrorBody(error.response?.data)
    const detail = body?.detail
    const msg = body?.error?.message || detail || '请求失败'
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
        const now = Date.now()
        if (detail && typeof detail === 'string' && now - lastAuthNotice > 3000) {
          lastAuthNotice = now
          ElMessage.warning(detail)
        }
        window.location.href = '/login'
      }
    } else {
      ElMessage.error(typeof msg === 'string' ? msg : '请求失败')
    }
    return Promise.reject(error)
  },
)

export default api
