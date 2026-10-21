<template>
  <main class="page">
    <nav class="crumb"><router-link to="/tickets">工单管理</router-link><span>›</span><strong>创建工单</strong></nav>
    <h1>创建工单</h1>
    <form id="ticket-create-form" novalidate @submit.prevent="submitTicket">
      <div class="create-layout"><div class="form-main">
      <TicketFormSection title="工单信息" icon="MessageBox"><div class="grid intake-grid"><div class="field"><label for="channel" class="required">受理渠道</label><select id="channel" v-model="form.channel" :class="{ invalid: errors.channel }"><option v-for="v in channels" :key="v">{{ v }}</option></select><small v-if="errors.channel" class="error">{{ errors.channel }}</small></div><fieldset v-if="!isInstantConsult" class="field radio-field"><legend class="required">是否为线索工单</legend><div class="radio-options"><label><input v-model="form.businessOpportunity" type="radio" value="yes" /> 是</label><label><input v-model="form.businessOpportunity" type="radio" value="no" /> 否</label></div><small v-if="errors.businessOpportunity" class="error">{{ errors.businessOpportunity }}</small></fieldset></div></TicketFormSection>
      <TicketFormSection title="客户信息" icon="User"><div class="grid customer-grid">
        <div class="field"><label for="customerName" :class="{ required: !isInstantConsult }">客户名称</label><input id="customerName" v-model.trim="form.customerName" placeholder="请输入客户名称" :class="{ invalid: errors.customerName }" /><small v-if="errors.customerName" class="error">{{ errors.customerName }}</small></div>
        <div class="field"><label for="companyName" :class="{ required: !isInstantConsult }">单位全称</label><input id="companyName" v-model.trim="form.companyName" placeholder="请输入单位全称" :class="{ invalid: errors.companyName }" /><small v-if="errors.companyName" class="error">{{ errors.companyName }}</small></div>
        <div class="field"><label for="industry" :class="{ required: !isInstantConsult }">行业</label><select id="industry" v-model="form.industry" :class="{ invalid: errors.industry }"><option value="" :disabled="!isInstantConsult" hidden>请选择行业</option><option v-for="v in industries" :key="v">{{ v }}</option></select><small v-if="errors.industry" class="error">{{ errors.industry }}</small></div>
        <div class="field"><label for="callerPhone" class="required">来电号码</label><input id="callerPhone" v-model.trim="form.callerPhone" inputmode="tel" placeholder="请输入来电号码" :class="{ invalid: errors.callerPhone }" /><small v-if="errors.callerPhone" class="error">{{ errors.callerPhone }}</small></div>
        <div class="field"><label for="contactPhone" :class="{ required: isOpportunity }">联系号码</label><input id="contactPhone" v-model.trim="form.contactPhone" inputmode="tel" placeholder="请输入联系号码" :class="{ invalid: errors.contactPhone }" /><small v-if="!isOpportunity" class="help">联系方式与来电号码不同时补充</small><small v-if="errors.contactPhone" class="error">{{ errors.contactPhone }}</small></div>
      </div></TicketFormSection>
      <TicketFormSection title="工单内容" icon="Document"><div class="grid content-grid">
        <div v-if="isOpportunity || isReconciliation" class="field"><label for="salesUser" class="required">销售人员</label><select id="salesUser" v-model.number="form.salesUserId" :class="{ invalid: errors.salesUserId }"><option :value="null" disabled>请选择销售人员</option><option v-for="person in salesUsers" :key="person.id" :value="person.id">{{ person.name }}</option></select><small v-if="errors.salesUserId" class="error">{{ errors.salesUserId }}</small></div>
        <div v-if="!isOpportunity && !isInstantConsult" class="field"><label for="satelliteNumber" :class="{ required: numberRequired }">卫星物联网码号</label><input id="satelliteNumber" v-model.trim="form.satelliteNumber" placeholder="请输入卫星物联网码号" :class="{ invalid: errors.satelliteNumber }" /><small class="help">一级分类为业务运营/业务保障时必填</small><small v-if="errors.satelliteNumber" class="error">{{ errors.satelliteNumber }}</small></div>
        <div v-if="!isOpportunity" class="field"><label for="category" class="required">一级分类</label><select id="category" v-model="form.category" :class="{ invalid: errors.category }" @change="onCategoryChange"><option value="" disabled hidden>请选择一级分类</option><option v-for="v in categoryNames" :key="v">{{ v }}</option></select><small v-if="errors.category" class="error">{{ errors.category }}</small></div>
        <div v-if="!isOpportunity && !rootCategory?.create_selectable" class="field"><label for="subcategory" class="required">细分分类</label><select id="subcategory" v-model="form.subcategory" :disabled="!form.category" :class="{ invalid: errors.subcategory }"><option value="" disabled hidden>{{ form.category ? '请选择可提交的分类' : '请先选择一级分类' }}</option><option v-for="v in subcategoryOptions" :key="v.id" :value="v.label">{{ v.label }}</option></select><small v-if="errors.subcategory" class="error">{{ errors.subcategory }}</small></div>
        <fieldset v-if="!isOpportunity && !isInstantConsult" class="field radio-field priority-field"><legend class="required">优先级</legend><div class="priority-options"><label v-for="v in priorities" :key="v" :class="{ chosen: form.priority === v }"><input v-model="form.priority" type="radio" :value="v" />{{ v }}</label></div><small v-if="errors.priority" class="error">{{ errors.priority }}</small></fieldset>
        <div class="field full"><label for="description" class="required">{{ isInstantConsult ? '咨询内容' : '客户问题详情' }}</label><div class="textarea-wrap"><textarea id="description" v-model="form.description" maxlength="1000" rows="5" placeholder="请尽量记录客户原始描述" :class="{ invalid: errors.description }"></textarea><span>{{ form.description.length }}/1000</span></div><small v-if="errors.description" class="error">{{ errors.description }}</small></div>
        <div v-if="isInstantConsult" class="field full"><label for="instantAnswer" class="required">即时答复内容</label><div class="textarea-wrap"><textarea id="instantAnswer" v-model="form.instantAnswer" maxlength="4000" rows="5" placeholder="记录客服当场提供的答复" :class="{ invalid: errors.instantAnswer }"></textarea><span>{{ form.instantAnswer.length }}/4000</span></div><small v-if="errors.instantAnswer" class="error">{{ errors.instantAnswer }}</small></div>
      </div></TicketFormSection>
      <TicketFormSection v-if="!isOpportunity && form.category === '业务保障'" title="故障信息" icon="Tools" hint="（一级分类为“业务保障”时需填写）"><div class="grid fault-grid">
        <div class="field"><label for="faultTime" class="required">故障发生时间</label><input id="faultTime" v-model="form.faultTime" type="datetime-local" :class="{ invalid: errors.faultTime }" /><small v-if="errors.faultTime" class="error">{{ errors.faultTime }}</small></div>
        <div class="field"><label for="recurrence" class="required">故障复现规律</label><select id="recurrence" v-model="form.recurrence" :class="{ invalid: errors.recurrence }"><option v-for="v in recurrenceOptions" :key="v">{{ v }}</option></select><small v-if="errors.recurrence" class="error">{{ errors.recurrence }}</small></div>
        <div class="field"><label for="faultLocation" class="required">故障发生地理位置</label><input id="faultLocation" v-model.trim="form.faultLocation" placeholder="经纬度或文字地址" :class="{ invalid: errors.faultLocation }" /><small class="help">优先经纬度，也可填写文字地址</small><small v-if="errors.faultLocation" class="error">{{ errors.faultLocation }}</small></div>
        <fieldset class="field radio-field"><legend class="required">是否批量故障</legend><div class="radio-options"><label><input v-model="form.batchFault" type="radio" value="yes" /> 是</label><label><input v-model="form.batchFault" type="radio" value="no" /> 否</label></div><small v-if="errors.batchFault" class="error">{{ errors.batchFault }}</small></fieldset>
      </div></TicketFormSection>
      </div><aside class="form-sidebar" aria-label="系统记录"><section class="record-card"><h2><span class="record-icon"><Setting /></span>系统记录<span class="readonly-badge">只读</span></h2><dl><div v-for="item in systemInfo" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></div></dl></section></aside></div>
    </form>
    <Teleport to="body">
      <div class="form-actions" :style="{ left: uiStore.sidebarCollapsed ? '68px' : '240px' }">
        <div class="required-progress" role="status" :aria-label="`必填完成度 ${completedRequired}/${requiredFields.length}`">
          <span class="progress-ring" :style="{ '--progress': `${requiredPercent}%` }"><span>{{ requiredPercent }}%</span></span>
          <span class="progress-copy"><span>必填完成度</span><strong>{{ completedRequired }} / {{ requiredFields.length }}</strong></span>
        </div>
        <div class="action-buttons"><button type="button" class="cancel" :disabled="busy" @click="router.push('/tickets')">取消</button><button type="button" class="secondary" :disabled="busy" @click="saveDraft">{{ busy ? '保存中…' : '保存草稿' }}</button><button type="submit" form="ticket-create-form" class="primary" :disabled="busy">{{ busy ? '处理中…' : isInstantConsult ? '记录并办结' : '提交工单' }}</button></div>
      </div>
    </Teleport>
  </main>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { useUIStore } from '@/stores/ui'
