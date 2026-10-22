<template>
  <div class="sla-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">SLA 策略</h2>
        <p class="page-subtitle">按一级分类配置解决时限：投诉三级、业务保障 P1～P4，其余分类单档；未配置的档位不计时。</p>
      </div>
      <el-button type="primary" @click="openCreate">新增策略</el-button>
    </div>

    <el-card shadow="never" class="list-card" v-loading="loading">
      <el-table :data="policies" :key="tableKey" row-key="id">
        <el-table-column label="一级分类" width="190">
          <template #default="{ row }">
            <span>{{ row.category_name || `分类 #${row.category_id}` }}</span>
          </template>
        </el-table-column>
        <el-table-column label="时限档位" width="200">
          <template #default="{ row }">
            <span v-if="row.category_name === '业务保障'" class="priority-dot" :style="{ background: priorityColor(row.variant) }" />
            {{ variantLabel(row.variant) }}
          </template>
        </el-table-column>
        <el-table-column label="解决时限（小时）">
          <template #default="{ row }">{{ formatHours(row.solution_minutes) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button text size="small" @click="openEdit(row)">编辑</el-button>
            <el-button text size="small" type="danger" @click="onRemove(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="editing ? '编辑策略' : '新增策略'" width="500px" align-center append-to-body class="ticket-dark-dialog sla-dialog" :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">
        <el-form-item label="一级分类" prop="category_id">
          <el-select v-model="form.category_id" popper-class="ticket-dark-select-popper" style="width: 100%" :disabled="editing" placeholder="请选择一级分类" @change="onCategoryChange">
            <el-option v-for="category in rootCategories" :key="category.id" :label="category.name" :value="category.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="时限档位" prop="variant">
          <el-select v-model="form.variant" popper-class="ticket-dark-select-popper" style="width: 100%" :disabled="editing" placeholder="请选择档位">
            <el-option v-for="option in variantOptions" :key="option.value" :label="option.label" :value="option.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="解决时限(小时)" prop="solution_hours">
          <el-input-number v-model="form.solution_hours" :min="0.02" :max="720" :step="0.5" :precision="2" style="width: 100%" />
        </el-form-item>
      </el-form>
      <p class="sla-hint">从正式建单开始；最终处理结果返回客服时结束。客服退回后开启新一轮。线索与即时办结不计 SLA。</p>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { slaApi, type SLAPolicyItem, type SLAPolicyPayload } from '@/api/sla'
import { metaApi } from '@/api/overviews'
import type { TicketCategory } from '@/types'

const loading = ref(false)
const saving = ref(false)
const policies = ref<SLAPolicyItem[]>([])
const rootCategories = ref<TicketCategory[]>([])
const tableKey = ref(0)

const dialogVisible = ref(false)
const editing = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const priorities = [
  { value: 'p1_urgent', label: 'P1 特别重大事件' },
  { value: 'p2_high', label: 'P2 重大事件' },
  { value: 'p3_normal', label: 'P3 较大事件' },
  { value: 'p4_enterprise', label: 'P4 一般事件' },
]
const PRIORITY_COLOR: Record<string, string> = {
  p1_urgent: '#F56C6C', p2_high: '#E6A23C', p3_normal: '#409EFF', p4_enterprise: '#67C23A',
}
function priorityLabel(v: string) { return priorities.find(p => p.value === v)?.label || v }
function priorityColor(v: string) { return PRIORITY_COLOR[v] || '#909399' }
function variantLabel(v: string) { return v === 'default' ? '单档' : priorityLabel(v) === v ? `${v}投诉` : priorityLabel(v) }

const form = reactive({
  category_id: null as number | null,
  variant: '',
  solution_hours: 8,
})
const rules: FormRules = {
  category_id: [{ required: true, message: '请选择一级分类', trigger: 'change' }],
  variant: [{ required: true, message: '请选择时限档位', trigger: 'change' }],
  solution_hours: [{ required: true, message: '请输入', trigger: 'blur' }],
}
const selectedCategory = computed(() => rootCategories.value.find(category => category.id === form.category_id))
const variantOptions = computed(() => selectedCategory.value?.name === '业务保障' ? priorities
  : ['投诉', '服务投诉', '投诉类'].includes(selectedCategory.value?.name || '')
    ? [{ value: '一般', label: '一般投诉' }, { value: '重要', label: '重要投诉' }, { value: '重大', label: '重大投诉' }]
    : [{ value: 'default', label: '单档' }])
function onCategoryChange() { form.variant = variantOptions.value[0]?.value || '' }

function formatHours(minutes: number): string { return Number((minutes / 60).toFixed(2)).toString() }

async function load() {
  loading.value = true
  try {
    const list = await slaApi.list()
    policies.value = []
    await nextTick()
    policies.value = list
    tableKey.value++
  } finally { loading.value = false }
}

