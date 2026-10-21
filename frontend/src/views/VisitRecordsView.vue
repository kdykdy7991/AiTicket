<template>
  <div class="visits-page">
    <div class="page-head">
      <div><h1>来访记录（非工单）</h1></div>
      <div class="head-actions">
        <el-button @click="exportCsv">导出汇总</el-button>
        <el-button v-if="canEdit" type="primary" @click="openCreate">新增来访记录</el-button>
      </div>
    </div>

    <div class="filters">
      <el-input v-model="keyword" clearable placeholder="搜索号码、姓名或分类" @keyup.enter="load(1)" @clear="load(1)" />
      <el-select v-model="channel" placeholder="全部渠道" clearable @change="load(1)">
        <el-option label="400客服热线" value="400客服热线" />
        <el-option label="在线客服" value="在线客服" />
      </el-select>
      <el-button @click="load(1)">查询</el-button>
    </div>

    <div class="table-card">
      <el-table v-loading="loading" :data="records" stripe>
        <el-table-column prop="contact_at" label="联系时间" min-width="155">
          <template #default="{ row }">{{ formatTime(row.contact_at) }}</template>
        </el-table-column>
        <el-table-column prop="channel" label="渠道" min-width="120" />
        <el-table-column prop="contact_number" label="联系号码" min-width="135" />
        <el-table-column prop="customer_name" label="姓名" min-width="88">
          <template #default="{ row }">{{ row.customer_name || '—' }}</template>
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

    <el-dialog v-model="dialogVisible" :title="selected?.id ? (editing ? '编辑来访记录' : '来访记录详情') : '新增来访记录'" width="820px" class="visit-dialog" destroy-on-close>
      <div v-if="selected?.source_sheet" class="source-note">原始来源：{{ selected.source_sheet }} · 第 {{ selected.source_row }} 行</div>
      <div v-if="!editing && selected" class="detail-grid">
        <div v-for="item in detailItems" :key="item.label" :class="{ wide: item.wide }">
          <span>{{ item.label }}</span><p>{{ item.value }}</p>
        </div>
      </div>
      <el-form v-else label-position="top" class="visit-form">
        <el-form-item label="联系时间" required><el-input v-model="form.contact_at" type="datetime-local" :disabled="!editing" /></el-form-item>
        <el-form-item label="渠道" required><el-select v-model="form.channel" :disabled="!editing"><el-option label="400客服热线" value="400客服热线" /><el-option label="在线客服" value="在线客服" /></el-select></el-form-item>
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
  { key: 'source_order', label: '原表序号' },
  { key: 'customer_source', label: '客户来源' },
  { key: 'gender', label: '称谓' },
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
    { label: '姓名', value: record.customer_name },
    { label: '接待客服', value: record.service_agent },
    { label: '一级分类', value: record.category_l1 },
    { label: '二级分类', value: record.category_l2 },
  ]
  const extra = extraFields.map(field => ({ label: field.label, value: record.fields[field.key], wide: field.multiline }))
  return [...base, ...extra].filter(item => item.value)
})

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
  form.customer_name = record?.customer_name || ''
  form.service_agent = record?.service_agent || ''
  form.registered_ticket = record?.registered_ticket == null ? '' : String(record.registered_ticket)
  form.category_l1 = record?.category_l1 || ''
  form.category_l2 = record?.category_l2 || ''
  form.fields = { ...(record?.fields || {}) }
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
.visits-page{padding:24px;min-width:0;background:#f6f8fb;min-height:100%;color:#17243b}.page-head{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:20px}.head-actions{display:flex;gap:8px}.page-head h1{font-size:25px;margin:0 0 5px}.filters{display:flex;gap:10px;flex-wrap:wrap;background:#fff;border:1px solid #e7ecf3;border-radius:10px;padding:14px;margin-bottom:14px}.filters .el-input{width:260px}.filters .el-select{width:180px}.table-card{background:#fff;border:1px solid #e7ecf3;border-radius:10px;padding:10px 14px}.pager{display:flex;justify-content:flex-end;padding:15px 3px 4px}.source-note{font-size:12px;color:#718098;background:#f4f7fb;padding:9px 12px;border-radius:6px;margin-bottom:14px}.visit-form,.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 18px;max-height:65vh;overflow:auto;padding-right:5px}.visit-form :deep(.el-form-item){min-width:0}.visit-form .wide,.detail-grid .wide{grid-column:1/-1}.visit-form :deep(.el-select){width:100%}.detail-grid{gap:14px 18px}.detail-grid>div{padding:10px 12px;background:#f7f9fc;border-radius:6px;min-width:0}.detail-grid span{font-size:12px;color:#8793a4}.detail-grid p{margin:5px 0 0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:14px}@media(max-width:760px){.visits-page{padding:14px}.visit-form,.detail-grid{grid-template-columns:1fr}}
</style>
