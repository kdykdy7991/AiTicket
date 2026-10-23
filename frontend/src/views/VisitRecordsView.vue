<template>
  <div class="visits-page">
    <div class="page-head">
      <div><h1>来访记录</h1></div>
      <div class="head-actions">
        <el-button @click="exportCsv">导出汇总</el-button>
        <el-button v-if="canEdit" type="primary" @click="openCreate">新增来访记录</el-button>
      </div>
    </div>

    <div class="filters">
      <el-input v-model="keyword" clearable placeholder="搜索号码、姓名或分类" @keyup.enter="load(1)" @clear="load(1)" />
      <el-select v-model="channel" popper-class="ticket-dark-select-popper" placeholder="全部渠道" clearable @change="load(1)">
        <el-option label="400客服热线" value="400客服热线" />
        <el-option label="在线客服" value="在线客服" />
      </el-select>
      <el-button @click="load(1)">查询</el-button>
    </div>

    <div class="table-card">
      <el-table v-loading="loading" :data="records">
        <el-table-column prop="contact_at" label="联系时间" min-width="155">
          <template #default="{ row }">{{ formatTime(row.contact_at) }}</template>
        </el-table-column>
        <el-table-column prop="channel" label="渠道" min-width="120" />
        <el-table-column prop="contact_number" label="联系号码" min-width="135" />
        <el-table-column prop="customer_name" label="姓名" min-width="88">
          <template #default="{ row }">{{ displayCustomerName(row) || '—' }}</template>
        </el-table-column>
        <el-table-column prop="category_l1" label="一级分类" min-width="115" />
        <el-table-column prop="category_l2" label="二级分类" min-width="120" />
        <el-table-column label="客户诉求" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.fields.request || '—' }}</template>
        </el-table-column>
        <el-table-column prop="service_agent" label="接待客服" width="100" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }"><el-button link type="primary" @click="openDetail(row)">查看</el-button></template>
        </el-table-column>
      </el-table>
      <div class="pager"><el-pagination v-model:current-page="page" :page-size="20" :total="total" layout="total, prev, pager, next" @current-change="load" /></div>
    </div>

    <el-dialog v-model="dialogVisible" :title="selected?.id ? (editing ? '编辑来访记录' : '来访记录详情') : '新增来访记录'" width="820px" append-to-body class="visit-dialog ticket-dark-dialog" destroy-on-close>
      <div v-if="!editing && selected" class="detail-grid">
        <div v-for="item in detailItems" :key="item.label" :class="{ wide: item.wide }">
          <span>{{ item.label }}</span><p>{{ item.value }}</p>
        </div>
      </div>
      <el-form v-else label-position="top" class="visit-form">
        <el-form-item label="联系时间" required><el-input v-model="form.contact_at" type="datetime-local" :disabled="!editing" /></el-form-item>
        <el-form-item label="渠道" required><el-select v-model="form.channel" popper-class="ticket-dark-select-popper" :disabled="!editing"><el-option label="400客服热线" value="400客服热线" /><el-option label="在线客服" value="在线客服" /></el-select></el-form-item>
        <el-form-item label="联系号码"><el-input v-model="form.contact_number" :disabled="!editing" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="form.customer_name" :disabled="!editing" /></el-form-item>
        <el-form-item label="接待客服"><el-input v-model="form.service_agent" :disabled="!editing" /></el-form-item>
        <el-form-item label="一级分类"><el-input v-model="form.category_l1" :disabled="!editing" /></el-form-item>
        <el-form-item label="二级分类"><el-input v-model="form.category_l2" :disabled="!editing" /></el-form-item>
        <template v-for="field in extraFields" :key="field.key">
          <el-form-item :label="field.label" :class="{ wide: field.multiline }">
            <el-input v-if="field.multiline" v-model="form.fields[field.key]" type="textarea" :rows="3" :disabled="!editing" />
            <el-input v-else v-model="form.fields[field.key]" :disabled="!editing" />
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">关闭</el-button>
        <el-button v-if="canEdit && !editing" type="primary" @click="editing = true">编辑</el-button>
        <el-button v-if="editing" type="primary" :loading="saving" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { visitRecordApi, type VisitRecord, type VisitPayload } from '@/api/visitRecords'

