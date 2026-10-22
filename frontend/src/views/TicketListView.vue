<template>
  <div class="ticket-list-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">工单列表</h2>
      </div>
      <div class="header-actions">
        <el-button @click="exportDialogVisible = true" class="export-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right: 6px">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7,10 12,15 17,10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          导出
        </el-button>
        <el-button v-if="authStore.isAgent" type="primary" @click="router.push({ name: 'TicketCreate' })" class="create-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" style="margin-right: 6px">
            <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
          </svg>
          新建工单
        </el-button>
      </div>
    </div>

    <!-- 快捷分类标签 -->
    <div class="quick-tabs">
      <button
        v-for="tab in quickTabs"
        :key="tab.key"
        class="quick-tab"
        :class="{ active: activeTab === tab.key }"
        @click="onQuickTab(tab.key)"
      >
        {{ tab.label }}
        <span v-if="tab.count !== undefined" class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <TicketFilters :model-value="ticketStore.filters" @update:model-value="onFilterChange" />

    <el-card shadow="never" v-loading="ticketStore.loading" class="list-card">
      <TicketTable :tickets="ticketStore.tickets" />

      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="ticketStore.pagination.per_page"
          :total="ticketStore.pagination.total"
          layout="total, prev, pager, next"
          @current-change="onPageChange"
        />
      </div>
    </el-card>

    <!-- 导出对话框 -->
    <el-dialog
      v-model="exportDialogVisible"
      title="导出工单"
      width="680px"
      align-center
      class="ticket-list-export-dialog"
    >
      <div class="export-dialog">
        <div class="export-summary">
          将按当前筛选条件导出 <b>{{ ticketStore.pagination.total }}</b> 条工单，选择要包含的字段：
        </div>

        <div class="export-columns">
          <div v-for="group in columnGroups" :key="group.key" class="column-group">
            <div class="group-label">
              <el-checkbox
                :model-value="isGroupAllChecked(group)"
                :indeterminate="isGroupIndeterminate(group)"
                @change="(v: boolean) => toggleGroup(group, v)"
              >
                {{ group.label }}（{{ group.columns.length }}）
              </el-checkbox>
            </div>
            <div class="group-columns">
              <el-checkbox
                v-for="col in group.columns"
                :key="col.key"
                v-model="selectedColumns"
                :value="col.key"
              >
                {{ col.label }}
              </el-checkbox>
            </div>
          </div>
        </div>
      </div>

      <template #footer>
        <el-button @click="exportDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="exporting" :disabled="selectedColumns.length === 0" @click="onExport">
          导出 {{ selectedColumns.length }} 列
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { useAuthStore } from '@/stores/auth'
import { ticketApi } from '@/api/tickets'
import TicketFilters from '@/components/ticket/TicketFilters.vue'
import TicketTable from '@/components/ticket/TicketTable.vue'
import { ElMessage } from 'element-plus'
import type { TicketFilters as Filters, ExportColumn } from '@/types'

const router = useRouter()
const ticketStore = useTicketStore()
const authStore = useAuthStore()
const currentPage = ref(1)

// 快捷分类标签：全部 + 7 个状态（id 与后端 STATE_ID_TO_KEY 1..7 对应）+ 已超时
const activeTab = ref('all')
const quickTabs = computed(() => [
  { key: 'all', label: '全部' },
  { key: 'pending', label: '待受理', stateId: 1 },
  { key: 'open', label: '处理中', stateId: 2 },
  { key: 'resolved', label: '已处理', stateId: 3 },
  { key: 'on_hold', label: '暂缓处理', stateId: 4 },
  { key: 'archived', label: '已归档', stateId: 5 },
  { key: 'returned', label: '已退回', stateId: 6 },
  { key: 'cancelled', label: '已撤销', stateId: 7 },
  { key: 'overdue', label: '已超时', isOverdue: true },
] as Array<{ key: string; label: string; stateId?: number; isOverdue?: boolean; count?: number }>)

