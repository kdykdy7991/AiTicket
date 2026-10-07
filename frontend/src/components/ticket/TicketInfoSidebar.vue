<template>
  <div class="ticket-sidebar" v-if="ticket">
    <!--
      责任归属：工单流程两阶段——问题判断 → 问题处理。
      客服组:创建人 恒存在（工单必由客服组建单）；
      问题判断组 可多环（售后 → 星座大系统负责人），空 = 客服组已完成判断；
      流转节点 处理链的中间环节（线性推进），空 = 无需流转；
      问题处理部门 处理链最后一环，判断节点未分诊时为「待分诊确定」。
    -->
    <div class="sidebar-section">
      <h4 class="section-title">责任归属</h4>
      <div class="field-row">
        <span class="field-label">客服组:创建人</span>
        <span class="field-value">{{ creatorSlotText }}</span>
      </div>
      <div class="field-row">
        <span class="field-label">问题判断组</span>
        <span class="field-value">
          <template v-if="judgementDepartments.length">
            <span
              v-for="(dept, i) in judgementDepartments"
              :key="dept"
              :class="{ 'dept-sep': i > 0 }"
            >{{ dept }}</span>
          </template>
          <span v-else class="muted">客服组已完成判断</span>
        </span>
      </div>
      <div class="field-row">
        <span class="field-label">流转节点</span>
        <span class="field-value">
          <template v-if="transitDepartments.length">
            <span
              v-for="(dept, i) in transitDepartments"
              :key="dept"
              :class="{ 'dept-sep': i > 0 }"
            >{{ dept }}</span>
          </template>
          <span v-else class="muted">无需流转</span>
        </span>
      </div>
      <div class="field-row">
        <span class="field-label">问题处理部门</span>
        <span class="field-value">
          {{ handlingDepartment || '待分诊确定' }}
        </span>
      </div>
      <div class="field-row">
        <span class="field-label">处理人</span>
        <span class="field-value">
          <span>{{ (ticket as any).owner_name || '未分配' }}</span>
          <span v-if="(ticket as any).owner_department" class="dept-tag">
            {{ (ticket as any).owner_department }}
          </span>
        </span>
      </div>
    </div>

    <div class="sidebar-divider" />

    <!-- 属性 -->
    <div class="sidebar-section">
      <h4 class="section-title">属性</h4>
      <div class="field-row">
        <span class="field-label">优先级</span>
        <span class="field-value">{{ ticket.priority?.name || '—' }}</span>
      </div>
      <div class="field-row">
        <span class="field-label">来源</span>
        <span class="field-value">
          <span class="channel-badge" :class="`channel-${ticket.channel}`">{{ channelLabel(ticket.channel) }}</span>
        </span>
      </div>
      <div class="field-row">
        <span class="field-label">SLA</span>
        <span class="field-value">
          <span :class="['sla-tag', ticket.sla_breached ? 'breached' : 'ok']">
            {{ ticket.sla_breached ? '超时' : '达标' }}
          </span>
        </span>
      </div>
    </div>

    <div class="sidebar-divider" />

    <!-- 客户信息 -->
    <div class="sidebar-section">
      <h4 class="section-title">客户信息</h4>
      <div class="info-row">
        <span class="info-label">客户</span>
        <UserAvatar :user="ticket.customer" :size="22" :show-name="true" />
      </div>
      <div class="info-row" v-if="ticket.customer_type">
        <span class="info-label">类型</span>
        <CustomerTypeChip :type="ticket.customer_type" />
      </div>
      <div class="info-row" v-if="ticket.customer_phone">
        <span class="info-label">来电号码</span>
        <span class="info-value mono">{{ ticket.customer_phone }}</span>
      </div>
      <div class="info-row" v-if="ticket.device_sn">
        <span class="info-label">设备 SN</span>
        <span class="info-value mono">{{ ticket.device_sn }}</span>
      </div>
      <div class="info-row" v-if="ticket.contact_name">
        <span class="info-label">联系人</span>
        <span class="info-value">{{ ticket.contact_name }}</span>
      </div>
      <div class="info-row">
        <span class="info-label">联系号码</span>
        <span class="info-value mono">{{ ticket.contact_phone || '—' }}</span>
      </div>
      <div class="info-row" v-if="ticket.region_name || (ticket.region && (ticket.region.province || ticket.region.city))">
        <span class="info-label">区域</span>
        <span class="info-value">{{
          ticket.region_name ||
          [ticket.region?.province, ticket.region?.city, ticket.region?.district, ticket.region?.station].filter(Boolean).join(' / ')
        }}</span>
      </div>
      <div class="info-row" v-if="ticket.customer_type === 'enterprise'">
        <span class="info-label">单位名称</span>
        <span class="info-value">{{ ticket.organization?.name || '—' }}</span>
      </div>
    </div>

    <div class="sidebar-divider" />

    <!-- 分类信息：展示完整路径（分类树深度不定，最多 4 层） -->
    <div class="sidebar-section">
      <h4 class="section-title">分类</h4>
      <div class="info-row" v-if="categoryText">
        <span class="info-label">分类</span>
        <span class="info-value">{{ categoryText }}</span>
      </div>
      <div class="info-row" v-if="!categoryText && ticket.category_l1">
        <span class="info-label">一级</span>
        <span class="info-value">{{ ticket.category_l1.name }}</span>
      </div>
      <div class="info-row" v-if="!categoryText && ticket.category_l2">
        <span class="info-label">二级</span>
        <span class="info-value">{{ ticket.category_l2.name }}</span>
      </div>
      <div class="info-row" v-if="ticket.symptom">
        <span class="info-label">故障</span>
        <span class="info-value symptom">{{ ticket.symptom }}</span>
      </div>
    </div>

    <!-- 重投提示 -->
    <template v-if="ticket.is_duplicate">
      <div class="sidebar-divider" />
      <div class="sidebar-section dup-section">
        <h4 class="section-title">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="17,1 21,5 17,9"/><path d="M3 11V9a4 4 0 0 1 4-4h14"/>
            <polyline points="7,23 3,19 7,15"/><path d="M21 13v2a4 4 0 0 1-4 4H3"/>
          </svg>
          重投工单
        </h4>
        <div v-if="ticket.duplicate_of" class="info-row">
          <span class="info-label">重投自</span>
          <router-link :to="{ name: 'TicketDetail', params: { id: ticket.duplicate_of.id } }" class="dup-link">
            {{ ticket.duplicate_of.number }}
          </router-link>
        </div>
        <div v-if="ticket.duplicate_reason" class="dup-reason">{{ ticket.duplicate_reason }}</div>
      </div>
    </template>

    <div class="sidebar-divider" />

    <!-- 处理结果 -->
    <div class="sidebar-section">
      <h4 class="section-title">处理结果</h4>
      <div class="info-row" v-if="ticket.resolved">
        <span class="info-label">解决</span>
        <span class="info-value resolved-yes">已解决</span>
      </div>
      <div v-if="ticket.resolution" class="resolution-block">
        <div class="resolution-label">解决方案</div>
        <div class="resolution-body">{{ ticket.resolution }}</div>
      </div>
    </div>

    <!-- 回访闭环：是否回访 / 满意度 / 回访详情（callback_details 贯通展示） -->
    <template v-if="ticket.is_callbacked || ticket.callback_details || ticket.satisfaction">
      <div class="sidebar-divider" />
      <div class="sidebar-section">
        <h4 class="section-title">回访</h4>
        <div class="info-row">
          <span class="info-label">状态</span>
          <span class="info-value">{{ ticket.is_callbacked ? '已回访' : '未回访' }}</span>
        </div>
        <div class="info-row" v-if="ticket.satisfaction">
          <span class="info-label">满意度</span>
          <span :class="['info-value', `sat-${ticket.satisfaction}`]">{{ satisfactionLabel(ticket.satisfaction) }}</span>
        </div>
        <!-- 不满意原因（V0.87 收尾：unsatisfied_reason，dissatisfied 时非空） -->
        <div v-if="ticket.satisfaction === 'dissatisfied' && ticket.unsatisfied_reason" class="resolution-block">
          <div class="resolution-label">不满意原因</div>
          <div class="resolution-body">{{ ticket.unsatisfied_reason }}</div>
        </div>
        <div v-if="ticket.callback_details" class="resolution-block">
          <div class="resolution-label">回访详情</div>
          <div class="resolution-body">{{ ticket.callback_details }}</div>
        </div>
      </div>
    </template>

    <template v-if="ticket.escalation_at">
      <div class="sidebar-divider" />
      <div class="sidebar-section">
        <h4 class="section-title">SLA</h4>
        <SLAIndicator :escalation-at="ticket.escalation_at" :total-minutes="totalSLAMinutes" />
      </div>
    </template>

    <template v-if="ticket.links?.length">
      <div class="sidebar-divider" />
      <div class="sidebar-section">
        <h4 class="section-title">关联工单</h4>
        <div v-for="link in ticket.links" :key="link.id" class="link-item">
          <router-link :to="{ name: 'TicketDetail', params: { id: link.target_ticket.id } }" class="link-anchor">
            <span class="link-number">{{ link.target_ticket.number }}</span>
          </router-link>
        </div>
      </div>
    </template>

    <div class="sidebar-divider" />

    <!-- 时间 -->
    <div class="sidebar-section">
      <h4 class="section-title">时间</h4>
      <div class="info-row">
        <span class="info-label">创建</span>
        <RelativeTime :datetime="ticket.created_at" />
      </div>
      <div class="info-row">
        <span class="info-label">更新</span>
        <RelativeTime :datetime="ticket.updated_at" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import UserAvatar from '@/components/common/UserAvatar.vue'
