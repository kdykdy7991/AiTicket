<template>
  <div class="ticket-information">
    <TicketFormSection title="工单信息" icon="Setting">
      <div class="fields system-fields">
        <div class="field"><span>工单号</span><strong>{{ t.number || '—' }}</strong></div>
        <div class="field"><span>受理工号</span><strong>{{ t.creator_username || t.creator_account || '—' }}</strong></div>
        <div class="field"><span>受理人</span><strong>{{ t.creator_name || '—' }}</strong></div>
        <div class="field"><span>受理班组</span><strong>{{ t.creator_group_name || t.creator_group || '—' }}</strong></div>
        <div class="field"><span>受理时间</span><strong>{{ formatTime(t.created_at) }}</strong></div>
        <div class="field"><span>受理渠道</span><strong>{{ channelText }}</strong></div>
      </div>
    </TicketFormSection>

    <TicketFormSection title="客户信息" icon="User">
      <div class="fields customer-fields">
        <div class="field"><span>客户名称</span><strong>{{ customerName }}</strong></div>
        <div class="field"><span>单位全称</span><strong>{{ t.customer_company || t.organization?.name || '—' }}</strong></div>
        <div class="field"><span>联系人</span><strong>{{ t.contact_name || '—' }}</strong></div>
        <div class="field"><span>行业</span><strong>{{ t.industry || '—' }}</strong></div>
        <div class="field"><span>来电号码</span><strong>{{ t.customer_phone || '—' }}</strong></div>
        <div class="field"><span>联系号码</span><strong>{{ t.contact_phone || '—' }}</strong></div>
        <div v-if="regionText || t.device_sn" class="field"><span>区域</span><strong>{{ regionText || '—' }}</strong></div>
        <div v-if="regionText || t.device_sn" class="field"><span>设备 SN</span><strong>{{ t.device_sn || '—' }}</strong></div>
      </div>
    </TicketFormSection>

    <TicketFormSection title="工单内容" icon="Document">
      <div class="fields content-fields">
        <div class="field"><span>卫星物联网码号</span><strong>{{ t.satellite_number || '—' }}</strong></div>
        <div class="field"><span>一级分类</span><strong>{{ t.category_l1?.name || '—' }}</strong></div>
        <div class="field"><span>二级分类</span><strong>{{ t.category_l2?.name || '—' }}</strong></div>
        <div class="field"><span>是否为线索工单</span><strong>{{ yesNo(t.is_opportunity) }}</strong></div>
        <div class="field"><span>客户期望结果</span><strong>{{ t.expected_result || '—' }}</strong></div>
        <div class="field"><span>优先级</span><strong>{{ priorityText }}</strong></div>
        <div v-if="t.category_path" class="field full compact-field"><span>当前分类路径</span><strong>{{ t.category_path }}</strong></div>
        <div v-if="t.symptom" class="field compact-field"><span>故障现象</span><strong>{{ t.symptom }}</strong></div>
        <div v-if="t.is_duplicate" class="field full compact-field"><span>重投工单</span><strong>{{ t.duplicate_of?.number || '是' }}{{ t.duplicate_reason ? `：${t.duplicate_reason}` : '' }}</strong></div>
        <div class="field full description-field"><span>客户问题详情</span><strong>{{ t.description || '—' }}</strong></div>
      </div>
    </TicketFormSection>

    <TicketFormSection v-if="hasFaultInfo" title="故障信息" icon="Tools">
      <div class="fields fault-fields">
        <div class="field"><span>故障发生时间</span><strong>{{ formatTime(t.fault_occurred_at) }}</strong></div>
        <div class="field"><span>故障复现规律</span><strong>{{ t.fault_recurrence || '—' }}</strong></div>
        <div class="field"><span>故障发生地理位置</span><strong>{{ t.fault_location || '—' }}</strong></div>
        <div class="field"><span>是否批量故障</span><strong>{{ yesNo(t.is_batch_fault) }}</strong></div>
      </div>
    </TicketFormSection>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
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
function formatTime(value?: string | null): string { return value && dayjs(value).isValid() ? dayjs(value).format('YYYY-MM-DD HH:mm:ss') : '—' }
function yesNo(value?: boolean | null): string { return value == null ? '—' : value ? '是' : '否' }
</script>

<style scoped>
.fields { display: grid; gap: 13px 18px; }
.system-fields, .content-fields { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.customer-fields, .fault-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.field { min-width: 0; display: flex; flex-direction: column; gap: 7px; }
.field > span { font-size: 12px; font-weight: 650; color: var(--color-text-secondary); }
.field > strong { display: flex; align-items: center; min-width: 0; min-height: 36px; padding: 8px 11px; border: 1px solid var(--color-border-light); border-radius: var(--radius-md); background: var(--color-bg-page); color: var(--color-text-primary); font-size: 13px; font-weight: 500; line-height: 1.5; overflow-wrap: anywhere; white-space: pre-wrap; }
.field.full { grid-column: 1 / -1; }
.field.description-field > strong { min-height: 100px; align-items: flex-start; line-height: 1.7; }
@media (max-width: 1200px) {
  .system-fields, .content-fields { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 700px) {
  .system-fields, .customer-fields, .content-fields, .fault-fields { grid-template-columns: 1fr; }
}
</style>