function onQuickTab(key: string) {
  activeTab.value = key
  currentPage.value = 1
  const tab = quickTabs.value.find(t => t.key === key)
  // 保留现有筛选条件（日期、优先级、搜索等），只叠加或移除 state_id / is_overdue
  const filters: Filters = { ...ticketStore.filters }
  if (tab?.stateId) {
    filters.state_id = tab.stateId
  } else {
    delete filters.state_id
  }
  if (tab?.isOverdue) {
    filters.is_overdue = true
  } else {
    delete filters.is_overdue
  }
  ticketStore.setFilters(filters)
  ticketStore.fetchTickets(1)
}

// 导出
const exportDialogVisible = ref(false)
const exporting = ref(false)
const selectedColumns = ref<string[]>([])

const columnGroups: Array<{ key: 'base' | 'customer' | 'category' | 'workflow'; label: string; columns: ExportColumn[] }> = [
  {
    key: 'base', label: '基础核心',
    columns: [
      { key: 'number', label: '工单号', group: 'base' },
      { key: 'created_at', label: '受理时间', group: 'base' },
      { key: 'closed_at', label: '结束时间', group: 'base' },
      { key: 'close_duration', label: '关闭时长（分钟）', group: 'base' },
      { key: 'state', label: '当前状态', group: 'base' },
      { key: 'channel', label: '受理渠道', group: 'base' },
    ],
  },
  {
    key: 'customer', label: '客户信息',
    columns: [
      { key: 'customer_name', label: '客户名称', group: 'customer' },
      { key: 'customer_company', label: '单位全称', group: 'customer' },
      { key: 'industry', label: '行业', group: 'customer' },
      { key: 'customer_phone', label: '来电号码', group: 'customer' },
      { key: 'contact_phone', label: '联系号码', group: 'customer' },
      { key: 'device_sn', label: '设备 SN', group: 'customer' },
      { key: 'region_name', label: '区域', group: 'customer' },
    ],
  },
  {
    key: 'category', label: '工单内容',
    columns: [
      { key: 'is_opportunity', label: '是否为线索工单', group: 'category' },
      { key: 'satellite_number', label: '卫星物联网码号', group: 'category' },
      { key: 'category_l1', label: '一级分类', group: 'category' },
      { key: 'category_l2', label: '二级分类', group: 'category' },
      { key: 'category_path', label: '分类路径', group: 'category' },
      { key: 'description', label: '客户问题详情', group: 'category' },
      { key: 'priority', label: '优先级', group: 'category' },
      { key: 'fault_occurred_at', label: '故障发生时间', group: 'category' },
      { key: 'fault_recurrence', label: '故障复现规律', group: 'category' },
      { key: 'fault_location', label: '故障发生地理位置', group: 'category' },
      { key: 'is_batch_fault', label: '是否批量故障', group: 'category' },
    ],
  },
  {
    key: 'workflow', label: '处理流转',
    columns: [
      { key: 'creator_name', label: '受理人', group: 'workflow' },
      { key: 'creator_group', label: '受理班组', group: 'workflow' },
      { key: 'dispatcher_name', label: '对接人', group: 'workflow' },
      { key: 'owner_name', label: '当前处理人', group: 'workflow' },
      { key: 'resolution', label: '处理结果', group: 'workflow' },
      { key: 'is_callbacked', label: '是否已回访', group: 'workflow' },
      { key: 'callback_details', label: '回访记录', group: 'workflow' },
      { key: 'customer_recognized', label: '客户是否认可', group: 'workflow' },
      { key: 'customer_satisfaction_score', label: '客户满意度评分', group: 'workflow' },
      { key: 'satisfaction', label: '客户满意度', group: 'workflow' },
      { key: 'archive_notes', label: '归档说明', group: 'workflow' },
      { key: 'sla_breached', label: 'SLA 解决时限', group: 'workflow' },
    ],
  },
]

onMounted(async () => {
  await ticketStore.fetchTickets()
  // 默认勾选所有列
  selectedColumns.value = columnGroups.flatMap(g => g.columns.map(c => c.key))
})

function onFilterChange(filters: Filters) {
  ticketStore.setFilters(filters)
  currentPage.value = 1
  ticketStore.fetchTickets(1)
}

function onPageChange(page: number) {
  ticketStore.fetchTickets(page)
}

