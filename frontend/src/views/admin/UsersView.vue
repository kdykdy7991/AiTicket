<template>
  <div class="users-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">用户管理</h2>
        <p class="page-subtitle">管理系统用户、角色与对接部门归属</p>
      </div>
      <el-button type="primary" @click="openCreate">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right: 6px"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        新建用户
      </el-button>
    </div>

    <!-- 筛选 -->
    <div class="filter-bar">
      <el-select v-model="filterRole" placeholder="全部角色" clearable size="default" style="width: 140px" @change="loadUsers">
        <el-option label="管理员" value="admin" />
        <el-option label="客服坐席" value="agent" />
        <el-option label="处理人" value="handler" />
      </el-select>
      <el-select v-model="filterSkillGroup" placeholder="全部对接部门" clearable size="default" style="width: 160px" @change="loadUsers">
        <el-option v-for="g in skillGroups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-input v-model="keyword" placeholder="搜索用户名/姓名" clearable size="default" style="width: 220px" @keyup.enter="loadUsers" @clear="loadUsers" />
      <el-checkbox v-model="includeInactive" @change="loadUsers">显示已禁用</el-checkbox>
    </div>

    <!-- 列表 -->
    <el-card shadow="never" v-loading="loading" class="list-card">
      <el-table :data="users" stripe>
        <el-table-column label="用户名" prop="username" width="130" />
        <el-table-column label="姓名" prop="name" width="110" />
        <el-table-column label="角色" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="roleTagType(row.role)">{{ roleLabel(row.role) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="所属组">
          <template #default="{ row }">
            <!-- 客服：显示客服组 -->
            <template v-if="row.role === 'agent'">
              <el-tag size="small">{{ groupName(row.group_id) }}</el-tag>
              <el-tag v-if="row.is_group_leader" size="small" type="warning" style="margin-left: 4px">组长</el-tag>
            </template>
            <!-- 部门人员：显示对接部门（带对接人标记） -->
            <span v-else-if="row.skill_groups?.length">
              <el-tag
                v-for="m in row.skill_groups"
                :key="m.skill_group_id"
                size="small"
                :type="m.is_dispatcher ? 'danger' : 'info'"
                :plain="!m.is_dispatcher"
                style="margin-right: 4px"
              >
                {{ skillGroupName(m.skill_group_id) }}{{ m.is_dispatcher ? '·对接' : '' }}
              </el-tag>
            </span>
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
            <el-button v-if="row.is_active" text size="small" type="danger" @click="onDisable(row)">禁用</el-button>
            <el-button v-else text size="small" type="success" @click="onActivate(row)">启用</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="editing ? '编辑用户' : '新建用户'" width="560px" align-center :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="90px">
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" :disabled="editing" placeholder="登录用用户名" />
        </el-form-item>
        <el-form-item label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="显示姓名" />
        </el-form-item>
        <el-form-item label="手机号" prop="phone">
          <el-input v-model="form.phone" placeholder="选填" />
        </el-form-item>
        <el-form-item label="密码" :prop="editing ? undefined : 'password'">
          <el-input v-model="form.password" type="password" show-password :placeholder="editing ? '留空则不修改' : '请输入密码'" />
        </el-form-item>
        <el-form-item label="角色" prop="role">
          <el-select v-model="form.role" style="width: 100%" @change="onRoleChange">
            <el-option label="管理员" value="admin" />
            <el-option label="客服坐席" value="agent" />
            <el-option label="处理人" value="handler" />
          </el-select>
        </el-form-item>
        <!-- 客服坐席：选客服组 + 组长开关 -->
        <template v-if="form.role === 'agent'">
          <el-form-item label="客服组" prop="group_id">
            <el-select v-model="form.group_id" style="width: 100%" clearable placeholder="选择客服组">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="组长">
            <el-switch v-model="form.is_group_leader" />
          </el-form-item>
        </template>
        <!-- 处理人：选对接部门 + 对接人标记 -->
        <el-form-item v-else-if="form.role === 'handler'" label="对接部门" prop="skill_groups">
          <el-checkbox-group v-model="form.skill_group_ids" @change="onSkillGroupSelect" style="width: 100%">
            <el-checkbox v-for="g in skillGroups" :key="g.id" :label="g.id">{{ g.name }}</el-checkbox>
          </el-checkbox-group>
          <div v-if="form.skill_groups.length" class="dispatcher-list">
            <div v-for="m in form.skill_groups" :key="m.skill_group_id" class="dispatcher-row">
              <span class="dispatcher-name">{{ skillGroupName(m.skill_group_id) }}</span>
              <el-checkbox v-model="m.is_dispatcher">部门对接人</el-checkbox>
            </div>
          </div>
        </el-form-item>
        <el-form-item label="钉钉ID" prop="dingtalk_id">
          <el-input v-model="form.dingtalk_id" placeholder="选填，用于钉钉通知" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { userApi, type UserItem, type UserPayload } from '@/api/users'
import { metaApi } from '@/api/overviews'
import type { Group } from '@/types'

const loading = ref(false)
const saving = ref(false)
const users = ref<UserItem[]>([])
const groups = ref<Group[]>([])
const skillGroups = ref<Group[]>([])

const filterRole = ref('')
const filterSkillGroup = ref<number | ''>('')
const keyword = ref('')
const includeInactive = ref(false)

const dialogVisible = ref(false)
const editing = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({
  username: '',
  name: '',
  phone: '',
  password: '',
  role: 'agent',
  group_id: null as number | null,
  skill_group_ids: [] as number[],
  skill_groups: [] as { skill_group_id: number; is_dispatcher: boolean }[],
  is_group_leader: false,
  dingtalk_id: '',
})

const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  role: [{ required: true, message: '请选择角色', trigger: 'change' }],
}

function roleLabel(role: string) {
  return role === 'admin' ? '管理员' : role === 'agent' ? '客服坐席' : role === 'handler' ? '处理人' : role
}
function roleTagType(role: string) {
  return role === 'admin' ? 'danger' : role === 'agent' ? '' : 'info'
}
function groupName(id: number | null) {
  return groups.value.find(g => g.id === id)?.name || '—'
}
function skillGroupNames(ids: number[]) {
  return ids.map(id => skillGroups.value.find(g => g.id === id)?.name).filter(Boolean) as string[]
}
function skillGroupName(id: number) {
  return skillGroups.value.find(g => g.id === id)?.name || ''
}
// 勾选对接部门时，同步 skill_groups 数组（保留已有对接人标记）
function onSkillGroupSelect(selected: number[]) {
  const existing = new Map(form.skill_groups.map(m => [m.skill_group_id, m.is_dispatcher]))
  form.skill_groups = selected.map(id => ({
    skill_group_id: id,
    is_dispatcher: existing.get(id) ?? false,
  }))
}
// 切换角色时，清空另一种组（客服组与对接部门互斥）
function onRoleChange() {
  if (form.role === 'agent') {
    form.skill_group_ids = []
    form.skill_groups = []
  } else if (form.role === 'handler') {
    form.group_id = null
    form.is_group_leader = false
  }
}

async function loadUsers() {
  const start = performance.now()
  loading.value = true
  try {
    const list = await userApi.list({
      role: filterRole.value || undefined,
      skill_group_id: filterSkillGroup.value || undefined,
      keyword: keyword.value || undefined,
      include_inactive: includeInactive.value,
      _t: Date.now(),  // 防止 GET 请求被缓存
    })
    users.value = list
    console.log(`[UsersView] loadUsers API+渲染: ${(performance.now() - start).toFixed(1)}ms, 用户数: ${list.length}`)
  } catch (e) {
    console.error('[UsersView] loadUsers 失败', e)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.username = ''
  form.name = ''
  form.phone = ''
  form.password = ''
  form.role = 'agent'
  form.group_id = groups.value[0]?.id || null
  form.skill_group_ids = []
  form.skill_groups = []
  form.is_group_leader = false
  form.dingtalk_id = ''
}

function openCreate() {
  editing.value = false
  editingId.value = null
  resetForm()
  dialogVisible.value = true
}

function openEdit(row: UserItem) {
  editing.value = true
  editingId.value = row.id
  form.username = row.username
  form.name = row.name
  form.phone = row.phone || ''
  form.password = ''
  form.role = row.role
  form.group_id = row.group_id
  form.skill_group_ids = (row.skill_groups || []).map(m => m.skill_group_id)
  form.skill_groups = (row.skill_groups || []).map(m => ({ skill_group_id: m.skill_group_id, is_dispatcher: m.is_dispatcher }))
  form.is_group_leader = row.is_group_leader
  form.dingtalk_id = row.dingtalk_id || ''
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload: UserPayload = {
      name: form.name,
      phone: form.phone || null,
      role: form.role,
      group_id: form.group_id,
      skill_groups: form.skill_groups,
      is_group_leader: form.role === 'agent' ? form.is_group_leader : false,
      dingtalk_id: form.dingtalk_id || null,
    }
    if (form.password) payload.password = form.password
    if (editing.value && editingId.value) {
      await userApi.update(editingId.value, payload)
      ElMessage.success('用户已更新')
    } else {
      payload.username = form.username
      await userApi.create(payload)
      ElMessage.success('用户已创建')
    }
    dialogVisible.value = false
    await loadUsers()
  } finally {
    saving.value = false
  }
}

async function onDisable(row: UserItem) {
  try {
    await ElMessageBox.confirm(`确定要禁用用户「${row.name}」吗？禁用后该用户将无法登录。`, '禁用用户', { type: 'warning' })
  } catch { return }
  await userApi.disable(row.id)
  ElMessage.success('已禁用')
  // 本地立即更新状态 + 重新加载确保一致
  row.is_active = false
  await loadUsers()
}

async function onActivate(row: UserItem) {
  await userApi.activate(row.id)
  ElMessage.success('已启用')
  row.is_active = true
  await loadUsers()
}

onMounted(async () => {
  const start = performance.now()
  const metaStart = performance.now()
  const [g, sg] = await Promise.all([metaApi.getGroups(), metaApi.getSkillGroups()])
  groups.value = g
  skillGroups.value = sg
  console.log(`[UsersView] 分组数据加载: ${(performance.now() - metaStart).toFixed(1)}ms`)
  await loadUsers()
  console.log(`[UsersView] 页面总加载（含分组数据）: ${(performance.now() - start).toFixed(1)}ms`)
})
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
.page-title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-text-tertiary); margin-top: 4px; }
.filter-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.list-card { border-radius: var(--radius-lg); }
.muted { color: var(--color-text-tertiary); }
.dispatcher-list { margin-top: 8px; border-top: 1px solid var(--color-border-light); padding-top: 8px; }
.dispatcher-row { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.dispatcher-name { color: var(--color-text-secondary); }
</style>