const extraFields: Array<{ key: string; label: string; multiline?: boolean }> = [
  { key: 'customer_source', label: '客户来源' },
  { key: 'customer_type', label: '客户分类' },
  { key: 'company_name', label: '公司名称' },
  { key: 'valid_contact', label: '是否有效电话' },
  { key: 'priority', label: '事件等级' },
  { key: 'request', label: '客户诉求', multiline: true },
  { key: 'department', label: '对接部门' },
  { key: 'liaison', label: '对接人' },
  { key: 'handler', label: '处理人' },
  { key: 'handling_detail', label: '处理详情', multiline: true },
  { key: 'callback_status', label: '是否回访' },
  { key: 'callback_time', label: '回访时间' },
  { key: 'callback_detail', label: '回访详情', multiline: true },
  { key: 'returned', label: '是否退回处理' },
  { key: 'closed', label: '是否闭环' },
  { key: 'closed_at', label: '闭环时间' },
  { key: 'satisfaction', label: '满意度' },
  { key: 'notes', label: '备注', multiline: true },
]

const auth = useAuthStore()
const canEdit = computed(() => auth.isAgent)
const records = ref<VisitRecord[]>([])
const page = ref(1)
const total = ref(0)
const loading = ref(false)
const saving = ref(false)
const keyword = ref('')
const channel = ref('')
const dialogVisible = ref(false)
const selected = ref<VisitRecord | null>(null)
const editing = ref(false)
const form = reactive({ contact_at: '', channel: '400客服热线', contact_number: '', customer_name: '', service_agent: '',
  registered_ticket: '', category_l1: '', category_l2: '', fields: {} as Record<string, string> })
const detailItems = computed(() => {
  const record = selected.value
  if (!record) return []
  const base: Array<{ label: string; value: string | null | undefined; wide?: boolean }> = [
    { label: '联系时间', value: formatTime(record.contact_at) },
    { label: '渠道', value: record.channel },
    { label: '联系号码', value: record.contact_number },
    { label: '姓名', value: displayCustomerName(record) },
    { label: '接待客服', value: record.service_agent },
    { label: '一级分类', value: record.category_l1 },
    { label: '二级分类', value: record.category_l2 },
  ]
  const extra = extraFields.map(field => ({ label: field.label, value: record.fields[field.key], wide: field.multiline }))
  return [...base, ...extra].filter(item => item.value)
})

function displayCustomerName(record: VisitRecord): string {
  const name = record.customer_name?.trim() || ''
  const title = record.fields?.gender?.trim() || ''
  return name && title && !name.endsWith(title) ? `${name}${title}` : name
}

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false })
}
function localInput(value: string) {
  return new Date(value).toLocaleString('sv-SE', { timeZone: 'Asia/Shanghai', hour12: false }).replace(' ', 'T').slice(0, 16)
}
async function load(next = page.value) {
  loading.value = true
  try {
    const result = await visitRecordApi.list({ page: next, page_size: 20, keyword: keyword.value || undefined,
      channel: channel.value || undefined })
    records.value = result.data
    total.value = result.pagination.total
    page.value = next
  } finally { loading.value = false }
}
async function exportCsv() {
  const blob = await visitRecordApi.export({ keyword: keyword.value || undefined, channel: channel.value || undefined })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `来访记录汇总_${new Date().toLocaleDateString('sv-SE')}.csv`
  link.click()
  URL.revokeObjectURL(url)
}
function fill(record: VisitRecord | null) {
  form.contact_at = record ? localInput(record.contact_at) : localInput(new Date().toISOString())
  form.channel = record?.channel || '400客服热线'
  form.contact_number = record?.contact_number || ''
  form.customer_name = record ? displayCustomerName(record) : ''
  form.service_agent = record?.service_agent || ''
  form.registered_ticket = record?.registered_ticket == null ? '' : String(record.registered_ticket)
  form.category_l1 = record?.category_l1 || ''
  form.category_l2 = record?.category_l2 || ''
  form.fields = { ...(record?.fields || {}) }
  delete form.fields.gender
}
function openCreate() { selected.value = null; fill(null); editing.value = true; dialogVisible.value = true }
function openDetail(record: VisitRecord) { selected.value = record; fill(record); editing.value = false; dialogVisible.value = true }
async function save() {
  if (!form.contact_at) { ElMessage.warning('请填写联系时间'); return }
  const payload: VisitPayload = {
    contact_at: `${form.contact_at}:00+08:00`,
    channel: form.channel,
    contact_number: form.contact_number || null,
    customer_name: form.customer_name || null,
    service_agent: form.service_agent || null,
    registered_ticket: form.registered_ticket === '' ? null : form.registered_ticket === 'true',
    category_l1: form.category_l1 || null,
    category_l2: form.category_l2 || null,
    fields: { ...form.fields },
  }
  saving.value = true
  try {
    if (selected.value) await visitRecordApi.update(selected.value.id, payload)
    else await visitRecordApi.create(payload)
    ElMessage.success('保存成功')
    dialogVisible.value = false
    await load(selected.value ? page.value : 1)
  } finally { saving.value = false }
}
onMounted(() => load(1))
</script>