function openCreate() {
  editing.value = false
  editingId.value = null
  form.category_id = null
  form.variant = ''
  form.solution_hours = 8
  dialogVisible.value = true
}
function openEdit(row: SLAPolicyItem) {
  editing.value = true
  editingId.value = row.id
  form.category_id = row.category_id
  form.variant = row.variant
  form.solution_hours = row.solution_minutes / 60
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload: SLAPolicyPayload = {
      category_id: form.category_id!,
      variant: form.variant,
      solution_minutes: Math.round(form.solution_hours * 60),
    }
    if (editing.value && editingId.value) {
      await slaApi.update(editingId.value, payload)
      ElMessage.success('已更新')
      // 本地立即更新对应行（不依赖 load，避免缓存返回旧数据）
      const idx = policies.value.findIndex(p => p.id === editingId.value)
      if (idx >= 0) {
        const categoryName = rootCategories.value.find(category => category.id === payload.category_id)?.name || null
        policies.value[idx] = {
          ...policies.value[idx],
          category_id: payload.category_id,
          category_name: categoryName,
          variant: payload.variant,
          solution_minutes: payload.solution_minutes,
        }
        tableKey.value++
      }
    } else {
      await slaApi.create(payload)
      ElMessage.success('已创建')
      await load()
    }
    dialogVisible.value = false
  } catch (e: any) {
    const msg = e?.response?.data?.error?.message || e?.response?.data?.detail
    if (msg) ElMessage.error(msg)
  } finally { saving.value = false }
}

async function onRemove(row: SLAPolicyItem) {
  try {
    await ElMessageBox.confirm('确定删除该解决时限策略吗？删除后新建及新一轮工单将不再匹配此档位；已有轮次保持原截止时间。', '删除策略', { type: 'warning', customClass: 'ticket-dark-dialog' })
  } catch { return }
  await slaApi.remove(row.id)
  ElMessage.success('已删除')
  // 本地立即移除
  policies.value = policies.value.filter(p => p.id !== row.id)
  tableKey.value++
}

onMounted(async () => {
  rootCategories.value = (await metaApi.getCategories()).filter(category => category.parent_id == null)
  await load()
})
</script>

<style scoped>
.page-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-text-tertiary); margin-top: 4px; }
.list-card { border-radius: var(--radius-lg); }
.priority-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; vertical-align: middle; }
.sla-view { min-width: 0; color: #eaf4ff; }
.page-header { align-items: center; margin: 4px 0 20px; }
.page-title { color: #f1f8ff; font-size: 28px; text-shadow: 0 0 17px #40aaff38; }
.page-header :deep(.el-button) { min-width: 126px; height: 40px; font-weight: 600; }
.list-card { position: relative; overflow: hidden; border: 1px solid #0d8cda; border-radius: 6px; background: #041b37; box-shadow: 0 0 19px #006fca4d; }
.list-card::before, .list-card::after { content: ''; position: absolute; z-index: 2; width: 55px; height: 2px; background: #4bd5ff; box-shadow: 0 0 11px #4bd5ff; pointer-events: none; }
.list-card::before { top: 0; left: 13px; }
.list-card::after { bottom: 0; right: 13px; }
.list-card :deep(.el-card__body) { padding: 0; }
.list-card :deep(.el-table) { --el-table-bg-color: #041b37; --el-table-tr-bg-color: #041b37; --el-table-header-bg-color: #0a315a; --el-table-row-hover-bg-color: #0b345b; --el-table-border-color: #0c3c65; --el-table-text-color: #c4d8f0; --el-table-header-text-color: #c9e2fb; background: #041b37; }
.list-card :deep(.el-table__header th.el-table__cell) { height: 46px; background: linear-gradient(180deg, #0c4278, #072c52); color: #c9e2fb; border-bottom-color: #1b6193; font-size: 12px; font-weight: 600; }
.list-card :deep(.el-table__body td.el-table__cell) { height: 48px; border-bottom-color: #0c385f; color: #c4d8f0; }
.list-card :deep(.el-table__body tr:nth-child(odd) > td.el-table__cell) { background: #031a34; }
.list-card :deep(.el-table__body tr:nth-child(even) > td.el-table__cell) { background: #051f3c; }
.list-card :deep(.el-table__body tr:hover > td.el-table__cell) { background: #0b345b; }
.list-card :deep(.el-table__empty-block) { background: #041b37; }
.list-card :deep(.el-table__empty-text) { color: #91afcb; }
.list-card :deep(.el-tag--info) { border-color: #3b617e; border-radius: 4px; background: #183249; color: #acc7dc; }
.list-card :deep(.el-button.is-text) { color: #76caff; }
.list-card :deep(.el-button--danger.is-text) { color: #ffa8b9; }
.priority-dot { box-shadow: 0 0 7px currentColor; }
@media (max-width: 700px) { .page-title { font-size: 24px; } .page-header :deep(.el-button) { min-width: 0; } }
</style>
