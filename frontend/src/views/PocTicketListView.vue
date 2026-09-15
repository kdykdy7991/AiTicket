<template>
  <div>
    <div class="page-header">
      <div><h1>POC 问题</h1><p>跟踪问题从提交审批到批准闭环的完整过程</p></div>
      <div class="actions">
        <el-button v-if="auth.canViewReport" :loading="exporting" @click="exportList">导出跟踪表</el-button>
        <el-button v-if="auth.canCreateTicket" type="primary" @click="router.push('/tickets/new')">新建 POC 问题</el-button>
      </div>
    </div>


    <el-card shadow="never" class="filters">
      <el-select v-model="filters.priority" multiple collapse-tags placeholder="问题级别" clearable @change="reload">
        <el-option v-for="item in POC_PRIORITY_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-select v-model="filters.skill_group_id" placeholder="分系统" clearable filterable @change="reload">
        <el-option v-for="group in skillGroups" :key="group.id" :label="group.name" :value="group.id" />
      </el-select>
      <el-select v-model="filters.verification_status" placeholder="验证状态" clearable @change="reload">
        <el-option v-for="item in VERIFICATION_STATUS_OPTIONS" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
      <el-checkbox v-model="filters.is_overdue" @change="reload">仅看逾期</el-checkbox>
      <el-input v-model="filters.keyword" clearable placeholder="搜索编号、名称、客户或产品线" @keyup.enter="reload" @clear="reload" />
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table v-loading="loading" :data="tickets" @row-click="openDetail">
        <el-table-column prop="number" label="编号" width="145" />
        <el-table-column prop="title" label="问题名称" min-width="220" show-overflow-tooltip />
        <el-table-column prop="customer_name" label="客户" min-width="130" show-overflow-tooltip />
        <el-table-column prop="product_line" label="产品线" min-width="120" />
        <el-table-column label="级别" width="100"><template #default="{ row }"><span :class="['priority', row.priority]">{{ priorityLabel(row.priority) }}</span></template></el-table-column>
        <el-table-column label="当前阶段" min-width="150"><template #default="{ row }"><el-tag :type="stateType(row.state)">{{ stateLabel(row.state) }}</el-tag></template></el-table-column>
        <el-table-column prop="skill_group_name" label="分系统" min-width="120" />
        <el-table-column label="当前责任" min-width="150"><template #default="{ row }">{{ responsibleText(row) }}</template></el-table-column>
        <el-table-column label="计划完成时间" min-width="155"><template #default="{ row }"><span :class="{ overdue: row.is_overdue }">{{ formatTime(row.planned_completion_at) }}</span></template></el-table-column>
        <el-table-column label="更新时间" min-width="155"><template #default="{ row }">{{ formatTime(row.updated_at) }}</template></el-table-column>
        <el-table-column label="创建时间" min-width="155"><template #default="{ row }">{{ formatTime(row.created_at) }}</template></el-table-column>
      </el-table>
      <el-pagination v-if="pagination.total" v-model:current-page="pagination.page" :page-size="pagination.page_size" :total="pagination.total" layout="total, prev, pager, next" @current-change="load" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage } from 'element-plus'
import { pocTicketApi } from '@/api/pocTickets'
import { pocMetaApi } from '@/api/pocMeta'
import { useAuthStore } from '@/stores/auth'
import { POC_PRIORITY_OPTIONS, POC_STATE_OPTIONS, VERIFICATION_STATUS_OPTIONS, priorityLabel, roleLabel, stateLabel, type PocState } from '@/domain/pocWorkflow'
import type { PocTicketBrief, PocTicketFilters } from '@/types/poc'
import type { Group } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const loading = ref(false)
const exporting = ref(false)
const tickets = ref<PocTicketBrief[]>([])
const skillGroups = ref<Group[]>([])
const filters = reactive<PocTicketFilters>({ sort: 'updated_desc' })
const pagination = reactive({ page: 1, page_size: 20, total: 0, total_pages: 0 })

function stateType(state: PocState) {
  return POC_STATE_OPTIONS.find(item => item.value === state)?.type || 'info'
}
function formatTime(value: string | null) { return value ? dayjs(value).format('YYYY-MM-DD') : '—' }
/** 当前节点由哪个角色处理；该节点有指定经办人（批准人/分系统负责人/创建人）时一并显示 */
function responsibleText(row: PocTicketBrief) {
  const role = roleLabel(row.current_responsible_role)
  return row.current_responsible_user_name ? `${role} · ${row.current_responsible_user_name}` : role
}
function openDetail(row: PocTicketBrief) { router.push({ name: 'TicketDetail', params: { id: row.id } }) }
function reload() { pagination.page = 1; load(1) }

async function load(page = pagination.page) {
  loading.value = true
  try {
    const result = await pocTicketApi.list(filters, page, pagination.page_size)
    tickets.value = result.data
    Object.assign(pagination, result.pagination)
  } finally { loading.value = false }
}

async function exportList() {
  exporting.value = true
  try {
    const blob = await pocTicketApi.export(filters)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url; link.download = `poc_tickets_${dayjs().format('YYYYMMDD_HHmmss')}.csv`; link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('跟踪表已导出')
  } finally { exporting.value = false }
}

onMounted(async () => { skillGroups.value = await pocMetaApi.getSkillGroups(); await load() })
</script>

<style scoped>
.page-header { display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:20px; }
.page-header h1 { margin:0; font-size:24px; }.page-header p { margin:6px 0 0; color:var(--color-text-tertiary); }.actions{display:flex;gap:8px}
.filters :deep(.el-card__body){display:flex;align-items:center;gap:10px}.filters .el-select{width:170px}.filters .el-input{max-width:300px;margin-left:auto}.table-card{margin-top:14px}.table-card :deep(.el-table__row){cursor:pointer}.el-pagination{justify-content:flex-end;margin-top:16px}.priority{font-weight:600}.p0_blocker{color:#dc2626}.p1_critical{color:#ea580c}.p2_normal{color:#2563eb}.p3_low{color:#64748b}.overdue{color:#dc2626;font-weight:600}
</style>
