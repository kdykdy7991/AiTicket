<template>
  <div class="ticket-create-view">
    <div class="page-header">
      <button class="back-btn" @click="router.back()">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
        </svg>
        返回
      </button>
      <h2 class="page-title">{{ editingDraftId ? '编辑草稿' : '新建工单' }}</h2>
      <p class="page-subtitle">填写客户与问题信息，提交后将自动分配</p>
    </div>

    <div class="form-container">
      <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="onSubmit" class="create-form">
        <!-- 一、客户信息 -->
        <div class="section">
          <div class="section-title">
            <span class="section-num">1</span>
            <span>客户信息</span>
          </div>
          <div class="form-row">
            <el-form-item label="用户类型" prop="customer_type" class="form-col">
              <el-radio-group v-model="form.customer_type">
                <el-radio-button value="personal">个人</el-radio-button>
                <el-radio-button value="enterprise">政企</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="来电号码" prop="customer_phone" class="form-col">
              <el-input v-model="form.customer_phone" placeholder="客户来电号码" maxlength="20" size="large" />
            </el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="联系人" prop="contact_name" class="form-col">
              <el-input v-model="form.contact_name" placeholder="联系人姓名" size="large" />
            </el-form-item>
            <el-form-item label="联系号码" prop="contact_phone" class="form-col">
              <el-input v-model="form.contact_phone" placeholder="联系人号码" maxlength="20" size="large" />
            </el-form-item>
          </div>
          <el-form-item v-if="form.customer_type === 'enterprise'" label="单位名称" prop="customer_company" :required="true">
            <el-input v-model="form.customer_company" placeholder="政企单位名称" maxlength="200" show-word-limit size="large" />
          </el-form-item>
          <el-form-item label="终端 / 设备 SN" prop="device_sn">
            <el-input v-model="form.device_sn" placeholder="设备序列号（选填）" size="large" />
          </el-form-item>
          <el-form-item label="所属区域" prop="region_name">
            <el-input
              v-model="form.region_name"
              placeholder="请输入所属区域"
              maxlength="200"
              show-word-limit
              size="large"
              clearable
            />
          </el-form-item>
        </div>

        <!-- 二、工单信息 -->
        <div class="section">
          <div class="section-title">
            <span class="section-num">2</span>
            <span>工单信息</span>
          </div>
          <div class="form-row">
            <el-form-item label="一级分类" prop="category_l1_id" class="form-col">
              <el-select v-model="form.category_l1_id" placeholder="选择一级分类" style="width: 100%" @change="onCategoryL1Change">
                <el-option v-for="c in categoriesL1" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="二级分类" prop="category_l2_id" class="form-col">
              <el-select v-model="form.category_l2_id" placeholder="选择二级分类" style="width: 100%" :disabled="!form.category_l1_id" clearable>
                <el-option v-for="c in categoriesL2" :key="c.id" :label="c.name" :value="c.id" />
              </el-select>
            </el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="对接部门" prop="skill_group_id" class="form-col">
              <el-select v-model="form.skill_group_id" placeholder="技术/市场/售后" style="width: 100%" @change="onSkillGroupChange">
                <el-option v-for="g in skillGroups" :key="g.id" :label="g.name" :value="g.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="部门对接人" prop="dispatcher_id" class="form-col">
              <el-select v-model="form.dispatcher_id" placeholder="选择部门对接人" style="width: 100%" filterable :disabled="!form.skill_group_id">
                <el-option v-for="d in dispatchers" :key="d.id" :label="d.name" :value="d.id" />
              </el-select>
            </el-form-item>
          </div>
          <div class="form-row">
            <el-form-item label="优先级" prop="priority_id" class="form-col">
              <el-select v-model="form.priority_id" placeholder="选择优先级" style="width: 100%">
                <el-option v-for="p in availablePriorities" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item label="工单来源" prop="channel" class="form-col">
              <el-select v-model="form.channel" placeholder="选择来源" style="width: 100%">
                <el-option label="Web" value="web" />
                <el-option label="邮件" value="email" />
                <el-option label="电话" value="phone" />
                <el-option label="微信服务号" value="wechat" />
                <el-option label="App" value="app" />
              </el-select>
            </el-form-item>
          </div>
          <el-form-item label="问题详情" prop="body">
            <el-input
              v-model="form.body"
              type="textarea"
              :rows="6"
              placeholder="详细描述问题..."
              maxlength="2000"
              show-word-limit
            />
          </el-form-item>
        </div>

        <div class="form-actions">
          <el-button @click="router.back()">取消</el-button>
          <el-button @click="onSaveDraft" :loading="savingDraft">暂存</el-button>
          <el-button type="primary" native-type="submit" :loading="submitting" class="submit-btn">
            提交工单
          </el-button>
        </div>
      </el-form>
    </div>

  </div>
</template>

