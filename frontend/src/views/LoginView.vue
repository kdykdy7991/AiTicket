<template>
  <div class="login-view">
    <div class="login-brand">
      <div class="brand-icon">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
          <polyline points="14,2 14,8 20,8"/>
          <line x1="16" y1="13" x2="8" y2="13"/>
          <line x1="16" y1="17" x2="8" y2="17"/>
        </svg>
      </div>
      <h1 class="brand-title">Skdy Ticket</h1>
      <p class="brand-subtitle">登录到您的工作台</p>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="onLogin" class="login-form">
      <el-form-item prop="email">
        <el-input v-model="form.email" placeholder="用户名" size="large" />
      </el-form-item>
      <el-form-item prop="password">
        <el-input v-model="form.password" placeholder="密码" type="password" show-password size="large" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" native-type="submit" :loading="loading" size="large" class="login-btn">
          登录
        </el-button>
      </el-form-item>
    </el-form>

    <div class="login-footer">
      <div class="demo-hint">
        <span class="hint-label">演示账号</span>
        <code>admin</code> / <code>admin123</code>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)

const form = reactive({ email: '', password: '' })

const rules: FormRules = {
  email: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
  ],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onLogin() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  loading.value = true
  try {
    await authStore.login(form)
    ElMessage.success('登录成功')
    const redirect = (route.query.redirect as string) || '/tickets'
    router.push(redirect)
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-view {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.login-brand {
  text-align: center;
  margin-bottom: 36px;
}

.brand-icon {
  width: 52px;
  height: 52px;
  background: linear-gradient(135deg, var(--color-primary), #8B85FF);
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  margin: 0 auto 16px;
  box-shadow: 0 4px 16px rgba(99, 91, 255, 0.3);
}

.brand-title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}

.brand-subtitle {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-top: 6px;
}

.login-form {
  width: 100%;
}
.login-form :deep(.el-form-item) {
  margin-bottom: 20px;
}
.login-form :deep(.el-input__wrapper) {
  padding: 6px 14px;
}

.login-btn {
  width: 100%;
  height: 44px;
  font-size: 15px;
  font-weight: 600;
  border-radius: var(--radius-md);
  letter-spacing: 0.02em;
}

.login-footer {
  margin-top: 24px;
  text-align: center;
}

.demo-hint {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.hint-label {
  background: var(--color-bg-subtle);
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-weight: 500;
  font-size: 11px;
}
.demo-hint code {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: var(--color-text-secondary);
  background: var(--color-bg-subtle);
  padding: 1px 6px;
  border-radius: 4px;
}
</style>