import CustomerTypeChip from '@/components/common/CustomerTypeChip.vue'
import SLAIndicator from '@/components/common/SLAIndicator.vue'
import RelativeTime from '@/components/common/RelativeTime.vue'
import type { TicketDetail, TicketChannel } from '@/types'

const props = defineProps<{ ticket: TicketDetail }>()

/**
 * 分类展示文案：优先用后端下发的完整路径（分类树深度不定，最多 4 层，
 * L1/L2 不足以表达 3、4 层），缺失时回退到一级/二级拼接。
 */
const categoryText = computed(() => {
  const t = props.ticket
  if (t.category_path) return t.category_path
  const parts = [t.category_l1?.name, t.category_l2?.name].filter(Boolean)
  return parts.length ? parts.join(' / ') : ''
})

/** 客服组:创建人 —— 工单必由客服组建单，两值合并成一行 */
const creatorSlotText = computed(() => {
  const t = props.ticket as any
  const group = t.group_name || '—'
  const creator = t.creator_name || '—'
  return `${group} / ${creator}`
})

/** 问题判断组：空数组 = 客服组建单时已完成判断 */
const judgementDepartments = computed<string[]>(
  () => (props.ticket as any).judgement_departments || []
)

/** 流转节点：处理链的中间环节，空 = 无需流转 */
const transitDepartments = computed<string[]>(
  () => (props.ticket as any).transit_departments || []
)

