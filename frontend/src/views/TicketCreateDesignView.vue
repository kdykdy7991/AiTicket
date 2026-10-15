<template>
  <main class="page">
    <nav class="crumb"><router-link to="/tickets">工单管理</router-link><span>›</span><strong>创建工单</strong></nav>
    <h1>创建工单</h1>
    <form novalidate @submit.prevent="submitTicket">
      <TicketFormSection title="工单信息" icon="Setting" hint="（工单号提交后生成）"><div class="grid system-grid"><div v-for="item in systemInfo" :key="item.label" class="field"><label>{{ item.label }}</label><input :value="item.value" readonly class="readonly" /></div><div class="field"><label for="channel" class="required">受理渠道</label><select id="channel" v-model="form.channel" :class="{ invalid: errors.channel }"><option v-for="v in channels" :key="v">{{ v }}</option></select><small v-if="errors.channel" class="error">{{ errors.channel }}</small></div></div></TicketFormSection>
      <TicketFormSection title="客户信息" icon="User"><div class="grid customer-grid">
        <div class="field"><label for="customerName" class="required">客户名称</label><input id="customerName" v-model.trim="form.customerName" placeholder="请输入客户名称" :class="{ invalid: errors.customerName }" /><small v-if="errors.customerName" class="error">{{ errors.customerName }}</small></div>
        <div class="field"><label for="companyName" class="required">单位全称</label><input id="companyName" v-model.trim="form.companyName" placeholder="请输入单位全称" :class="{ invalid: errors.companyName }" /><small v-if="errors.companyName" class="error">{{ errors.companyName }}</small></div>
        <div class="field"><label for="industry" class="required">行业</label><select id="industry" v-model="form.industry" :class="{ invalid: errors.industry }"><option value="" disabled hidden>请选择行业</option><option v-for="v in industries" :key="v">{{ v }}</option></select><small v-if="errors.industry" class="error">{{ errors.industry }}</small></div>
        <div class="field"><label for="callerPhone" class="required">来电号码</label><input id="callerPhone" v-model.trim="form.callerPhone" inputmode="tel" placeholder="请输入来电号码" :class="{ invalid: errors.callerPhone }" /><small v-if="errors.callerPhone" class="error">{{ errors.callerPhone }}</small></div>
        <div class="field"><label for="contactPhone">联系号码</label><input id="contactPhone" v-model.trim="form.contactPhone" inputmode="tel" placeholder="请输入联系号码" :class="{ invalid: errors.contactPhone }" /><small class="help">联系方式与来电号码不同时补充</small><small v-if="errors.contactPhone" class="error">{{ errors.contactPhone }}</small></div>
        <div class="field"><label for="email">邮箱</label><input id="email" v-model.trim="form.email" type="email" placeholder="请输入邮箱" :class="{ invalid: errors.email }" /><small v-if="errors.email" class="error">{{ errors.email }}</small></div>
      </div></TicketFormSection>
      <TicketFormSection title="工单内容" icon="Document"><div class="grid content-grid">
        <div class="field"><label for="satelliteNumber" :class="{ required: numberRequired }">卫星物联网码号</label><input id="satelliteNumber" v-model.trim="form.satelliteNumber" placeholder="请输入卫星物联网码号" :class="{ invalid: errors.satelliteNumber }" /><small class="help">一级分类为业务运营/业务保障时必填</small><small v-if="errors.satelliteNumber" class="error">{{ errors.satelliteNumber }}</small></div>
        <div class="field"><label for="category" class="required">一级分类</label><select id="category" v-model="form.category" :class="{ invalid: errors.category }" @change="onCategoryChange"><option value="" disabled hidden>请选择一级分类</option><option v-for="v in categoryNames" :key="v">{{ v }}</option></select><small v-if="errors.category" class="error">{{ errors.category }}</small></div>
        <div class="field"><label for="subcategory" class="required">二级分类</label><select id="subcategory" v-model="form.subcategory" :disabled="!form.category" :class="{ invalid: errors.subcategory }"><option value="" disabled hidden>{{ form.category ? '请选择二级分类' : '请先选择一级分类' }}</option><option v-for="v in subcategoryOptions" :key="v">{{ v }}</option></select><small v-if="errors.subcategory" class="error">{{ errors.subcategory }}</small></div>
        <fieldset class="field radio-field"><legend class="required">是否为商机工单</legend><div class="radio-options"><label><input v-model="form.businessOpportunity" type="radio" value="yes" /> 是</label><label><input v-model="form.businessOpportunity" type="radio" value="no" /> 否</label></div><small v-if="errors.businessOpportunity" class="error">{{ errors.businessOpportunity }}</small></fieldset>
        <div class="field"><label for="expectedResult" class="required">客户期望结果</label><select id="expectedResult" v-model="form.expectedResult" :class="{ invalid: errors.expectedResult }"><option v-for="v in expectedResults" :key="v">{{ v }}</option></select><small v-if="errors.expectedResult" class="error">{{ errors.expectedResult }}</small></div>
        <fieldset class="field radio-field priority-field"><legend class="required">优先级</legend><div class="priority-options"><label v-for="v in priorities" :key="v" :class="{ chosen: form.priority === v }"><input v-model="form.priority" type="radio" :value="v" />{{ v }}</label></div><small v-if="errors.priority" class="error">{{ errors.priority }}</small></fieldset>
        <div class="field full"><label for="description" class="required">客户问题详情</label><div class="textarea-wrap"><textarea id="description" v-model="form.description" maxlength="1000" rows="5" placeholder="请尽量记录客户原始描述" :class="{ invalid: errors.description }"></textarea><span>{{ form.description.length }}/1000</span></div><small v-if="errors.description" class="error">{{ errors.description }}</small></div>
      </div></TicketFormSection>
      <TicketFormSection v-if="form.category === '业务保障'" title="故障信息" icon="Tools" hint="（一级分类为“业务保障”时需填写）"><div class="grid fault-grid">
        <div class="field"><label for="faultTime" class="required">故障发生时间</label><input id="faultTime" v-model="form.faultTime" type="datetime-local" :class="{ invalid: errors.faultTime }" /><small v-if="errors.faultTime" class="error">{{ errors.faultTime }}</small></div>
        <div class="field"><label for="recurrence" class="required">故障复现规律</label><select id="recurrence" v-model="form.recurrence" :class="{ invalid: errors.recurrence }"><option v-for="v in recurrenceOptions" :key="v">{{ v }}</option></select><small v-if="errors.recurrence" class="error">{{ errors.recurrence }}</small></div>
        <div class="field"><label for="faultLocation" class="required">故障发生地理位置</label><input id="faultLocation" v-model.trim="form.faultLocation" placeholder="经纬度或文字地址" :class="{ invalid: errors.faultLocation }" /><small class="help">优先经纬度，也可填写文字地址</small><small v-if="errors.faultLocation" class="error">{{ errors.faultLocation }}</small></div>
        <fieldset class="field radio-field"><legend class="required">是否批量故障</legend><div class="radio-options"><label><input v-model="form.batchFault" type="radio" value="yes" /> 是</label><label><input v-model="form.batchFault" type="radio" value="no" /> 否</label></div><small v-if="errors.batchFault" class="error">{{ errors.batchFault }}</small></fieldset>
      </div></TicketFormSection>
      <div class="form-actions"><button type="button" class="cancel" :disabled="busy" @click="router.push('/tickets')">取消</button><button type="button" class="secondary" :disabled="busy" @click="saveDraft">{{ busy ? '保存中…' : '保存草稿' }}</button><button type="submit" class="primary" :disabled="busy">{{ busy ? '处理中…' : '提交工单' }}</button></div>
    </form>
  </main>