function isGroupAllChecked(group: typeof columnGroups[number]): boolean {
  return group.columns.every(c => selectedColumns.value.includes(c.key))
}

function isGroupIndeterminate(group: typeof columnGroups[number]): boolean {
  const count = group.columns.filter(c => selectedColumns.value.includes(c.key)).length
  return count > 0 && count < group.columns.length
}

function toggleGroup(group: typeof columnGroups[number], checked: boolean) {
  const keys = group.columns.map(c => c.key)
  if (checked) {
    selectedColumns.value = Array.from(new Set([...selectedColumns.value, ...keys]))
  } else {
    selectedColumns.value = selectedColumns.value.filter(k => !keys.includes(k))
  }
}

async function onExport() {
  exporting.value = true
  try {
    const allColumns = columnGroups.flatMap(g => g.columns)
    const cols = allColumns.filter(c => selectedColumns.value.includes(c.key))
    const blob = await ticketApi.export({
      filters: ticketStore.filters,
      columns: cols.map(c => c.key),
    })
    // 触发下载
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `工单列表_${new Date().toLocaleDateString('sv-SE')}.csv`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
    exportDialogVisible.value = false
  } catch {
    ElMessage.error('导出失败')
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
}
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

.header-actions {
  display: flex;
  gap: 8px;
}
.export-btn, .create-btn {
  height: 38px;
  padding: 0 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

/* 多选已移除，无相关样式 */

.list-card { border: 1px solid var(--color-border-light); }
.list-card :deep(.el-card__body) { padding: 0; }
/* 行背景（灰色行/表头灰底）顶满卡片边：表格本身贴卡片边。
   视觉留白只放在 .el-table__cell 上，并清零 Element Plus .cell 自带的
   `padding: 0 12px`——两层叠加会变成每侧 28px（合计 56px），7 列共吃掉 392px，
   使各列可用宽度比内容实测需求少 24px，内容被裁切（.cell 默认
   `overflow: hidden` + `white-space: normal`，溢出表现为换行或截断而非省略号）。 */
.list-card :deep(.el-table .el-table__cell) {
  padding-left: 16px;
  padding-right: 16px;
}
.list-card :deep(.el-table .cell) {
  padding-left: 0;
  padding-right: 0;
}

/* 快捷分类标签 */
.quick-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.quick-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--color-border-light);
  background: var(--color-bg-card);
  border-radius: var(--radius-full);
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-out);
  font-family: var(--font-sans);
}
.quick-tab:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.quick-tab.active {
  background: var(--color-primary);
  border-color: var(--color-primary);
  color: #fff;
}
.quick-tab .tab-count {
  font-size: 11px;
  background: rgba(0,0,0,0.08);
  padding: 0 6px;
  border-radius: 10px;
}
.quick-tab.active .tab-count {
  background: rgba(255,255,255,0.25);
}

.pagination-wrapper {
  padding: 16px 20px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid var(--color-divider);
}

/* 导出对话框 */
.export-dialog { display: flex; flex-direction: column; gap: 16px; }
.export-summary { font-size: 13.5px; color: var(--color-text-secondary); }
.export-summary b { color: var(--color-primary); font-weight: 700; }

.export-format {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--color-bg-subtle);
  border-radius: var(--radius-sm);
}
.format-label { font-size: 13px; color: var(--color-text-secondary); font-weight: 500; }

.export-columns {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 360px;
  overflow-y: auto;
  padding: 4px;
}

.column-group {
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  padding: 10px 14px;
}
.group-label { margin-bottom: 6px; }
.group-label :deep(.el-checkbox__label) { font-weight: 600; }

.group-columns {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px 16px;
  padding-left: 24px;
}