<script setup lang="ts">
import { reactive, ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { metaApi } from '@/api/overviews'
import { ticketApi, draftApi } from '@/api/tickets'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import type {
  Group, TicketPriority, TicketCategory,
} from '@/types'

const router = useRouter()
const route = useRoute()
const ticketStore = useTicketStore()
const formRef = ref<FormInstance>()
const submitting = ref(false)
const savingDraft = ref(false)
const editingDraftId = ref<number | null>(null)

const groups = ref<Group[]>([])
const skillGroups = ref<Group[]>([])
const dispatchers = ref<any[]>([])
const priorities = ref<TicketPriority[]>([])
const categories = ref<TicketCategory[]>([])

const form = reactive({
  customer_type: 'personal' as 'personal' | 'enterprise',
  customer_phone: '',
  contact_name: '',
  contact_phone: '',
  customer_company: '',
  device_sn: '',
  region_name: '',
  category_l1_id: null as number | null,
  category_l2_id: null as number | null,
  group_id: null as number | null,
  skill_group_id: null as number | null,
  dispatcher_id: null as number | null,
  priority_id: null as number | null,
  channel: 'phone' as 'web' | 'email' | 'phone' | 'wechat' | 'app',
  body: '',
})

const rules: FormRules = {
  customer_type: [{ required: true, message: '请选择用户类型', trigger: 'change' }],
  customer_phone: [
    { required: true, message: '请输入来电号码', trigger: 'blur' },
    { pattern: /^1[3-9]\d{9}$/, message: '请输入正确的来电号码', trigger: 'blur' },
  ],
  contact_phone: [
    { required: true, message: '请输入联系号码', trigger: 'blur' },
  ],
  customer_company: [{
    validator: (_r, _v, cb) => {
      if (form.customer_type === 'enterprise' && !form.customer_company.trim()) {
        return cb(new Error('政企工单必须填写单位名称'))
      }
      cb()
    },
    trigger: 'blur',
  }],
  skill_group_id: [{ required: true, message: '请选择对接部门', trigger: 'change' }],
  dispatcher_id: [{ required: true, message: '请选择部门对接人', trigger: 'change' }],
  priority_id: [{ required: true, message: '请选择优先级', trigger: 'change' }],
  channel: [{ required: true, message: '请选择工单来源', trigger: 'change' }],
  category_l1_id: [{ required: true, message: '请选择一级分类', trigger: 'change' }],
  body: [{ required: true, message: '请输入问题详情', trigger: 'blur' }],
}

const categoriesL1 = computed(() => categories.value.filter(c => c.parent_id === null))
const categoriesL2 = computed(() => categories.value.filter(c => c.parent_id === form.category_l1_id))

const availablePriorities = computed(() => {
  if (form.customer_type === 'enterprise') return priorities.value
  return priorities.value.filter(p => p.customer_type_restriction !== 'enterprise')
})

function onCategoryL1Change() {
  form.category_l2_id = null
}

onMounted(async () => {
  const [g, sg, p, cats] = await Promise.all([
    metaApi.getGroups(), metaApi.getSkillGroups(),
    metaApi.getPriorities(), metaApi.getCategories(),
  ])
  groups.value = g
  skillGroups.value = sg
  priorities.value = p
  categories.value = cats
  form.priority_id = p.find(x => x.name === 'P4 一般事件')?.id || p.find(x => x.id === 4)?.id || p[0]?.id || null
  form.group_id = g[0]?.id || null

  // 从草稿加载
  const draftId = route.query.draft_id
  if (draftId) {
    try {
      const draft = await ticketApi.get(Number(draftId))
      editingDraftId.value = draft.id
      // 回填表单
      form.customer_type = draft.customer_type || form.customer_type
      form.customer_phone = draft.customer_phone || form.customer_phone
      form.contact_name = (draft as any).contact_name || draft.customer_name || ''
      form.contact_phone = draft.contact_phone || form.contact_phone
      form.customer_company = (draft as any).customer_company || ''
      form.device_sn = draft.device_sn || form.device_sn
      form.region_name = draft.region_name || form.region_name
      form.category_l1_id = (draft as any).category_l1_id || null
      form.category_l2_id = (draft as any).category_l2_id || null
      form.skill_group_id = draft.skill_group_id || form.skill_group_id
      form.dispatcher_id = (draft as any).dispatcher_id || null
      form.channel = draft.channel || form.channel
      form.body = (draft as any).description || form.body
      // 优先级：从后端字符串反查 ID
      const stateStrToPriority = (s: string) => {
        const map: Record<string, number> = { 'p1_urgent': 1, 'p2_high': 2, 'p3_normal': 3, 'p4_enterprise': 4 }
        return map[s] || form.priority_id
      }
      form.priority_id = stateStrToPriority(draft.priority) || form.priority_id
      if (form.skill_group_id) {
        dispatchers.value = await metaApi.getDispatchers(form.skill_group_id)
      }
    } catch {
      ElMessage.warning('加载草稿失败')
    }
  }
})

// 选对接部门后联动加载该部门的部门对接人
async function onSkillGroupChange() {
  form.dispatcher_id = null
  dispatchers.value = []
  if (form.skill_group_id) {
    dispatchers.value = await metaApi.getDispatchers(form.skill_group_id)
  }
}

// 监听 draft_id 变化：从编辑草稿切换到新建工单时重置表单
watch(() => route.query.draft_id, (newDraftId, oldDraftId) => {
  if (!newDraftId && oldDraftId) {
    // draft_id 被清除，重置表单为新建状态
    editingDraftId.value = null
    form.customer_type = 'personal'
    form.customer_phone = ''
    form.contact_name = ''
    form.contact_phone = ''
    form.customer_company = ''
    form.device_sn = ''
    form.region_name = ''
    form.category_l1_id = null
    form.category_l2_id = null
    form.group_id = groups.value[0]?.id || null
    form.skill_group_id = null
    form.dispatcher_id = null
    form.priority_id = priorities.value.find(x => x.name === 'P4 一般事件')?.id || priorities.value.find(x => x.id === 4)?.id || priorities.value[0]?.id || null
    form.channel = 'phone'
    form.body = ''
    dispatchers.value = []
  }
})

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  await doSubmit()
}