import { metaApi } from '@/api/overviews'
import api from '@/api'
import TicketFormSection from '@/components/ticket-create/TicketFormSection.vue'
import { initialTicketForm, type CategoryName, type TicketCreateDesignForm } from '@/types/ticketCreateDesign'
import type { TicketCategory } from '@/types'
import { Setting } from '@element-plus/icons-vue'

const router = useRouter(), route = useRoute(), auth = useAuthStore(), uiStore = useUIStore()
const channels = ['语音', '在线客服', '内部转办']
const industries = ['海洋渔业', '工程机械', '智能网联', '交通物流', '能源行业', '应急通信', '智慧林草', '低空出行', '智慧水利', '智慧农业', 'Robotaxi', '未提供']
const recurrenceOptions = ['必现', '偶发', '仅特定时段']
const priorities = ['P1', 'P2', 'P3', 'P4']
const categoryNames: CategoryName[] = ['咨询', '投诉', '业务运营', '业务保障']
const rootNames: Record<CategoryName, string> = { 咨询: '客户咨询', 投诉: '服务投诉', 业务运营: '业务运营', 业务保障: '业务保障' }
const priorityCodes: Record<string, string> = { P1: 'p1_urgent', P2: 'p2_high', P3: 'p3_normal', P4: 'p4_enterprise' }
const channelCodes: Record<string, string> = { 语音: 'phone', 在线客服: 'web', 内部转办: 'internal' }
const form = reactive<TicketCreateDesignForm>(initialTicketForm())
const errors = reactive<Partial<Record<keyof TicketCreateDesignForm, string>>>({})
const categories = ref<TicketCategory[]>([])
const categoriesLoaded = ref(false)
const salesGroupId = ref<number | null>(null)
const salesUsers = ref<{ id: number; name: string }[]>([])
const draftId = ref<number | null>(null)
const busy = ref(false)
const now = ref(new Date().toLocaleString('sv-SE').replace('T', ' '))
let clockTimer: number | undefined
const systemInfo = computed(() => [
  { label: '工单号', value: '提交后自动生成' },
  { label: '受理工号', value: (auth.user as any)?.username || '—' },
  { label: '受理人', value: auth.displayName || '—' },
  { label: '受理班组', value: (auth.user as any)?.group?.name || auth.user?.groups?.[0]?.name || '—' },
  { label: '受理时间', value: now.value },
])
const rootCategory = computed(() => form.category ? categories.value.find(c => c.parent_id == null && c.name === rootNames[form.category as CategoryName]) : undefined)
const subcategoryOptions = computed(() => {
  const root = rootCategory.value
  if (!root || root.create_selectable) return []
  const byId = new Map(categories.value.map(c => [c.id, c]))
  return categories.value.filter(c => c.create_selectable).flatMap(c => {
    const names: string[] = []
    let node: TicketCategory | undefined = c
    while (node && node.id !== root.id) {
      names.unshift(node.name)
      node = node.parent_id == null ? undefined : byId.get(node.parent_id)
    }
    return node?.id === root.id ? [{ id: c.id, label: names.join(' / ') }] : []
  })
})
const selectedCategoryId = computed(() => rootCategory.value?.create_selectable
  ? rootCategory.value.id
  : subcategoryOptions.value.find(c => c.label === form.subcategory)?.id)
