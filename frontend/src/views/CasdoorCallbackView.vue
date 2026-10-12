<template>
  <div class="casdoor-callback">
    <p>{{ message }}</p>
    <el-button v-if="failed" type="primary" @click="router.replace('/login')">返回登录</el-button>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { finishCasdoor } from '@/auth/casdoor'

const router = useRouter()
const message = ref('正在完成 Casdoor 登录…')
const failed = ref(false)

onMounted(async () => {
  try {
    const mode = await finishCasdoor()
    ElMessage.success(mode === 'link' ? 'Casdoor 账号绑定成功' : '登录成功')
    router.replace('/tickets')
  } catch (error) {
    failed.value = true
    const detail = (error as any)?.response?.data?.detail
    message.value = typeof detail === 'string' ? detail : error instanceof Error ? error.message : 'Casdoor 登录失败'
    ElMessage.error(message.value)
  }
})
</script>

<style scoped>
.casdoor-callback { padding: 80px 24px; text-align: center; color: var(--color-text-secondary); }
</style>
