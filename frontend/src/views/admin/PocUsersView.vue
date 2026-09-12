<template>
  <div class="users-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-subtitle">管理 POC 流程用户、业务角色与分系统归属</p>
      </div>
      <el-button type="primary" @click="openCreate">新建用户</el-button>
    </div>

    <div class="filter-bar">
      <el-select v-model="filterRole" placeholder="全部角色" clearable style="width: 170px" @change="loadUsers">
        <el-option v-for="role in SYSTEM_ROLE_OPTIONS" :key="role.value" :label="role.label" :value="role.value" />
      </el-select>
      <el-select v-model="filterSkillGroup" placeholder="全部分系统" clearable style="width: 180px" @change="loadUsers">
        <el-option v-for="group in skillGroups" :key="group.id" :label="group.name" :value="group.id" />
      </el-select>
      <el-input v-model="keyword" placeholder="搜索用户名或姓名" clearable style="width: 230px" @keyup.enter="loadUsers" @clear="loadUsers" />
      <el-checkbox v-model="includeInactive" @change="loadUsers">显示已禁用</el-checkbox>
    </div>

    <el-card shadow="never" v-loading="loading">
      <el-table :data="users" stripe>
        <el-table-column prop="username" label="用户名" min-width="130" />
        <el-table-column prop="name" label="姓名" min-width="110" />
        <el-table-column label="角色" min-width="200">
          <template #default="{ row }">
            <el-tag
              v-for="role in row.roles"
              :key="role"
              :type="roleTagType(role)"
              size="small"
              class="role-tag"
            >
              {{ roleLabel(role as BusinessRole) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="所属分系统" min-width="220">
          <template #default="{ row }">
            <template v-if="row.roles?.includes('subsystem') && row.skill_groups?.length">
              <el-tag v-for="group in row.skill_groups" :key="group.id || group.skill_group_id" size="small" type="info" class="group-tag">
                {{ group.name || skillGroupName(group.skill_group_id) }}
              </el-tag>
            </template>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.is_active" size="small" type="success">启用</el-tag>
            <el-tag v-else size="small" type="info">禁用</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openEdit(row)">编辑</el-button>
            <el-button v-if="row.is_active" text size="small" type="danger" @click="disableUser(row)">禁用</el-button>
            <el-button v-else text size="small" type="success" @click="activateUser(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editingId ? '编辑用户' : '新建用户'" width="540px" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="!!editingId" placeholder="登录用户名" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="显示姓名" />
        </el-form-item>
        <el-form-item label="手机号">
          <el-input v-model="form.phone" placeholder="选填，用于通知" />
        </el-form-item>
        <el-form-item label="密码" :prop="editingId ? undefined : 'password'">
          <el-input v-model="form.password" type="password" show-password :placeholder="editingId ? '留空则不修改' : '至少 6 位'" />
        </el-form-item>
        <el-form-item label="角色" prop="roles">
          <el-select v-model="form.roles" multiple style="width: 100%" placeholder="可多选，至少一个" @change="onRolesChange">
            <el-option v-for="role in SYSTEM_ROLE_OPTIONS" :key="role.value" :label="role.value === 'admin' ? `${role.label}（不参与业务流程）` : role.label" :value="role.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.roles.includes('subsystem')" label="所属分系统" prop="skill_group_ids">
          <el-select v-model="form.skill_group_ids" multiple filterable style="width: 100%" placeholder="选择一个或多个分系统">
            <el-option v-for="group in skillGroups" :key="group.id" :label="group.name" :value="group.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="钉钉 ID">
          <el-input v-model="form.dingtalk_id" placeholder="选填" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { userApi, type UserItem, type UserPayload } from '@/api/users'
import { pocMetaApi } from '@/api/pocMeta'
import { SYSTEM_ROLE_OPTIONS, roleLabel, type BusinessRole } from '@/domain/pocWorkflow'
import type { Group } from '@/types'

const loading = ref(false)
const saving = ref(false)
const users = ref<UserItem[]>([])
const skillGroups = ref<Group[]>([])
const filterRole = ref('')
const filterSkillGroup = ref<number | ''>('')
const keyword = ref('')
const includeInactive = ref(false)
const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({
  username: '', name: '', phone: '', password: '',
  roles: ['presales'] as BusinessRole[],
  skill_group_ids: [] as number[],
  dingtalk_id: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少 6 位', trigger: 'blur' }],
  roles: [{ validator: (_rule, value: BusinessRole[], callback) => value?.length ? callback() : callback(new Error('至少选择一个角色')), trigger: 'change' }],
  skill_group_ids: [{ validator: (_rule, value, callback) => !form.roles.includes('subsystem') || value.length ? callback() : callback(new Error('请选择所属分系统')), trigger: 'change' }],
}

function roleTagType(role: string) {
  if (role === 'admin') return 'danger'
  if (role === 'quality') return 'success'
  if (role === 'approver') return 'warning'
  return 'info'
}

function skillGroupName(id?: number) {
  return skillGroups.value.find(group => group.id === id)?.name || '未知分系统'
}

function onRolesChange() {
  // 只有拥有 subsystem 角色时才需要维护分系统归属
  if (!form.roles.includes('subsystem')) form.skill_group_ids = []
}

function resetForm() {
  Object.assign(form, { username: '', name: '', phone: '', password: '', roles: ['presales'], skill_group_ids: [], dingtalk_id: '' })
  formRef.value?.clearValidate()
}

function openCreate() {
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: UserItem) {
  editingId.value = row.id
  Object.assign(form, {
    username: row.username,
    name: row.name,
    phone: row.phone || '',
    password: '',
    roles: (row.roles || []) as BusinessRole[],
    skill_group_ids: (row.skill_groups || []).map(group => group.id || group.skill_group_id).filter((id): id is number => id != null),
    dingtalk_id: row.dingtalk_id || '',
  })
  dialogVisible.value = true
}

async function loadUsers() {
  loading.value = true
  try {
    users.value = await userApi.list({
      role: filterRole.value || undefined,
      skill_group_id: filterSkillGroup.value || undefined,
      keyword: keyword.value || undefined,
      include_inactive: includeInactive.value,
    })
  } finally {
    loading.value = false
  }
}

async function submit() {
  if (!await formRef.value?.validate().catch(() => false)) return
  saving.value = true
  try {
    const payload: UserPayload = {
      name: form.name,
      phone: form.phone || null,
      roles: form.roles,
      skill_groups: form.roles.includes('subsystem')
        ? form.skill_group_ids.map(skill_group_id => ({ skill_group_id }))
        : [],
      dingtalk_id: form.dingtalk_id || null,
    }
    if (form.password) payload.password = form.password
    if (editingId.value) await userApi.update(editingId.value, payload)
    else await userApi.create({ ...payload, username: form.username })
    ElMessage.success(editingId.value ? '用户已更新' : '用户已创建')
    dialogVisible.value = false
    await loadUsers()
  } finally {
    saving.value = false
  }
}

async function disableUser(row: UserItem) {
  await ElMessageBox.confirm(`确定禁用用户“${row.name}”吗？`, '禁用用户', { type: 'warning' })
  await userApi.disable(row.id)
  ElMessage.success('已禁用')
  await loadUsers()
}

async function activateUser(row: UserItem) {
  await userApi.activate(row.id)
  ElMessage.success('已启用')
  await loadUsers()
}

onMounted(async () => {
  skillGroups.value = await pocMetaApi.getSkillGroups()
  await loadUsers()
})
</script>

<style scoped>
.page-header { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 24px; }
.page-title { margin: 0; font-size: 22px; color: var(--color-text-primary); }
.page-subtitle { margin: 6px 0 0; color: var(--color-text-tertiary); font-size: 14px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 16px; }
.group-tag { margin-right: 6px; }
.role-tag { margin-right: 6px; }
.muted { color: var(--color-text-tertiary); }
</style>