</template>
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { metaApi } from '@/api/overviews'
import api from '@/api'
import TicketFormSection from '@/components/ticket-create/TicketFormSection.vue'
import { initialTicketForm, type CategoryName, type TicketCreateDesignForm } from '@/types/ticketCreateDesign'
import type { TicketCategory } from '@/types'

const router = useRouter(), route = useRoute(), auth = useAuthStore()
const channels = ['语音', '在线客服', '内部转办']
const industries = ['物联网', '海洋渔业', '水利', '能源', '未提供']
const expectedResults = ['解释说明', '远程排查', '上门检修', '换终端', '退费', '销户', '体验优化']
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
const draftId = ref<number | null>(null)
const busy = ref(false)
const now = ref(new Date().toLocaleString('sv-SE').replace('T', ' '))
let clockTimer: number | undefined
const systemInfo = computed(() => [
  { label: '工单号', value: '提交后自动生成' },
  { label: '受理工号', value: (auth.user as any)?.username || '当前账号' },
  { label: '受理人', value: auth.displayName || '当前用户' },
  { label: '受理班组', value: (auth.user as any)?.group?.name || auth.user?.groups?.[0]?.name || '当前所属班组' },
  { label: '受理时间', value: now.value },
])
const rootCategory = computed(() => form.category ? categories.value.find(c => c.parent_id == null && c.name === rootNames[form.category as CategoryName]) : undefined)
const subcategoryRows = computed(() => categories.value.filter(c => c.parent_id === rootCategory.value?.id))
const subcategoryOptions = computed(() => subcategoryRows.value.map(c => c.name))
const selectedCategoryId = computed(() => subcategoryRows.value.find(c => c.name === form.subcategory)?.id)
const numberRequired = computed(() => form.category === '业务运营' || form.category === '业务保障')

