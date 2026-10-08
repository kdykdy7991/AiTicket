<template>
  <section class="overview-card">
    <h3 class="card-title"><svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="M6 16c.7-1.5 1.7-2 3-2s2.3.5 3 2M15 9h3M15 13h3"/></svg>基本信息</h3>
    <div class="overview-grid">
      <div class="info-column">
        <div class="info-row"><span>标题</span><strong>{{ t.title || t.subject || t.symptom || '—' }}</strong></div>
        <div class="info-row"><span>问题分类</span><strong>{{ t.category_path || [t.category_l1?.name, t.category_l2?.name].filter(Boolean).join(' / ') || '—' }}</strong></div>
        <div v-if="t.symptom" class="info-row"><span>故障现象</span><strong>{{ t.symptom }}</strong></div>
        <div class="info-row"><span>创建人</span><strong>{{ t.creator_name || '—' }}</strong></div>
      </div>
      <div class="info-column">
        <div class="info-row"><span>客户</span><strong>{{ customerName }}</strong></div>
        <div class="info-row"><span>客户类型</span><strong>{{ t.customer_type === 'enterprise' ? '企业' : '个人' }}</strong></div>
        <div v-if="t.organization?.name" class="info-row"><span>单位名称</span><strong>{{ t.organization.name }}</strong></div>
        <div v-if="t.customer_phone" class="info-row"><span>来电号码</span><strong>{{ t.customer_phone }}</strong></div>
        <div v-if="t.contact_name" class="info-row"><span>联系人</span><strong>{{ t.contact_name }}</strong></div>
        <div class="info-row"><span>联系号码</span><strong>{{ t.contact_phone || '—' }}</strong></div>
        <div v-if="regionText" class="info-row"><span>区域</span><strong>{{ regionText }}</strong></div>
        <div v-if="t.device_sn" class="info-row"><span>设备 SN</span><strong>{{ t.device_sn }}</strong></div>
      </div>
    </div>
    <div class="overview-grid section-divider">
      <div class="info-column">
        <div class="info-row"><span>优先级</span><strong>{{ t.priority?.name || '—' }}</strong></div>
        <div class="info-row"><span>来源</span><strong>{{ channelText }}</strong></div>
        <div class="info-row"><span>SLA</span><strong :class="t.sla_breached ? 'status-bad' : 'status-good'">{{ t.sla_breached ? '超时' : '达标' }}</strong></div>
      </div>
      <div class="info-column">
        <div class="info-row"><span>创建时间</span><strong>{{ formatTime(t.created_at) }}</strong></div>
        <div class="info-row"><span>最后更新</span><strong>{{ formatTime(t.updated_at) }}</strong></div>
        <div v-if="t.escalation_at" class="info-row"><span>处理时限</span><strong>{{ formatTime(t.escalation_at) }}</strong></div>
      </div>
    </div>
    <div v-if="t.resolution || t.root_cause || t.solution || t.is_callbacked || t.satisfaction" class="section-divider responsibility">
      <h3 class="card-title"><svg class="title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg>处理结果</h3>
      <div class="overview-grid">
        <div class="info-column">
          <div v-if="t.root_cause" class="info-row"><span>根本原因</span><strong>{{ t.root_cause }}</strong></div>
          <div v-if="t.solution || t.resolution" class="info-row"><span>解决方案</span><strong>{{ t.solution || t.resolution }}</strong></div>
        </div>
        <div class="info-column">
          <div v-if="t.is_callbacked" class="info-row"><span>回访</span><strong>已回访</strong></div>
          <div v-if="t.satisfaction" class="info-row"><span>满意度</span><strong>{{ satisfactionText }}</strong></div>
          <div v-if="t.callback_details" class="info-row"><span>回访详情</span><strong>{{ t.callback_details }}</strong></div>
          <div v-if="t.unsatisfied_reason" class="info-row"><span>不满意原因</span><strong>{{ t.unsatisfied_reason }}</strong></div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import type { TicketDetail, User } from '@/types'

const props = defineProps<{ ticket: TicketDetail }>()
const t = computed<any>(() => props.ticket)
function userName(user?: User | null) { return user ? `${user.firstname || ''}${user.lastname || ''}` : '' }
const customerName = computed(() => t.value.customer_name || userName(t.value.customer) || '—')
const regionText = computed(() => t.value.region_name || [t.value.region?.province, t.value.region?.city, t.value.region?.district, t.value.region?.station].filter(Boolean).join(' / '))
const channelText = computed(() => ({ web: 'Web', email: '邮件', phone: '电话', wechat: '微信', app: 'App' } as Record<string, string>)[t.value.channel] || '—')
const satisfactionText = computed(() => ({ satisfied: '满意', average: '一般', dissatisfied: '不满意', unrated: '未评价' } as Record<string, string>)[t.value.satisfaction] || t.value.satisfaction)
function formatTime(value?: string) { return value ? dayjs(value).format('YYYY/MM/DD HH:mm:ss') : '—' }
</script>

<style scoped>
.overview-card { padding: 22px 26px; background: var(--color-bg-card); border: 1px solid var(--color-border-light); border-radius: var(--radius-lg); box-shadow: var(--shadow-xs); }
.card-title { display: flex; align-items: center; gap: 10px; margin: 0 0 20px; color: var(--color-text-primary); font-size: 15px; font-weight: 700; }
.title-icon { width: 19px; height: 19px; flex: none; color: var(--color-primary); }
.overview-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 32px; }
.info-column { display: flex; flex-direction: column; gap: 15px; min-width: 0; }
.info-column + .info-column { border-left: 1px solid var(--color-divider); padding-left: 32px; }
.info-row { display: grid; grid-template-columns: 132px minmax(0, 1fr); gap: 12px; align-items: baseline; font-size: 13px; }
.info-row > span { color: var(--color-text-tertiary); }
.info-row > strong { color: var(--color-text-primary); font-weight: 550; min-width: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.info-row > .status-good { color: #047857; }
.info-row > .status-bad { color: #b91c1c; }
.section-divider { border-top: 1px solid var(--color-divider); margin-top: 24px; padding-top: 24px; }
.responsibility .card-title { margin-bottom: 18px; }
@media (max-width: 700px) { .overview-grid { grid-template-columns: 1fr; gap: 15px; } .info-column + .info-column { border-left: 0; padding-left: 0; } .info-row { grid-template-columns: 112px minmax(0, 1fr); } }
</style>