/** 问题处理部门：判断节点未分诊时后端返回 null */
const handlingDepartment = computed<string>(
  () => (props.ticket as any).handling_department || ''
)

// SLA 总时长 = 创建时间 →  escalation_at（解决/首次响应截止时间）
const totalSLAMinutes = computed(() => {
  const t = props.ticket
  if (!t.escalation_at || !t.created_at) return undefined
  return dayjs(t.escalation_at).diff(dayjs(t.created_at), 'minute')
})

function channelLabel(c: TicketChannel): string {
  const map: Record<TicketChannel, string> = {
    web: 'Web', email: '邮件', phone: '电话', wechat: '微信', app: 'App',
  }
  return map[c]
}

function satisfactionLabel(v: string): string {
  const map: Record<string, string> = {
    satisfied: '满意', average: '一般', dissatisfied: '不满意', unrated: '未评价',
  }
  return map[v] || v
}
</script>

<style scoped>
.ticket-sidebar { padding: 20px; }

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0;
}
/* 多环分隔：售后 → 星座大系统负责人 */
.dept-sep { margin-left: 6px; }
.dept-sep::before {
  content: '→';
  margin-right: 6px;
  color: var(--color-text-placeholder);
}
/* 人员所属部门标注：跨部门错配时一眼可见 */
.dept-tag {
  margin-left: 6px;
  padding: 1px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-bg-subtle);
  color: var(--color-text-tertiary);
  font-size: 11px;
  font-weight: 500;
}
/* 语义化占位（客服组已完成判断 / 未分配 等） */
.muted { color: var(--color-text-tertiary); }

