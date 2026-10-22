<template>
  <div class="ticket-information">
    <TicketFormSection title="工单信息" icon="Document" eyebrow="TICKET INFORMATION">
      <div class="fields system-fields">
        <div v-for="field in systemFields" :key="field.label" class="field"><span class="field-icon"><component :is="field.icon" /></span><div class="field-copy"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div></div>
      </div>
    </TicketFormSection>

    <TicketFormSection title="客户信息" icon="User" eyebrow="CUSTOMER INFORMATION">
      <div class="fields customer-fields">
        <div v-for="field in customerFields" :key="field.label" class="field"><span class="field-icon"><component :is="field.icon" /></span><div class="field-copy"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div></div>
      </div>
    </TicketFormSection>

    <TicketFormSection title="工单内容" icon="Document" eyebrow="TICKET CONTENT">
      <div class="fields content-fields">
        <div v-for="field in contentFields" :key="field.label" class="field" :class="{ full: field.full, 'description-field': field.description }"><span class="field-icon"><component :is="field.icon" /></span><div class="field-copy"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div></div>
      </div>
    </TicketFormSection>

    <TicketFormSection v-if="hasFaultInfo" title="故障信息" icon="Tools" eyebrow="FAULT INFORMATION">
      <div class="fields fault-fields">
        <div v-for="field in faultFields" :key="field.label" class="field"><span class="field-icon"><component :is="field.icon" /></span><div class="field-copy"><span>{{ field.label }}</span><strong>{{ field.value }}</strong></div></div>
      </div>
    </TicketFormSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import { Document, User as UserIcon, OfficeBuilding, Phone, Clock, Grid, Flag, Location, Warning, ChatDotRound, Collection, Connection, Tickets } from '@element-plus/icons-vue'
import type { TicketDetail, User } from '@/types'
import TicketFormSection from '@/components/ticket-create/TicketFormSection.vue'
const props = defineProps<{ ticket: TicketDetail }>()
const t = computed<Record<string, any>>(() => props.ticket)
const userName = (user?: User | null) => user ? `${user.firstname || ''}${user.lastname || ''}`.trim() : ''
const customerName = computed(() => t.value.customer_name || userName(t.value.customer) || '—')
const regionText = computed(() => t.value.region_name || [t.value.region?.province, t.value.region?.city, t.value.region?.district, t.value.region?.station].filter(Boolean).join(' / '))
const channelText = computed(() => ({ phone: '语音', web: '在线客服', internal: '内部转办', email: '邮件' } as Record<string, string>)[t.value.channel] || t.value.channel || '—')
const priorityText = computed(() => ({ p1_urgent: 'P1', p2_high: 'P2', p3_normal: 'P3', p4_enterprise: 'P4' } as Record<string, string>)[t.value.priority?.key || t.value.priority] || t.value.priority?.name || '—')
const hasFaultInfo = computed(() => !!(t.value.fault_occurred_at || t.value.fault_recurrence || t.value.fault_location || t.value.is_batch_fault != null))
const systemFields = computed(() => [
  { label: '工单号', value: t.value.number || '—', icon: Tickets },
  { label: '受理工号', value: t.value.creator_username || t.value.creator_account || '—', icon: Connection },
  { label: '受理人', value: t.value.creator_name || '—', icon: UserIcon },
  { label: '受理班组', value: t.value.creator_group_name || t.value.creator_group || '—', icon: OfficeBuilding },
  { label: '受理时间', value: formatTime(t.value.created_at), icon: Clock },
  { label: '受理渠道', value: channelText.value, icon: ChatDotRound },
])
const customerFields = computed(() => [
  { label: '客户名称', value: customerName.value, icon: OfficeBuilding },
  { label: '单位全称', value: t.value.customer_company || t.value.organization?.name || '—', icon: OfficeBuilding },
  { label: '联系人', value: t.value.contact_name || '—', icon: UserIcon },
  { label: '行业', value: t.value.industry || '—', icon: Collection },
  { label: '来电号码', value: t.value.customer_phone || '—', icon: Phone },
  { label: '联系号码', value: t.value.contact_phone || '—', icon: Phone },
  ...(regionText.value || t.value.device_sn ? [
    { label: '区域', value: regionText.value || '—', icon: Location },
    { label: '设备 SN', value: t.value.device_sn || '—', icon: Connection },
  ] : []),
])
const contentFields = computed(() => [
  { label: '卫星物联网码号', value: t.value.satellite_number || '—', icon: Connection },
  { label: '一级分类', value: t.value.category_l1?.name || '—', icon: Grid },
  { label: '二级分类', value: t.value.category_l2?.name || '—', icon: Grid },
  { label: '是否为线索工单', value: yesNo(t.value.is_opportunity), icon: Warning },
  { label: '客户期望结果', value: t.value.expected_result || '—', icon: Document },
  { label: '优先级', value: priorityText.value, icon: Flag },
  ...(t.value.category_path ? [{ label: '当前分类路径', value: t.value.category_path, icon: Collection, full: true }] : []),
  ...(t.value.symptom ? [{ label: '故障现象', value: t.value.symptom, icon: Warning }] : []),
  ...(t.value.is_duplicate ? [{ label: '重投工单', value: `${t.value.duplicate_of?.number || '是'}${t.value.duplicate_reason ? `：${t.value.duplicate_reason}` : ''}`, icon: Tickets, full: true }] : []),
  { label: '客户问题详情', value: t.value.description || '—', icon: Document, full: true, description: true },
])
const faultFields = computed(() => [
  { label: '故障发生时间', value: formatTime(t.value.fault_occurred_at), icon: Clock },
  { label: '故障复现规律', value: t.value.fault_recurrence || '—', icon: Connection },
  { label: '故障发生地理位置', value: t.value.fault_location || '—', icon: Location },
  { label: '是否批量故障', value: yesNo(t.value.is_batch_fault), icon: Warning },
])
function formatTime(value?: string | null): string { return value && dayjs(value).isValid() ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' }
function yesNo(value?: boolean | null): string { return value == null ? '—' : value ? '是' : '否' }
</script>

<style scoped>
.fields { display: grid; column-gap: 18px; }
.system-fields, .content-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.customer-fields, .fault-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.field { min-width: 0; min-height: 60px; display: flex; align-items: center; gap: 14px; border-bottom: 1px solid #17466d; }
.field-icon { width: 40px; height: 40px; flex: none; display: grid; place-items: center; border: 1px solid #164e78; border-radius: 8px; background: linear-gradient(135deg, #0a3d68, #092a4b); color: #8fd1ff; }
.field-icon :deep(svg) { width: 19px; height: 19px; }
.field-copy { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.field-copy > span { font-size: 12px; color: #8fb8dc; }
.field-copy > strong { min-width: 0; color: #ecf6ff; font-size: 14px; font-weight: 500; line-height: 1.45; overflow-wrap: anywhere; white-space: pre-wrap; }
.field.full { grid-column: 1 / -1; }
.field.description-field { align-items: flex-start; padding: 10px 0; }
.field.description-field .field-copy > strong { line-height: 1.7; }
@media (max-width: 1200px) {
  .system-fields, .content-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .system-fields, .customer-fields, .content-fields, .fault-fields { grid-template-columns: 1fr; }
}
</style>
