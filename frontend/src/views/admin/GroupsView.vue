<template>
  <div class="groups-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">组管理</h2>
      </div>
    </div>

    <!-- 客服组 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <h3 class="section-title">客服组</h3>
          <span class="section-hint">工单归属的客服团队，决定组长可见范围</span>
          <el-button v-if="auth.isAdmin" type="primary" size="small" @click="openCreate('group')">新建客服组</el-button>
        </div>
      </template>
      <el-table :data="groups" :key="groupKey" v-loading="loadingGroup">
        <el-table-column label="名称" prop="name" width="180" />
        <el-table-column label="钉钉 Webhook">
          <template #default="{ row }">
            <span v-if="row.dingtalk_webhook_url" class="webhook">{{ maskWebhook(row.dingtalk_webhook_url) }}</span>
            <span v-else class="muted">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" :disabled="!row.dingtalk_webhook_url" @click="onTestDingtalk('group', row)">测试机器人</el-button>
            <el-button text size="small" @click="openEdit('group', row)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onRemove('group', row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 对接部门 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header">
          <h3 class="section-title">对接部门</h3>
          <span class="section-hint">工单派发去向，如技术/市场/售后</span>
          <el-button v-if="auth.isAdmin" type="primary" size="small" @click="openCreate('skill')">新建对接部门</el-button>
        </div>
      </template>
      <el-table :data="skillGroups" :key="skillKey" v-loading="loadingSkill">
        <el-table-column label="名称" prop="name" width="180" />
        <el-table-column label="钉钉 Webhook">
          <template #default="{ row }">
            <span v-if="row.dingtalk_webhook_url" class="webhook">{{ maskWebhook(row.dingtalk_webhook_url) }}</span>
            <span v-else class="muted">未配置</span>
          </template>
        </el-table-column>
        <el-table-column label="创建时间" width="180">
          <template #default="{ row }">{{ formatDate(row.created_at) }}</template>
        </el-table-column>
        <el-table-column v-if="auth.isAdmin" label="操作" width="210" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" :disabled="!row.dingtalk_webhook_url" @click="onTestDingtalk('skill', row)">测试机器人</el-button>
            <el-button text size="small" @click="openEdit('skill', row)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onRemove('skill', row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" align-center append-to-body class="ticket-dark-dialog groups-dialog" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item :label="formType === 'group' ? '客服组名称' : '对接部门名称'" prop="name">
          <el-input v-model="form.name" placeholder="如：技术组" />
        </el-form-item>
        <el-form-item label="钉钉 Webhook" prop="dingtalk_webhook_url">
          <el-input v-model="form.dingtalk_webhook_url" placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
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
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { groupApi, skillGroupApi, type GroupItem } from '@/api/groups'
import { useAuthStore } from '@/stores/auth'

const loadingGroup = ref(false)
const auth = useAuthStore()
const loadingSkill = ref(false)
const saving = ref(false)
const groups = ref<GroupItem[]>([])
const skillGroups = ref<GroupItem[]>([])
const groupKey = ref(0)
const skillKey = ref(0)

const dialogVisible = ref(false)
const formType = ref<'group' | 'skill'>('group')
const editing = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  dingtalk_webhook_url: '',
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }],
}

const dialogTitle = computed(() => {
  const t = formType.value === 'group' ? '客服组' : '对接部门'
  return `${editing.value ? '编辑' : '新建'}${t}`
})

function maskWebhook(url: string) {
  // 只显示前 40 字符 + ...
  return url.length > 40 ? url.slice(0, 40) + '...' : url
}
function formatDate(iso: string) {
  return new Date(iso).toLocaleString('zh-CN', { hour12: false })
}

async function loadGroups() {
  loadingGroup.value = true
  try {
    groups.value = await groupApi.list()
    groupKey.value++
  } finally { loadingGroup.value = false }
}
async function loadSkillGroups() {
  loadingSkill.value = true
  try {
    skillGroups.value = await skillGroupApi.list()
    skillKey.value++
  } finally { loadingSkill.value = false }
}