.sidebar-divider {
  height: 1px;
  background: var(--color-divider);
  margin: 16px 0;
}

.field-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.field-label {
  font-size: 13px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
  width: 96px;
  font-weight: 500;
}
.field-select { flex: 1; }
.field-value { flex: 1; font-size: 13px; color: var(--color-text-primary); }
.field-select :deep(.el-input__wrapper) {
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  box-shadow: none;
}
.field-select :deep(.el-input__wrapper:hover) { border-color: var(--color-border); }

.info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  min-height: 22px;
}
.info-label {
  color: var(--color-text-tertiary);
  width: 56px;
  flex-shrink: 0;
  font-weight: 500;
}
.info-value {
  color: var(--color-text-primary);
  font-weight: 500;
  word-break: break-word;
}
.info-value.mono {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12.5px;
}
/* 回访满意度着色 */
.info-value.sat-satisfied { color: #67c23a; }
.info-value.sat-average { color: #e6a23c; }
.info-value.sat-dissatisfied { color: #f56c6c; font-weight: 600; }
.info-value.sat-unrated { color: var(--color-text-tertiary); }
.muted { color: var(--color-text-tertiary); font-weight: 400; }
.symptom {
  font-size: 12.5px;
  line-height: 1.5;
  font-weight: 400;
}

/* 渠道 chip */
.channel-badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11.5px;
  font-weight: 600;
}
.channel-web    { background: rgba(99,91,255,0.10); color: #4338CA; }
.channel-email  { background: var(--color-info-light); color: var(--color-info-text); }
.channel-phone  { background: rgba(16,185,129,0.10); color: #065F46; }
.channel-wechat { background: rgba(7,193,96,0.12); color: #065F46; }
.channel-app    { background: rgba(245,158,11,0.12); color: #92400E; }

/* SLA 标签 */
.sla-tag {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11.5px;
  font-weight: 600;
}
.sla-tag.ok { background: rgba(16,185,129,0.10); color: #065F46; }
.sla-tag.breached { background: rgba(239,68,68,0.10); color: #B91C1C; }

.resolved-yes { color: #065F46; font-weight: 600; }

/* 解决方案 */
.resolution-block {
  margin-top: 6px;
  padding: 8px 10px;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-sm);
  border-left: 3px solid var(--color-success);
}
.resolution-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-weight: 600;
  margin-bottom: 4px;
}
.resolution-body {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--color-text-primary);
  white-space: pre-wrap;
}

/* 重投区域 */
.dup-section { background: #FFFBEB; padding: 10px 12px; border-radius: var(--radius-md); border: 1px dashed #FCD34D; }
.dup-link {
  font-size: 12.5px;
  color: var(--color-primary);
  font-weight: 500;
}
.dup-link:hover { text-decoration: underline; }
.dup-reason {
  margin-top: 4px;
  font-size: 12px;
  color: #92400E;
  line-height: 1.5;
}

/* 关联工单 */
.link-item { font-size: 13px; }
.link-anchor {
  display: flex;
  align-items: baseline;
  gap: 6px;
  padding: 4px 8px;
  margin: -4px -8px;
  border-radius: var(--radius-sm);
  transition: background var(--duration-fast) var(--ease-out);
}
.link-anchor:hover { background: var(--color-bg-hover); }
.link-number {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 12px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}
</style>