const numberRequired = computed(() => form.category === '业务运营' || form.category === '业务保障')
const isOpportunity = computed(() => form.businessOpportunity === 'yes')
const isInstantConsult = computed(() => !isOpportunity.value && selectedCategoryId.value === 1205)
const isReconciliation = computed(() => !isOpportunity.value && selectedCategoryId.value === 2204)
const requiredFields = computed<(keyof TicketCreateDesignForm)[]>(() => {
  if (isInstantConsult.value) return ['channel', 'callerPhone', 'category', 'subcategory', 'description', 'instantAnswer']
  const fields: (keyof TicketCreateDesignForm)[] = ['channel', 'customerName', 'companyName', 'industry', 'callerPhone', 'businessOpportunity', 'description']
  if (isOpportunity.value) return [...fields, 'contactPhone', 'salesUserId']
  if (isReconciliation.value) fields.push('salesUserId')
  fields.push('category', 'priority')
  if (!rootCategory.value?.create_selectable) fields.push('subcategory')
  if (numberRequired.value) fields.push('satelliteNumber')
  if (form.category === '业务保障') fields.push('faultTime', 'recurrence', 'faultLocation', 'batchFault')
  return fields
})
const completedRequired = computed(() => requiredFields.value.filter(key => {
  const raw = form[key]
  const value = typeof raw === 'string' ? raw.trim() : raw
  if (!value) return false
  if (key === 'subcategory') return subcategoryOptions.value.some(c => c.label === value)
  if (key === 'callerPhone') return /^(1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$/.test(String(value))
  if (key === 'faultTime') return !Number.isNaN(new Date(String(value)).getTime())
  return true
}).length)
const requiredPercent = computed(() => Math.round(completedRequired.value / requiredFields.value.length * 100))

onMounted(async () => {
  clockTimer = window.setInterval(() => { now.value = new Date().toLocaleString('sv-SE') }, 1000)
  try {
    categories.value = await metaApi.getCategories()
    categoriesLoaded.value = true
    if (form.subcategory && !subcategoryOptions.value.some(c => c.label === form.subcategory)) form.subcategory = ''
  } catch { ElMessage.error('分类加载失败，请刷新页面后重试') }
  try {
    const salesGroup = (await metaApi.getSkillGroups()).find(group => group.name === '销售')
    salesGroupId.value = salesGroup?.id ?? null
    salesUsers.value = salesGroup ? await metaApi.getHandlers(salesGroup.id) : []
  } catch { ElMessage.error('销售人员加载失败，请刷新页面后重试') }
  const id = Number(route.query.draft_id)
  if (Number.isInteger(id) && id > 0) {
    try {
      const ticket: any = await api.get(`/tickets/${id}`)
      if (!ticket.is_draft) throw new Error('非草稿')
      draftId.value = id
      form.channel = ({ phone: '语音', web: '在线客服', internal: '内部转办' } as Record<string,string>)[ticket.channel] || '语音'
      form.customerName = ticket.customer_name || ''
      form.companyName = ticket.customer_company || ''
      form.industry = ticket.industry || ''
      form.callerPhone = ticket.customer_phone || ''
      form.contactPhone = ticket.contact_phone || ''
      form.instantAnswer = ticket.resolution || ''
      form.satelliteNumber = ticket.satellite_number || ''
      const root = categories.value.find(c => c.id === ticket.category_l1_id)
      form.category = (Object.keys(rootNames) as CategoryName[]).find(k => rootNames[k] === root?.name) || ''
      form.subcategory = subcategoryOptions.value.find(c => c.id === ticket.category_id)?.label || ''
      form.businessOpportunity = ticket.is_opportunity == null ? '' : ticket.is_opportunity ? 'yes' : 'no'
      form.salesUserId = ticket.is_opportunity || ticket.category_id === 2204 ? ticket.owner_id ?? null : null
      form.priority = (Object.keys(priorityCodes).find(k => priorityCodes[k] === ticket.priority)) || 'P4'
      form.description = ticket.description || ''
      form.faultTime = ticket.fault_occurred_at ? new Date(ticket.fault_occurred_at).toLocaleString('sv-SE').replace(' ', 'T').slice(0, 16) : ''
      form.recurrence = ticket.fault_recurrence || ''
      form.faultLocation = ticket.fault_location || ''
      form.batchFault = ticket.is_batch_fault == null ? '' : ticket.is_batch_fault ? 'yes' : 'no'
    } catch { ElMessage.error('草稿加载失败') }
  }
})
onUnmounted(() => { if (clockTimer !== undefined) window.clearInterval(clockTimer) })
function onCategoryChange() {
  form.subcategory = ''
  for (const key of Object.keys(errors)) delete errors[key as keyof TicketCreateDesignForm]
}
function validate(): boolean {
  for (const key of Object.keys(errors)) delete errors[key as keyof TicketCreateDesignForm]
  for (const key of requiredFields.value) {
    const value = form[key]
    if (value === null || value === undefined || (typeof value === 'string' && !value.trim())) errors[key] = '请填写此项'
  }
  if ((isOpportunity.value || isReconciliation.value) && (!salesGroupId.value || !salesUsers.value.some(person => person.id === form.salesUserId))) errors.salesUserId = '请选择有效的销售人员'
  if (!isOpportunity.value && form.subcategory && !subcategoryOptions.value.some(c => c.label === form.subcategory)) errors.subcategory = '请选择当前分类下可提交的细分分类'
  const phone = /^(1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$/
  if (form.callerPhone && !phone.test(form.callerPhone)) errors.callerPhone = '请输入有效的手机号或固定电话'
  if (form.contactPhone && !phone.test(form.contactPhone)) errors.contactPhone = '请输入有效的手机号或固定电话'
  if (!isOpportunity.value && (!categoriesLoaded.value || !selectedCategoryId.value)) errors.subcategory ||= '分类尚未加载或当前分类不可提交'
  return !Object.keys(errors).length
}
function payload(isDraft: boolean) {
  return {
    intake_form: true, is_draft: isDraft,
    is_instant_resolve: isInstantConsult.value && !isDraft,
    instant_resolution: isInstantConsult.value ? form.instantAnswer.trim() || null : null,
    customer_type: 'enterprise', customer_name: form.customerName.trim() || null,
    customer_company: form.companyName.trim() || null, industry: form.industry || null,
    customer_phone: form.callerPhone.trim(),
    customer_phone_type: form.callerPhone.startsWith('1') ? 'mobile' : 'landline',
    contact_phone: form.contactPhone.trim() || null, customer_email: null,
    channel: channelCodes[form.channel] || 'phone', priority: isOpportunity.value || isInstantConsult.value ? 'p4_enterprise' : priorityCodes[form.priority] || 'p4_enterprise',
    category_id: isOpportunity.value ? null : selectedCategoryId.value || null, description: form.description.trim(),
    skill_group_id: isOpportunity.value || isReconciliation.value ? salesGroupId.value : null,
    sales_owner_id: isOpportunity.value || isReconciliation.value ? form.salesUserId : null,
    dispatcher_id: null,
    complaint_level: !isOpportunity.value && form.category === '投诉' ? ({ 一般投诉: '一般', 重要投诉: '重要', 重大投诉: '重大' } as Record<string, string>)[form.subcategory] || null : null,
    satellite_number: isOpportunity.value || isInstantConsult.value ? null : form.satelliteNumber.trim() || null,
    is_opportunity: isInstantConsult.value ? false : form.businessOpportunity ? form.businessOpportunity === 'yes' : null,
    expected_result: null,
    fault_occurred_at: !isOpportunity.value && form.category === '业务保障' && form.faultTime ? new Date(form.faultTime).toISOString() : null,
    fault_recurrence: !isOpportunity.value && form.category === '业务保障' ? form.recurrence || null : null,
    fault_location: !isOpportunity.value && form.category === '业务保障' ? form.faultLocation.trim() || null : null,
    is_batch_fault: !isOpportunity.value && form.category === '业务保障' && form.batchFault ? form.batchFault === 'yes' : null,
  }
}
async function saveDraft() {
  if (busy.value) return
  busy.value = true
  try {
    const res: any = draftId.value
      ? await api.patch(`/tickets/drafts/${draftId.value}`, payload(true))
      : await api.post('/tickets', payload(true))
    draftId.value = res.data.id
    await router.replace({ path: '/tickets/new', query: { draft_id: draftId.value } })
    ElMessage.success('草稿已保存')
  } catch { /* API 拦截器显示错误 */ }
  finally { busy.value = false }
}
async function submitTicket() {
  if (busy.value) return
  if (!validate()) { ElMessage.warning('请检查标记的字段'); return }
  busy.value = true
  try {
    const res: any = await api.post('/tickets', payload(false))
    if (draftId.value) {
      try { await api.delete(`/tickets/drafts/${draftId.value}`, { silent: true }) }
      catch { ElMessage.warning('工单已创建，但旧草稿未能删除，请稍后手动清理') }
    }
    ElMessage.success(isInstantConsult.value ? '咨询记录已办结' : '工单提交成功')
    await router.push(`/tickets/${res.data.id}`)
  } catch { /* API 拦截器显示错误 */ }
  finally { busy.value = false }
}
</script>
<style scoped>
.page{padding:12px 18px 80px;color:var(--color-text-primary);font-family:var(--font-sans)}.crumb{display:flex;align-items:center;gap:12px;color:var(--color-text-tertiary);font-size:13px}.crumb strong{color:var(--color-text-secondary);font-weight:500}h1{margin:12px 0 1px;font-size:24px;line-height:1.3;color:var(--color-text-primary)}.subtitle{margin:0 0 14px;color:var(--color-text-tertiary);font-size:13px}.grid{display:grid;gap:12px 22px}.system-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.one-grid{grid-template-columns:420px}.customer-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.content-grid,.fault-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.field{min-width:0;display:flex;flex-direction:column;gap:4px}.field.full{grid-column:1/-1}.field>label,.radio-field legend{font-size:13px;font-weight:600}.required:after{content:' *';color:var(--color-danger)}.field input:not([type=radio]),.field select,.field textarea{box-sizing:border-box;width:100%;height:34px;padding:6px 12px;border:1px solid var(--color-border);border-radius:4px;background:#fff;color:var(--color-text-primary);font:inherit;font-size:13px;outline:none}.field input.readonly{border-color:transparent;background:var(--color-bg-subtle);color:var(--color-text-secondary)}.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--color-primary);box-shadow:0 0 0 2px var(--color-primary-ring)}.field .invalid{border-color:var(--color-danger)!important}.field input::placeholder,.field textarea::placeholder{color:var(--color-text-tertiary)}.field select:disabled{background:var(--color-bg-hover)}.help{color:var(--color-text-tertiary);font-size:11px}.error{color:var(--color-danger);font-size:11px}.radio-field{margin:0;padding:0;border:0}.radio-field legend{margin-bottom:10px;padding:0}.radio-options{display:flex;gap:28px;height:34px;align-items:center}.radio-options label{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}.radio-field input{accent-color:var(--color-primary)}.priority-field{grid-column:2/5}.priority-options{display:flex;gap:14px}.priority-options label{min-width:78px;height:33px;display:flex;align-items:center;gap:10px;padding:0 12px;border:1px solid var(--color-border);border-radius:4px;font-size:13px;cursor:pointer}.priority-options label.chosen{border-color:var(--color-primary);background:var(--color-primary-ghost)}.priority-options label.chosen input{accent-color:var(--color-primary)}.textarea-wrap{position:relative}.field .textarea-wrap textarea{height:112px;resize:vertical;padding-bottom:22px}.textarea-wrap span{position:absolute;right:12px;bottom:9px;color:var(--color-text-tertiary);font-size:11px}.form-actions{position:sticky;bottom:0;z-index:2;display:flex;justify-content:flex-end;gap:9px;margin:0 -18px -80px;padding:10px 18px;background:#fff;border-top:1px solid var(--color-border-light)}.form-actions button{min-width:94px;height:37px;border-radius:var(--radius-md);border:1px solid var(--color-border);background:#fff;color:var(--color-text-primary);cursor:pointer}.form-actions .secondary{border-color:var(--color-primary);color:var(--color-primary)}.form-actions .primary{border-color:var(--color-primary);background:var(--color-primary);color:#fff;font-weight:700}.form-actions button:hover{border-color:var(--color-primary);color:var(--color-primary)}.form-actions .primary:hover{background:var(--color-primary-hover);border-color:var(--color-primary-hover);color:#fff}@media(max-width:1100px){.system-grid,.content-grid,.fault-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.priority-field{grid-column:auto}.one-grid{grid-template-columns:minmax(0,420px)}}@media(max-width:700px){.page{padding:16px 12px 75px}.system-grid,.customer-grid,.content-grid,.fault-grid,.one-grid{grid-template-columns:1fr}.priority-field{grid-column:auto}.priority-options{flex-wrap:wrap}.form-actions{margin:0 -12px -75px;padding:10px 12px}.form-actions button{min-width:0;flex:1}}
</style>
<style scoped>
/* 按主内容区宽度换列，侧边栏展开或收起时也能自适应。 */
.page { container-type: inline-size; width: 100%; min-width: 0; box-sizing: border-box; }
.page h1 { margin-bottom: 18px; }
.system-grid { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.one-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.priority-options { flex-wrap: wrap; }
.priority-options label { box-sizing: border-box; }
.form-actions {
  bottom: 12px;
  margin: 12px 0 0;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
}
@container (max-width: 1120px) {
  .system-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .content-grid, .fault-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .priority-field { grid-column: 2 / 4; }
}
@container (max-width: 780px) {
  .system-grid, .customer-grid, .content-grid, .fault-grid, .one-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .priority-field { grid-column: 1 / -1; }
}
@container (max-width: 520px) {
  .system-grid, .customer-grid, .content-grid, .fault-grid, .one-grid { grid-template-columns: minmax(0, 1fr); }
  .priority-field { grid-column: 1 / -1; }
}
</style>
<style scoped>
.page{padding-bottom:104px}
.form-actions{position:fixed;right:0;bottom:0;z-index:20;box-sizing:border-box;display:flex;align-items:center;justify-content:space-between;gap:20px;margin:0;padding:12px clamp(18px,2.4vw,36px);border:0;border-top:1px solid var(--color-border-light);border-radius:0;background:#fff;box-shadow:0 -5px 22px rgba(27,41,64,.055)}
.required-progress{display:flex;align-items:center;gap:11px;min-width:0}.progress-ring{--progress:0%;position:relative;display:grid;place-items:center;flex:none;width:38px;height:38px;border-radius:50%;background:conic-gradient(var(--color-primary) var(--progress),#e6ebef 0)}.progress-ring:before{content:'';position:absolute;inset:4px;border-radius:50%;background:#fff}.progress-ring span{position:relative;z-index:1;font-size:9px;font-weight:700;color:var(--color-text-secondary)}.progress-copy{display:flex;flex-direction:column;gap:2px;color:var(--color-text-tertiary);font-size:11px;white-space:nowrap}.progress-copy strong{color:var(--color-text-primary);font-size:13px}.action-buttons{display:flex;align-items:center;gap:9px}.form-actions button{flex:none;min-width:94px;height:38px;border-radius:var(--radius-md)}
@media(max-width:700px){.page{padding-bottom:124px}.form-actions{left:0!important;gap:8px;padding:10px 12px}.required-progress{gap:6px}.progress-ring{width:34px;height:34px}.progress-copy{font-size:10px}.progress-copy strong{font-size:11px}.action-buttons{gap:5px}.form-actions button{min-width:0;padding:0 8px;font-size:12px}}
</style>
<style scoped>
/* 表单控件统一尺寸与内边距；原生 select 箭头由同一图形绘制，避免贴边。 */
.grid{column-gap:20px;row-gap:17px}
.field{gap:7px}
.field>label,.radio-field legend{color:var(--color-text-secondary);font-size:12.5px;font-weight:650;line-height:1.35}
.field input:not([type=radio]),.field select,.field textarea{height:40px;padding:9px 13px;border:1px solid #dce2e9;border-radius:var(--radius-sm);background-color:#fff;font-size:13px;line-height:1.4;transition:border-color .16s,box-shadow .16s,background-color .16s}
.field select{appearance:none;-webkit-appearance:none;padding-right:40px;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%23778394' stroke-width='1.8' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E");background-repeat:no-repeat;background-size:16px 16px;background-position:right 14px center;cursor:pointer}
.field select:disabled{cursor:not-allowed;color:var(--color-text-tertiary);background-color:var(--color-bg-subtle);opacity:1}
.field input:not([type=radio]):not(.readonly):hover,.field select:not(:disabled):hover,.field textarea:hover{border-color:#b7c2ce}
.field input.readonly{border-color:#edf0f2;background:var(--color-bg-subtle);color:var(--color-text-secondary);cursor:default}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--color-primary);box-shadow:0 0 0 3px var(--color-primary-ghost)}
.field .invalid,.field .invalid:focus{border-color:var(--color-danger)!important;box-shadow:0 0 0 3px var(--color-danger-light)}
.help{line-height:1.45}.error{line-height:1.45}
.radio-field legend{margin-bottom:9px}
.radio-options{height:40px;gap:8px}
.radio-options label{box-sizing:border-box;display:inline-flex;align-items:center;justify-content:center;gap:8px;min-width:66px;height:40px;padding:0 13px;border:1px solid #dce2e9;border-radius:var(--radius-sm);background:#fff;transition:border-color .16s,background-color .16s}
.radio-options label:hover,.priority-options label:hover{border-color:#aebacf}
.radio-options label:has(input:checked){border-color:var(--color-primary);background:var(--color-primary-ghost);color:var(--color-primary)}
.radio-options input,.priority-options input{width:15px;height:15px;margin:0;accent-color:var(--color-primary)}
.priority-options{gap:9px}
.priority-options label{min-width:67px;height:40px;padding:0 12px;border-color:#dce2e9;border-radius:var(--radius-sm);transition:border-color .16s,background-color .16s}
.field .textarea-wrap textarea{height:148px;min-height:120px;padding:12px 14px 29px;line-height:1.65}
.textarea-wrap span{right:15px;bottom:12px}
.form-actions button{padding:0 18px;border-radius:var(--radius-sm);transition:border-color .16s,background-color .16s,box-shadow .16s}
.form-actions button:focus-visible,.radio-options label:focus-within,.priority-options label:focus-within{outline:2px solid var(--color-primary);outline-offset:2px}
.form-actions button:disabled{opacity:.55;cursor:not-allowed}
@media(max-width:700px){.form-actions button{padding:0 8px}}
</style>
<style scoped>
.create-layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;align-items:start;gap:20px}
.priority-field{grid-column:1/-1}
.priority-options{display:flex;justify-content:flex-start;flex-wrap:wrap}
.priority-options label{width:auto;min-width:67px;justify-content:flex-start}
.form-main{min-width:0}.form-sidebar{min-width:0;position:sticky;top:18px}
.intake-grid{grid-template-columns:minmax(0,320px)}
.record-card{overflow:hidden;border:1px solid var(--color-border);border-radius:var(--radius-lg);background:var(--color-bg-card);box-shadow:var(--shadow-xs)}
.record-card h2{display:flex;align-items:center;gap:9px;margin:0;padding:16px 18px;border-bottom:1px solid var(--color-border-light);font-size:14px;font-weight:700;color:var(--color-text-primary)}
.record-icon{display:grid;place-items:center;width:25px;height:25px;border-radius:6px;background:var(--color-primary-light);color:var(--color-primary)}
.record-icon :deep(svg){width:15px;height:15px}.readonly-badge{margin-left:auto;padding:3px 8px;border:1px solid var(--color-border);border-radius:999px;color:var(--color-text-tertiary);font-size:11px;font-weight:500}
.record-card dl{margin:0;padding:4px 18px 12px}.record-card dl>div{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px dashed var(--color-border-light)}.record-card dl>div:last-child{border-bottom:0}.record-card dt{flex:none;color:var(--color-text-tertiary);font-size:12px}.record-card dd{margin:0;min-width:0;color:var(--color-text-primary);font-size:12px;font-weight:600;text-align:right;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}
@container (max-width:980px){.create-layout{grid-template-columns:minmax(0,1fr)}.form-sidebar{position:static;grid-row:1}.record-card dl{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 22px}.record-card dl>div:nth-last-child(-n+2){border-bottom:0}}
@container (max-width:580px){.record-card dl{grid-template-columns:1fr}.record-card dl>div:nth-last-child(2){border-bottom:1px dashed var(--color-border-light)}.intake-grid{grid-template-columns:1fr}}
</style>