onMounted(async () => {
  clockTimer = window.setInterval(() => { now.value = new Date().toLocaleString('sv-SE') }, 1000)
  try {
    categories.value = await metaApi.getCategories()
    categoriesLoaded.value = true
    if (form.subcategory && !subcategoryOptions.value.includes(form.subcategory)) form.subcategory = ''
  } catch { ElMessage.error('分类加载失败，请刷新页面后重试') }
  const id = Number(route.query.draft_id)
  if (Number.isInteger(id) && id > 0) {
    try {
      const ticket: any = await api.get(`/tickets/${id}`)
      if (!ticket.is_draft) throw new Error('非草稿')
      draftId.value = id
      form.channel = ({ phone: '语音', web: '在线客服', internal: '内部转办' } as Record<string,string>)[ticket.channel] || '在线客服'
      form.customerName = ticket.customer_name || ''
      form.companyName = ticket.customer_company || ''
      form.industry = ticket.industry || ''
      form.callerPhone = ticket.customer_phone || ''
      form.contactPhone = ticket.contact_phone || ''
      form.email = ticket.customer_email || ''
      form.satelliteNumber = ticket.satellite_number || ''
      const root = categories.value.find(c => c.id === ticket.category_l1_id)
      form.category = (Object.keys(rootNames) as CategoryName[]).find(k => rootNames[k] === root?.name) || ''
      form.subcategory = categories.value.find(c => c.id === ticket.category_id)?.name || ''
      form.businessOpportunity = ticket.is_opportunity == null ? '' : ticket.is_opportunity ? 'yes' : 'no'
      form.expectedResult = ticket.expected_result || ''
      form.priority = (Object.keys(priorityCodes).find(k => priorityCodes[k] === ticket.priority)) || 'P2'
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
  const required: (keyof TicketCreateDesignForm)[] = ['channel', 'customerName', 'companyName', 'industry', 'callerPhone', 'category', 'subcategory', 'businessOpportunity', 'expectedResult', 'priority', 'description']
  if (numberRequired.value) required.push('satelliteNumber')
  if (form.category === '业务保障') required.push('faultTime', 'recurrence', 'faultLocation', 'batchFault')
  for (const key of required) if (!form[key]?.trim()) errors[key] = '请填写此项'
  if (form.subcategory && !subcategoryOptions.value.includes(form.subcategory)) errors.subcategory = '请选择当前分类对应的二级分类'
  const phone = /^(1[3-9]\d{9}|0\d{2,3}-?\d{7,8})$/
  if (form.callerPhone && !phone.test(form.callerPhone)) errors.callerPhone = '请输入有效的手机号或固定电话'
  if (form.contactPhone && !phone.test(form.contactPhone)) errors.contactPhone = '请输入有效的手机号或固定电话'
  if (form.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(form.email)) errors.email = '请输入有效的邮箱地址'
  if (!categoriesLoaded.value || !selectedCategoryId.value) errors.subcategory ||= '分类尚未加载或未选择'
  return !Object.keys(errors).length
}
function payload(isDraft: boolean) {
  return {
    intake_form: true, is_draft: isDraft,
    customer_type: 'enterprise', customer_name: form.customerName.trim() || null,
    customer_company: form.companyName.trim() || null, industry: form.industry || null,
    customer_phone: form.callerPhone.trim(),
    customer_phone_type: form.callerPhone.startsWith('1') ? 'mobile' : 'landline',
    contact_phone: form.contactPhone.trim() || null, customer_email: form.email.trim() || null,
    channel: channelCodes[form.channel] || 'web', priority: priorityCodes[form.priority] || 'p2_high',
    category_id: selectedCategoryId.value || null, description: form.description.trim(),
    complaint_level: form.category === '投诉' ? ({ 一般投诉: '一般', 重要投诉: '重要', 重大投诉: '重大' } as Record<string, string>)[form.subcategory] || null : null,
    satellite_number: form.satelliteNumber.trim() || null,
    is_opportunity: form.businessOpportunity ? form.businessOpportunity === 'yes' : null,
    expected_result: form.expectedResult || null,
    fault_occurred_at: form.category === '业务保障' && form.faultTime ? new Date(form.faultTime).toISOString() : null,
    fault_recurrence: form.category === '业务保障' ? form.recurrence || null : null,
    fault_location: form.category === '业务保障' ? form.faultLocation.trim() || null : null,
    is_batch_fault: form.category === '业务保障' && form.batchFault ? form.batchFault === 'yes' : null,
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
    ElMessage.success('工单提交成功')
    await router.push(`/tickets/${res.data.id}`)
  } catch { /* API 拦截器显示错误 */ }
  finally { busy.value = false }
}
</script>
<style scoped>
.page{padding:12px 18px 80px;color:var(--color-text-primary);font-family:var(--font-sans)}.crumb{display:flex;align-items:center;gap:12px;color:var(--color-text-tertiary);font-size:13px}.crumb strong{color:var(--color-text-secondary);font-weight:500}h1{margin:12px 0 1px;font-size:24px;line-height:1.3;color:var(--color-text-primary)}.subtitle{margin:0 0 14px;color:var(--color-text-tertiary);font-size:13px}.grid{display:grid;gap:12px 22px}.system-grid{grid-template-columns:repeat(5,minmax(0,1fr))}.one-grid{grid-template-columns:420px}.customer-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.content-grid,.fault-grid{grid-template-columns:repeat(4,minmax(0,1fr))}.field{min-width:0;display:flex;flex-direction:column;gap:4px}.field.full{grid-column:1/-1}.field>label,.radio-field legend{font-size:13px;font-weight:600}.required:after{content:' *';color:var(--color-danger)}.field input:not([type=radio]),.field select,.field textarea{box-sizing:border-box;width:100%;height:34px;padding:6px 12px;border:1px solid var(--color-border);border-radius:4px;background:#fff;color:var(--color-text-primary);font:inherit;font-size:13px;outline:none}.field input.readonly{border-color:transparent;background:var(--color-bg-subtle);color:var(--color-text-secondary)}.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--color-primary);box-shadow:0 0 0 2px var(--color-primary-ring)}.field .invalid{border-color:var(--color-danger)!important}.field input::placeholder,.field textarea::placeholder{color:var(--color-text-tertiary)}.field select:disabled{background:var(--color-bg-hover)}.help{color:var(--color-text-tertiary);font-size:11px}.error{color:var(--color-danger);font-size:11px}.radio-field{margin:0;padding:0;border:0}.radio-field legend{margin-bottom:10px;padding:0}.radio-options{display:flex;gap:28px;height:34px;align-items:center}.radio-options label{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}.radio-field input{accent-color:var(--color-primary)}.priority-field{grid-column:2/5}.priority-options{display:flex;gap:14px}.priority-options label{min-width:78px;height:33px;display:flex;align-items:center;gap:10px;padding:0 12px;border:1px solid var(--color-border);border-radius:4px;font-size:13px;cursor:pointer}.priority-options label.chosen{border-color:var(--color-primary);background:var(--color-primary-ghost)}.priority-options label.chosen input{accent-color:var(--color-primary)}.textarea-wrap{position:relative}.field .textarea-wrap textarea{height:112px;resize:vertical;padding-bottom:22px}.textarea-wrap span{position:absolute;right:12px;bottom:9px;color:var(--color-text-tertiary);font-size:11px}.form-actions{position:sticky;bottom:0;z-index:2;display:flex;justify-content:flex-end;gap:9px;margin:0 -18px -80px;padding:10px 18px;background:#fff;border-top:1px solid var(--color-border-light)}.form-actions button{min-width:94px;height:37px;border-radius:var(--radius-md);border:1px solid var(--color-border);background:#fff;color:var(--color-text-primary);cursor:pointer}.form-actions .secondary{border-color:var(--color-primary);color:var(--color-primary)}.form-actions .primary{border-color:var(--color-primary);background:var(--color-primary);color:#fff;font-weight:700}.form-actions button:hover{border-color:var(--color-primary);color:var(--color-primary)}.form-actions .primary:hover{background:var(--color-primary-hover);border-color:var(--color-primary-hover);color:#fff}@media(max-width:1100px){.system-grid,.content-grid,.fault-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.priority-field{grid-column:auto}.one-grid{grid-template-columns:minmax(0,420px)}}@media(max-width:700px){.page{padding:16px 12px 75px}.system-grid,.customer-grid,.content-grid,.fault-grid,.one-grid{grid-template-columns:1fr}.priority-field{grid-column:auto}.priority-options{flex-wrap:wrap}.form-actions{margin:0 -12px -75px;padding:10px 12px}.form-actions button{min-width:0;flex:1}}
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
