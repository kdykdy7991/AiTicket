<template>
  <div class="ticket-list-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">工单列表</h2>
        <p class="page-subtitle">管理和追踪所有工单</p>
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
        <el-button type="primary" @click="router.push({ name: 'TicketCreate' })" class="create-btn">
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

    <!-- 批量操作工具栏 -->
    <transition name="batch-bar">
      <div v-if="selectedTickets.length > 0" class="batch-bar">
        <div class="batch-info">
          <span class="batch-count">已选 {{ selectedTickets.length }} 条</span>
          <el-button text size="small" @click="clearSelection">取消选择</el-button>
        </div>
        <div class="batch-actions">
          <el-select v-model="batchField" placeholder="选择要批量修改的字段" size="small" style="width: 160px" @change="onBatchFieldChange">
            <el-option label="批量改状态" value="state_id" />
            <el-option label="批量改优先级" value="priority_id" />
            <el-option label="批量改负责人" value="owner_id" />
            <el-option label="批量改客服组" value="group_id" />
          </el-select>
          <el-select v-if="batchField" v-model="batchValue" placeholder="选择新值" size="small" style="width: 160px" clearable>
            <template v-if="batchField === 'state_id'">
              <el-option v-for="s in states" :key="s.id" :label="s.name" :value="s.id" />
            </template>
            <template v-else-if="batchField === 'priority_id'">
              <el-option v-for="p in priorities" :key="p.id" :label="p.name" :value="p.id" />
            </template>
            <template v-else-if="batchField === 'owner_id'">
              <el-option v-for="a in agents" :key="a.id" :label="`${a.firstname}${a.lastname}`" :value="a.id" />
              <el-option label="取消分配" :value="null" />
            </template>
            <template v-else-if="batchField === 'group_id'">
              <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
            </template>
          </el-select>
          <el-button type="primary" size="small" :disabled="!batchField || batchValue === ''" :loading="batchUpdating" @click="onBatchApply">
            应用
          </el-button>
        </div>
      </div>
    </transition>

    <el-card shadow="never" v-loading="ticketStore.loading" class="list-card">
      <TicketTable
        :tickets="ticketStore.tickets"
        :selectable="true"
        @selection-change="onSelectionChange"
      />

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
import { ref, reactive, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTicketStore } from '@/stores/ticket'
import { useAuthStore } from '@/stores/auth'
import { metaApi } from '@/api/overviews'
import { ticketApi, STATE_ID_TO_KEY, PRIORITY_ID_TO_KEY } from '@/api/tickets'
import TicketFilters from '@/components/ticket/TicketFilters.vue'
import TicketTable from '@/components/ticket/TicketTable.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TicketFilters as Filters, Ticket, TicketState, TicketPriority, Group, User, ExportColumn, BatchUpdatePayload } from '@/types'

const router = useRouter()
const ticketStore = useTicketStore()
const authStore = useAuthStore()
const currentPage = ref(1)

// 快捷分类标签
const activeTab = ref('all')
const quickTabs = computed(() => [
  { key: 'all', label: '全部' },
  { key: 'mine', label: '我的待办' },
  { key: 'pending', label: '待受理' },
  { key: 'archived', label: '已归档' },
  { key: 'on_hold', label: '暂缓处理' },
  { key: 'escalated', label: '升级/重投' },
  { key: 'overdue', label: '已超时' },
])

function onQuickTab(key: string) {
  activeTab.value = key
  currentPage.value = 1
  // 根据标签设置筛选条件
  const filters: any = {}
  const me = authStore.user as any
  switch (key) {
    case 'all':
      break
    case 'mine':
      filters.owner_id = me?.id
      break
    case 'pending':
      filters.state_id = 1  // 待受理
      break
    case 'archived':
      filters.state_id = 5  // 已归档
      break
    case 'on_hold':
      filters.state_id = 4  // 暂缓处理
      break
    case 'escalated':
      filters.is_duplicate = true
      break
    case 'overdue':
      filters.is_overdue = true
      break
  }
  ticketStore.setFilters(filters)
  ticketStore.fetchTickets(1)
}

const selectedTickets = ref<Ticket[]>([])
const states = ref<TicketState[]>([])
const priorities = ref<TicketPriority[]>([])
const groups = ref<Group[]>([])
const agents = ref<User[]>([])

// 批量操作
const batchField = ref<keyof BatchUpdatePayload | ''>('')
const batchValue = ref<number | null | ''>('')
const batchUpdating = ref(false)

// 导出
const exportDialogVisible = ref(false)
const exporting = ref(false)
const selectedColumns = ref<string[]>([])

