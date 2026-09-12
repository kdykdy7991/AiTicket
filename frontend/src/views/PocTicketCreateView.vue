<template>
  <div class="create-view">
    <div class="page-header">
      <div>
        <h1>新建 POC 问题</h1>
        <p>填写现场问题信息并提交批准人审批</p>
      </div>
      <el-tag v-if="draftId" type="info">草稿 #{{ draftId }}</el-tag>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" status-icon>
      <el-card shadow="never" class="form-card">
        <template #header><strong>基本信息</strong></template>
        <div class="form-grid">
          <el-form-item label="问题名称" prop="title" class="span-2">
            <el-input v-model="form.title" maxlength="500" show-word-limit placeholder="一句话概括 POC 问题" />
          </el-form-item>
          <el-form-item label="提出人" prop="proposer">
            <el-input v-model="form.proposer" maxlength="100" placeholder="填写实际反馈问题的人" />
          </el-form-item>
          <el-form-item label="提出部门" prop="proposer_department">
            <el-input v-model="form.proposer_department" maxlength="100" placeholder="填写提出人所属部门" />
          </el-form-item>
          <el-form-item label="产品线" prop="product_line">
            <el-input v-model="form.product_line" maxlength="100" placeholder="填写产品线" />
          </el-form-item>
          <el-form-item label="客户名称" prop="customer_name">
            <el-input v-model="form.customer_name" maxlength="100" placeholder="填写客户名称" />
          </el-form-item>
          <el-form-item label="问题级别" prop="priority">
            <el-select v-model="form.priority" style="width: 100%">
              <el-option v-for="option in POC_PRIORITY_OPTIONS" :key="option.value" :label="option.label" :value="option.value">
                <span class="priority-option"><i :style="{ background: option.color }" />{{ option.label }}</span>
              </el-option>
            </el-select>
          </el-form-item>
          <el-form-item label="问题类型" prop="problem_type">
            <el-input v-model="form.problem_type" maxlength="100" placeholder="例如：功能、性能、稳定性" />
          </el-form-item>
          <el-form-item label="批准人" prop="approver_id">
            <el-select v-model="form.approver_id" filterable style="width: 100%" placeholder="选择批准人" :loading="approversLoading">
              <el-option v-for="user in approvers" :key="user.id" :label="user.name" :value="user.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="闭环要求" prop="closure_requirement" class="span-2">
            <el-input v-model="form.closure_requirement" type="textarea" :rows="3" placeholder="填写期望完成时间、交付物和闭环标准" />
          </el-form-item>
        </div>
      </el-card>

      <el-card shadow="never" class="form-card">
        <template #header><strong>问题现象</strong></template>
        <div class="form-grid">
          <el-form-item label="发生时间" prop="occurred_at">
            <el-date-picker v-model="form.occurred_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" placeholder="选择发生时间" style="width: 100%" />
          </el-form-item>
          <el-form-item label="发生地点" prop="location">
            <el-input v-model="form.location" maxlength="300" placeholder="填写现场地点" />
          </el-form-item>
          <el-form-item label="经度">
            <el-input-number v-model="form.longitude" :min="-180" :max="180" :precision="7" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="纬度">
            <el-input-number v-model="form.latitude" :min="-90" :max="90" :precision="7" controls-position="right" style="width: 100%" />
          </el-form-item>
          <el-form-item label="设备信息" prop="device_info" class="span-2">
            <el-input v-model="form.device_info" type="textarea" :rows="3" placeholder="设备名称、型号、编号、版本和配置等" />
          </el-form-item>
          <el-form-item label="问题现象概述" prop="description" class="span-2">
            <el-input v-model="form.description" type="textarea" :rows="6" maxlength="10000" show-word-limit placeholder="描述问题现象、触发条件、影响范围和复现步骤" />
          </el-form-item>
        </div>
      </el-card>

      <div class="form-actions">
        <el-button @click="router.push('/tickets')">取消</el-button>
        <el-button :loading="saving" @click="saveDraft(false)">保存草稿</el-button>
        <el-button type="primary" :loading="submitting" @click="submitForApproval">提交审批</el-button>
      </div>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, type FormInstance, type FormRules } from 'element-plus'
