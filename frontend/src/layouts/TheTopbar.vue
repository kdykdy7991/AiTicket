<template>
  <header class="topbar">
    <div class="topbar-left">
      <!-- 顶部搜索已移除 -->
    </div>
    <div class="topbar-right">
      <el-dropdown @command="onCommand" trigger="click">
        <button class="user-trigger">
          <span class="user-avatar-circle">
            {{ authStore.displayName.charAt(0) }}
          </span>
          <span class="user-name">{{ authStore.displayName }}</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="chevron-icon">
            <polyline points="6,9 12,15 18,9"/>
          </svg>
        </button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item disabled>
              <span style="color: var(--color-text-tertiary); font-size: 12px;">{{ authStore.user?.email }}</span>
            </el-dropdown-item>
            <el-dropdown-item command="changePassword">
              修改密码
            </el-dropdown-item>
            <el-dropdown-item v-if="authStore.isAdmin && casdoorEnabled" command="bindCasdoor">
              绑定 Casdoor 账号
            </el-dropdown-item>
            <el-dropdown-item divided command="logout">
              退出登录
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <ChangePasswordDialog v-model="changePasswordVisible" />
  </header>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import ChangePasswordDialog from '@/components/ChangePasswordDialog.vue'
import { authApi } from '@/api/auth'
import { startCasdoor } from '@/auth/casdoor'
import { ElMessage } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()

const changePasswordVisible = ref(false)
const casdoorEnabled = ref(false)

onMounted(async () => {
  if (authStore.isAdmin) {
    try { casdoorEnabled.value = (await authApi.casdoorConfig()).enabled } catch { /* optional integration */ }
  }
})

async function onCommand(cmd: string) {
  if (cmd === 'logout') {
    authStore.logout()
    router.push({ name: 'Login' })
  } else if (cmd === 'changePassword') {
    changePasswordVisible.value = true
  } else if (cmd === 'bindCasdoor') {
    try { await startCasdoor('link') }
    catch (error) { ElMessage.error(error instanceof Error ? error.message : '无法连接 Casdoor') }
  }
}
</script>

<style scoped>
.topbar {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  background: var(--color-bg-elevated);
  border-bottom: 1px solid var(--color-border-light);
  flex-shrink: 0;
}

.topbar-right {
  display: flex;
  align-items: center;
}

.user-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  cursor: pointer;
  border: none;
  background: transparent;
  padding: 6px 8px;
  border-radius: var(--radius-md);
  transition: background var(--duration-fast) var(--ease-out);
  font-family: var(--font-sans);
}
.user-trigger:hover {
  background: var(--color-bg-hover);
}

.user-avatar-circle {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-primary), #8B85FF);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--color-text-primary);
}

.chevron-icon {
  color: var(--color-text-tertiary);
}
</style>