function openCreate(type: 'group' | 'skill') {
  formType.value = type
  editing.value = false
  editingId.value = null
  form.name = ''
  form.dingtalk_webhook_url = ''
  dialogVisible.value = true
}
function openEdit(type: 'group' | 'skill', row: GroupItem) {
  formType.value = type
  editing.value = true
  editingId.value = row.id
  form.name = row.name
  form.dingtalk_webhook_url = row.dingtalk_webhook_url || ''
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = { name: form.name, dingtalk_webhook_url: form.dingtalk_webhook_url || null }
    if (editing.value && editingId.value) {
      if (formType.value === 'group') await groupApi.update(editingId.value, payload)
      else await skillGroupApi.update(editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      if (formType.value === 'group') await groupApi.create(payload)
      else await skillGroupApi.create(payload)
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    if (formType.value === 'group') await loadGroups()
    else await loadSkillGroups()
  } finally { saving.value = false }
}

async function onRemove(type: 'group' | 'skill', row: GroupItem) {
  const label = type === 'group' ? '客服组' : '对接部门'
  try {
    await ElMessageBox.confirm(`确定要删除${label}「${row.name}」吗？有用户或工单关联时无法删除。`, `删除${label}`, { type: 'warning', customClass: 'ticket-dark-dialog' })
  } catch { return }
  try {
    if (type === 'group') await groupApi.remove(row.id)
    else await skillGroupApi.remove(row.id)
    ElMessage.success('已删除')
    if (type === 'group') await loadGroups()
    else await loadSkillGroups()
  } catch (e: any) {
    // 后端返回 400 时拦截器已弹消息，这里兜底
    const msg = e?.response?.data?.error?.message || e?.response?.data?.detail
    if (msg) ElMessage.error(msg)
  }
}

async function onTestDingtalk(type: 'group' | 'skill', row: GroupItem) {
  try {
    if (type === 'group') await groupApi.testDingtalk(row.id)
    else await skillGroupApi.testDingtalk(row.id)
    ElMessage.success('测试消息已发送，请在钉钉群中确认')
  } catch (e: any) {
    const msg = e?.response?.data?.detail || '测试发送失败'
    ElMessage.error(msg)
  }
}

onMounted(() => {
  loadGroups()
  loadSkillGroups()
})
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-text-tertiary); margin-top: 4px; }
.section-card { margin-bottom: 20px; border-radius: var(--radius-lg); }
.section-header { display: flex; align-items: center; gap: 12px; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
.section-hint { font-size: 12px; color: var(--color-text-tertiary); flex: 1; }
.webhook { font-family: 'SF Mono', monospace; font-size: 12px; color: var(--color-text-secondary); word-break: break-all; }
.muted { color: var(--color-text-tertiary); }
.groups-view { min-width: 0; color: #eaf4ff; }
.page-header { margin: 4px 0 20px; }
.page-title { color: #f1f8ff; font-size: 28px; text-shadow: 0 0 17px #40aaff38; }
.section-card { position: relative; overflow: hidden; margin-bottom: 16px; border: 1px solid #0d8cda; border-radius: 6px; background: #041b37; box-shadow: 0 0 19px #006fca4d; }
.section-card::before, .section-card::after { content: ''; position: absolute; z-index: 2; width: 55px; height: 2px; background: #4bd5ff; box-shadow: 0 0 11px #4bd5ff; pointer-events: none; }
.section-card::before { top: 0; left: 13px; }
.section-card::after { bottom: 0; right: 13px; }
.section-card :deep(.el-card__header) { padding: 18px 21px; border-bottom: 1px solid #1b6193; background: linear-gradient(180deg, #0a335c, #082847); }
.section-card :deep(.el-card__body) { padding: 0; }
.section-header { gap: 16px; }
.section-title { color: #edf7ff; font-size: 18px; font-weight: 700; }
.section-hint { color: #91b7d7; font-size: 12px; }
.section-header :deep(.el-button) { min-width: 132px; height: 36px; font-weight: 600; }
.section-card :deep(.el-table) { --el-table-bg-color: #041b37; --el-table-tr-bg-color: #041b37; --el-table-header-bg-color: #0a315a; --el-table-row-hover-bg-color: #0b345b; --el-table-border-color: #0c3c65; --el-table-text-color: #c4d8f0; --el-table-header-text-color: #c9e2fb; background: #041b37; }
.section-card :deep(.el-table__header th.el-table__cell) { height: 46px; background: linear-gradient(180deg, #0c4278, #072c52); color: #c9e2fb; border-bottom-color: #1b6193; font-size: 12px; font-weight: 600; }
.section-card :deep(.el-table__body td.el-table__cell) { height: 48px; border-bottom-color: #0c385f; color: #c4d8f0; }
.section-card :deep(.el-table__body tr:nth-child(odd) > td.el-table__cell) { background: #031a34; }
.section-card :deep(.el-table__body tr:nth-child(even) > td.el-table__cell) { background: #051f3c; }
.section-card :deep(.el-table__body tr:hover > td.el-table__cell) { background: #0b345b; }
.section-card :deep(.el-table__empty-block) { background: #041b37; }
.section-card :deep(.el-table__empty-text) { color: #91afcb; }
.section-card :deep(.el-button.is-text) { color: #76caff; }
.section-card :deep(.el-button--danger.is-text) { color: #ffa8b9; }
.webhook { color: #9fc4e3; }
.muted { color: #91afcb; }
@media (max-width: 700px) { .page-title { font-size: 24px; } .section-header { flex-wrap: wrap; } .section-hint { flex-basis: 100%; order: 3; } .section-header :deep(.el-button) { margin-left: auto; min-width: 0; } }
</style>