import { pocTicketApi } from '@/api/pocTickets'
import { userApi, type UserItem } from '@/api/users'
import { POC_PRIORITY_OPTIONS } from '@/domain/pocWorkflow'
import type { PocTicketForm } from '@/types/poc'

const route = useRoute()
const router = useRouter()
const formRef = ref<FormInstance>()
const approvers = ref<UserItem[]>([])
const approversLoading = ref(false)
const saving = ref(false)
const submitting = ref(false)
const draftId = ref<number | null>(Number(route.query.draft_id) || null)

const form = reactive<PocTicketForm>({
  title: '', proposer: '', proposer_department: '',
  product_line: '', customer_name: '', priority: 'p2_normal',
  problem_type: '', closure_requirement: '', occurred_at: '', location: '',
  longitude: null, latitude: null, device_info: '', description: '', approver_id: null,
})

const required = (message: string) => [{ required: true, message, trigger: ['blur', 'change'] }]
const rules: FormRules = {
  title: required('请输入问题名称'), proposer: required('请输入提出人'),
  proposer_department: required('请输入提出部门'), product_line: required('请输入产品线'),
  customer_name: required('请输入客户名称'), priority: required('请选择问题级别'),
  problem_type: required('请输入问题类型'), closure_requirement: required('请输入闭环要求'),
  occurred_at: required('请选择发生时间'), location: required('请输入发生地点'),
  device_info: required('请输入设备信息'), description: required('请输入问题现象'),
  approver_id: required('请选择批准人'),
}

function payload(): PocTicketForm {
  return { ...form }
}

async function saveDraft(showMessage = true) {
  saving.value = true
  try {
    const draft = draftId.value
      ? await pocTicketApi.updateDraft(draftId.value, payload())
      : await pocTicketApi.createDraft(payload())
    draftId.value = draft.id
    await router.replace({ query: { ...route.query, draft_id: String(draft.id) } })
    if (showMessage) ElMessage.success('草稿已保存')
    return draft
  } finally {
    saving.value = false
  }
}

async function submitForApproval() {
  if (!await formRef.value?.validate().catch(() => false)) return
  submitting.value = true
  try {
    if (!draftId.value) await saveDraft(false)
    if (!draftId.value) return
    const ticket = await pocTicketApi.submitDraft(draftId.value, payload())
    ElMessage.success('已提交，等待批准人审批')
    await router.push({ name: 'TicketDetail', params: { id: ticket.id } })
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  approversLoading.value = true
  try {
    const [approverList, draft] = await Promise.all([
      userApi.list({ role: 'approver' }),
      draftId.value ? pocTicketApi.get(draftId.value) : Promise.resolve(null),
    ])
    approvers.value = approverList
    if (draft) {
      Object.assign(form, {
        title: draft.title || '', product_line: draft.product_line || '', customer_name: draft.customer_name || '',
        priority: draft.priority, problem_type: draft.problem_type || '', closure_requirement: draft.closure_requirement || '',
        occurred_at: draft.occurred_at || '', location: draft.location || '', longitude: draft.longitude, latitude: draft.latitude,
        device_info: draft.device_info || '', description: draft.description || '', approver_id: draft.approver_id,
      })
    }
    if (!form.approver_id && approvers.value.length === 1) form.approver_id = approvers.value[0].id
  } finally {
    approversLoading.value = false
  }
})
</script>

<style scoped>
.create-view { max-width: 1040px; margin: 0 auto; padding-bottom: 32px; }
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; }
.page-header h1 { margin: 0; font-size: 24px; color: var(--color-text-primary); }
.page-header p { margin: 6px 0 0; color: var(--color-text-tertiary); }
.form-card { margin-bottom: 16px; border-color: var(--color-border-light); }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); column-gap: 24px; }
.span-2 { grid-column: span 2; }
.form-actions { display: flex; justify-content: flex-end; gap: 10px; position: sticky; bottom: 0; padding: 16px; background: rgba(255, 255, 255, 0.94); border-top: 1px solid var(--color-border-light); backdrop-filter: blur(8px); z-index: 2; }
.priority-option { display: inline-flex; align-items: center; gap: 8px; }
.priority-option i { width: 8px; height: 8px; border-radius: 50%; }
@media (max-width: 760px) { .form-grid { grid-template-columns: 1fr; } .span-2 { grid-column: span 1; } }
</style>