<style scoped>
.visits-page { min-width: 0; min-height: 100%; padding: 4px 0 24px; color: #eaf4ff; }
.page-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; margin-bottom: 20px; }
.page-head h1 { margin: 0; color: #f1f8ff; font-size: 28px; font-weight: 700; text-shadow: 0 0 17px #40aaff38; }
.head-actions { display: flex; gap: 12px; }
.head-actions :deep(.el-button) { min-width: 118px; height: 40px; font-weight: 600; }
.filters { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 13px; padding: 12px 14px; border: 1px solid #176496; border-radius: 6px; background: #06213e; box-shadow: 0 0 12px #0064ae2b; }
.filters .el-input { width: min(320px, 100%); }
.filters .el-select { width: 180px; }
.filters :deep(.el-input__wrapper), .filters :deep(.el-select__wrapper) { min-height: 38px; }
.filters :deep(.el-button) { min-width: 88px; height: 38px; border-color: #2b82bb; background: #092c4e; color: #d9eeff; }
.filters :deep(.el-button:hover) { border-color: #50bbf7; background: #0d406b; color: #fff; }
.table-card { position: relative; overflow: hidden; border: 1px solid #0d8cda; border-radius: 6px; background: #041b37; box-shadow: 0 0 19px #006fca4d; }
.table-card::before, .table-card::after { content: ''; position: absolute; z-index: 2; width: 55px; height: 2px; background: #4bd5ff; box-shadow: 0 0 11px #4bd5ff; pointer-events: none; }
.table-card::before { top: 0; left: 13px; }
.table-card::after { bottom: 0; right: 13px; }
.table-card :deep(.el-table) { --el-table-bg-color: #041b37; --el-table-tr-bg-color: #041b37; --el-table-header-bg-color: #0a315a; --el-table-row-hover-bg-color: #0b345b; --el-table-border-color: #0c3c65; --el-table-text-color: #c4d8f0; --el-table-header-text-color: #c9e2fb; --el-fill-color-lighter: #051f3c; background: #041b37; }
.table-card :deep(.el-table__header th.el-table__cell) { height: 46px; background: linear-gradient(180deg, #0c4278, #072c52); color: #c9e2fb; border-bottom-color: #1b6193; font-size: 12px; font-weight: 600; }
.table-card :deep(.el-table__body td.el-table__cell) { height: 48px; border-bottom-color: #0c385f; color: #c4d8f0; }
.table-card :deep(.el-table__body tr:nth-child(odd) > td.el-table__cell) { background: #031a34; }
.table-card :deep(.el-table__body tr:nth-child(even) > td.el-table__cell) { background: #051f3c; }
.table-card :deep(.el-table__body tr:hover > td.el-table__cell) { background: #0b345b; }
.table-card :deep(.el-table__empty-block) { min-height: 150px; background: #041b37; }
.table-card :deep(.el-table__empty-text) { color: #8daecb; }
.table-card :deep(.el-button.is-link) { color: #72caff; font-weight: 600; }
.table-card :deep(.el-button.is-link:hover) { color: #b7e6ff; }
.pager { display: flex; justify-content: flex-end; padding: 15px 18px; border-top: 1px solid #16476e; }
.pager :deep(.el-pagination) { color: #9bbbd7; }
.visit-form, .detail-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; max-height: 65vh; overflow: auto; padding-right: 5px; }
.visit-form :deep(.el-form-item) { min-width: 0; }
.visit-form .wide, .detail-grid .wide { grid-column: 1 / -1; }
.visit-form :deep(.el-select) { width: 100%; }
.detail-grid { gap: 0 18px; }
.detail-grid > div { min-width: 0; padding: 12px 2px; border-bottom: 1px solid #17466d; }
.detail-grid span { color: #90b5d3; font-size: 12px; }
.detail-grid p { margin: 5px 0 0; color: #e9f5ff; font-size: 14px; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 760px) { .page-head { align-items: flex-start; } .head-actions { flex-wrap: wrap; justify-content: flex-end; } .visit-form, .detail-grid { grid-template-columns: 1fr; } }
@media (max-width: 520px) { .page-head { flex-direction: column; } .page-head h1 { font-size: 24px; } .head-actions { width: 100%; justify-content: flex-start; } .head-actions :deep(.el-button) { flex: 1; min-width: 0; margin-left: 0; } .filters .el-input, .filters .el-select { width: 100%; } }
</style>