/* 工单列表：深蓝指挥中心视觉。 */
.ticket-list-view { min-height: 100%; }
.page-header { align-items: center; margin-bottom: 19px; }
.page-title { font-size: 27px; letter-spacing: .02em; color: #edf7ff; text-shadow: 0 0 16px #40aaff3b; }
.header-actions { gap: 16px; }
.export-btn, .create-btn { height: 40px; border-radius: 4px; }
.export-btn { background: #041b36; border-color: #1778bd; color: #e7f4ff; }
.export-btn:hover { background: #0b3159; border-color: #3ba8eb; color: #fff; }
.create-btn { min-width: 150px; }
.quick-tabs { gap: 8px; margin-bottom: 14px; flex-wrap: nowrap; overflow-x: auto; padding-bottom: 2px; scrollbar-width: thin; }
.quick-tab { flex: none; min-height: 35px; padding: 5px 13px; border-radius: 4px; border-color: #15436c; background: #061c39; color: #c5d8ee; }
.quick-tab:hover { border-color: #2d90d0; color: #eff8ff; }
.quick-tab.active { background: linear-gradient(180deg, #0a6ac6, #084ba7); border-color: #278cdb; box-shadow: 0 0 11px #075fc56b, inset 0 1px #80c9ff50; }
.quick-tab .tab-count { background: #ffffff18; }
.list-card { border-color: #0d8cda; border-radius: 6px; background: #041b37; box-shadow: 0 0 19px #006fca4d; overflow: hidden; position: relative; }
.list-card::before, .list-card::after { content: ''; position: absolute; z-index: 2; width: 55px; height: 2px; background: #4bd5ff; box-shadow: 0 0 11px #4bd5ff; pointer-events: none; }
.list-card::before { top: 0; left: 13px; }
.list-card::after { bottom: 0; right: 13px; }
.list-card :deep(.el-table) { background: #041b37; }
.list-card :deep(.el-table__header th.el-table__cell) { height: 46px; background: linear-gradient(180deg, #0c4278, #072c52); color: #c9e2fb; border-bottom-color: #1b6193; font-size: 12px; font-weight: 600; text-transform: none; letter-spacing: 0; }
.list-card :deep(.el-table__body td.el-table__cell) { height: 48px; border-bottom-color: #0c385f; color: #c4d8f0; }
.list-card :deep(.el-table__body tr:nth-child(odd)) { background: #031a34; }
.list-card :deep(.el-table__body tr:nth-child(even)) { background: #051f3c; }
.list-card :deep(.el-table__body tr:hover > td.el-table__cell) { background: #0b345b; }
.list-card :deep(.el-table__empty-block) { background: #041b37; color: #98b7d6; }
.list-card :deep(.number-cell) { color: #b6d6f8; }
.list-card :deep(.title-badge) { border-radius: 4px; border: 1px solid transparent; }
.list-card :deep(.badge-sla) { background: #481c36; border-color: #9a345b; color: #ff9cb1; }
.list-card :deep(.badge-returned), .list-card :deep(.badge-dup) { background: #453216; border-color: #97701d; color: #ffd47a; }
.list-card :deep(.badge-addition) { background: #112e69; border-color: #174dbe; color: #85b7ff; }
.list-card :deep(.badge-more) { background: #143657; color: #bed4ea; }
.list-card :deep(.state-tag) { border: 1px solid currentColor; padding: 4px 10px; }
.list-card :deep(.state-new) { background: #0a2960; color: #78adff; }
.list-card :deep(.state-open) { background: #423111; color: #ffc54f; }
.list-card :deep(.state-pending) { background: #142e4d; color: #c3d8ee; }
.list-card :deep(.state-closed) { background: #06463e; color: #27e2b7; }
.list-card :deep(.state-merged) { background: #263052; color: #cac5ee; }
.list-card :deep(.priority-label) { color: #c4d8f0; }
.list-card :deep(.sla-cell.danger) { color: #ff7e99; }
.list-card :deep(.sla-cell.warning) { color: #ffc75f; }
.list-card :deep(.row-sla-warning) { background: linear-gradient(90deg, #4b371d66, #041b37) !important; }
.list-card :deep(.row-sla-danger) { background: linear-gradient(90deg, #64243b70, #041b37) !important; }
.list-card :deep(.row-sla-danger .number-cell) { color: #ff9cb1; }
.pagination-wrapper { border-top-color: #0c3d66; padding: 12px 18px; }
@media (max-width: 900px) { .page-title { font-size: 23px; } .header-actions { gap: 8px; } .create-btn { min-width: 0; } }
</style>