const columnGroups: Array<{ key: 'base' | 'customer' | 'category' | 'workflow'; label: string; columns: ExportColumn[] }> = [
  {
    key: 'base', label: '基础核心',
    columns: [
      { key: 'number', label: '工单编号', group: 'base' },
      { key: 'state', label: '当前状态', group: 'base' },
      { key: 'priority', label: '优先级', group: 'base' },
      { key: 'channel', label: '工单来源', group: 'base' },
      { key: 'created_at', label: '创建时间', group: 'base' },
      { key: 'close_at', label: '结案时间', group: 'base' },
      { key: 'close_duration', label: '关闭时长', group: 'base' },
    ],
  },
  {
    key: 'customer', label: '用户信息',
    columns: [
      { key: 'customer_name', label: '用户姓名', group: 'customer' },
      { key: 'customer_phone', label: '联系手机号', group: 'customer' },
      { key: 'customer_type', label: '用户类型', group: 'customer' },
      { key: 'device_sn', label: '设备 SN', group: 'customer' },
      { key: 'region', label: '所属区域', group: 'customer' },
    ],
  },
  {
    key: 'category', label: '分类标签',
    columns: [
      { key: 'category_l1', label: '一级问题分类', group: 'category' },
      { key: 'category_l2', label: '二级细分标签', group: 'category' },
      { key: 'symptom', label: '故障现象', group: 'category' },
      { key: 'is_duplicate', label: '是否重复', group: 'category' },
    ],
  },
  {
    key: 'workflow', label: '处理流转',
    columns: [
      { key: 'first_owner', label: '首次受理坐席', group: 'workflow' },
      { key: 'skill_group', label: '对接部门', group: 'workflow' },
      { key: 'sla_breached', label: 'SLA 达标', group: 'workflow' },
      { key: 'resolved', label: '是否解决', group: 'workflow' },
      { key: 'resolution', label: '处理备注/解决方案', group: 'workflow' },
    ],
  },
]

onMounted(async () => {
  await ticketStore.fetchTickets()
  const [s, p, g, a] = await Promise.all([
    metaApi.getStates(), metaApi.getPriorities(), metaApi.getGroups(), metaApi.getAgents(),
  ])
  states.value = s; priorities.value = p; groups.value = g; agents.value = a
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

function onSelectionChange(rows: Ticket[]) {
  selectedTickets.value = rows
}

function clearSelection() {
  selectedTickets.value = []
  batchField.value = ''
  batchValue.value = ''
}

function onBatchFieldChange() {
  batchValue.value = ''
}

async function onBatchApply() {
  if (!batchField.value) return
  try {
    await ElMessageBox.confirm(
      `确定要批量修改 ${selectedTickets.value.length} 条工单吗？`,
      '确认批量操作',
      { type: 'warning' }
    )
  } catch { return }

  batchUpdating.value = true
  try {
    // 批量字段映射到后端 TicketUpdate（字符串/数字）并包进 updates
    const rawValue = batchValue.value === '' ? null : batchValue.value
    const updates: Record<string, any> = {}
    if (batchField.value === 'state_id') {
      updates.state = STATE_ID_TO_KEY[rawValue as number]
    } else if (batchField.value === 'priority_id') {
      updates.priority = PRIORITY_ID_TO_KEY[rawValue as number]
    } else if (batchField.value === 'owner_id') {
      updates.owner_id = rawValue
    } else if (batchField.value === 'group_id') {
      updates.group_id = rawValue
    }
    const res = await ticketApi.batchUpdate({
      ticket_ids: selectedTickets.value.map(t => t.id),
      updates,
    } as any)
    ElMessage.success(`已更新 ${res.updated} 条工单`)
    clearSelection()
    await ticketStore.fetchTickets(currentPage.value)
  } catch {
    ElMessage.error('批量更新失败')
  } finally {
    batchUpdating.value = false
  }
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
    a.download = `tickets_${Date.now()}.csv`
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

/* 批量工具栏 */
.batch-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  background: rgba(99, 91, 255, 0.06);
  border: 1px solid rgba(99, 91, 255, 0.20);
  border-radius: var(--radius-md);
  margin-bottom: 12px;
}
.batch-info { display: flex; align-items: center; gap: 8px; }
.batch-count { font-size: 13px; font-weight: 600; color: var(--color-primary); }
.batch-actions { display: flex; gap: 8px; align-items: center; }

.batch-bar-enter-active, .batch-bar-leave-active {
  transition: all 0.25s var(--ease-out);
}
.batch-bar-enter-from, .batch-bar-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

.list-card { border: 1px solid var(--color-border-light); }
.list-card :deep(.el-card__body) { padding: 0; }

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
</style>