async function onSaveDraft() {
  savingDraft.value = true
  try {
    const payload = buildFormPayload({ is_draft: true })
    if (editingDraftId.value) {
      // 编辑已有草稿：更新当前草稿
      await draftApi.update(editingDraftId.value, payload)
    } else {
      // 新建草稿
      await draftApi.save(payload)
    }
    ElMessage.success('已暂存')
    router.push({ name: 'TicketDrafts' })
  } finally {
    savingDraft.value = false
  }
}

/** 构建表单载荷 */
function buildFormPayload(extra: Record<string, any> = {}): Record<string, any> {
  return {
    ...extra,
    customer_type: form.customer_type,
    customer_phone: form.customer_phone,
    customer_company: form.customer_company || null,
    device_sn: form.device_sn || null,
    contact_name: form.contact_name || null,
    contact_phone: form.contact_phone || null,
    region_name: form.region_name || null,
    category_l1_id: form.category_l1_id,
    category_l2_id: form.category_l2_id,
    skill_group_id: form.skill_group_id,
    dispatcher_id: form.dispatcher_id,
    channel: form.channel,
    article: { body: form.body, content_type: 'text/plain' },
    priority_id: form.priority_id,
    group_id: form.group_id,
  }
}

async function doSubmit() {
  submitting.value = true
  try {
    const ticket = await ticketStore.createTicket({
      group_id: form.group_id!,
      priority_id: form.priority_id!,
      channel: form.channel,
      customer_type: form.customer_type,
      customer_phone: form.customer_phone,
      customer_company: form.customer_company || null,
      device_sn: form.device_sn || null,
      contact_name: form.contact_name || null,
      contact_phone: form.contact_phone || null,
      region_name: form.region_name || null,
      category_l1_id: form.category_l1_id,
      category_l2_id: form.category_l2_id,
      skill_group_id: form.skill_group_id,
      dispatcher_id: form.dispatcher_id,
      article: { body: form.body, content_type: 'text/plain' },
    })
    // 如果是从草稿提交的，删除原草稿
    if (editingDraftId.value) {
      await draftApi.delete(editingDraftId.value).catch(() => {})
    }
    ElMessage.success('工单创建成功')
    router.push({ name: 'TicketDetail', params: { id: ticket.id } })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page-header {
  margin-bottom: 32px;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--color-text-tertiary);
  font-size: 13px;
  font-weight: 500;
  border: none;
  background: none;
  cursor: pointer;
  padding: 4px 0;
  font-family: var(--font-sans);
  transition: color var(--duration-fast) var(--ease-out);
  margin-bottom: 16px;
}
.back-btn:hover { color: var(--color-primary); }

.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--color-text-primary);
  letter-spacing: -0.02em;
  margin: 0;
}
.page-subtitle {
  font-size: 14px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}

.form-container {
  max-width: 760px;
}

.section {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 20px 24px 4px;
  margin-bottom: 16px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin-bottom: 16px;
}

.section-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: var(--radius-full);
  background: var(--color-primary-light);
  color: var(--color-primary);
  font-size: 12px;
  font-weight: 700;
}

.section-hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  font-weight: 400;
}

.create-form :deep(.el-form-item__label) {
  font-weight: 600;
  font-size: 13px;
  color: var(--color-text-secondary);
  padding-bottom: 6px;
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding-top: 16px;
}

.submit-btn {
  min-width: 120px;
  font-weight: 600;
}
</style>
