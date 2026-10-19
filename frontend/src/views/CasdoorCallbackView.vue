<template>
  <div class="casdoor-callback">
    <span v-if="!failed" class="callback-spinner" aria-hidden="true" />
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
const message = ref('正在进入工单系统…')
const failed = ref(false)

onMounted(async () => {
  try {
    await finishCasdoor()
    await router.replace('/tickets')
  } catch (error) {
    failed.value = true
    const detail = (error as any)?.response?.data?.detail
    message.value = typeof detail === 'string' ? detail : error instanceof Error ? error.message : '登录失败'
    ElMessage.error(message.value)
  }
})
</script>

<style scoped>
.casdoor-callback { min-height: 100vh; display: flex; flex-direction: column; align-items: center; justify-content: center; color: var(--color-text-secondary); }
.callback-spinner { width: 30px; height: 30px; border: 3px solid var(--color-border-light); border-top-color: var(--color-primary); border-radius: 50%; animation: callback-spin 0.8s linear infinite; }
@keyframes callback-spin { to { transform: rotate(360deg); } }
</style>
