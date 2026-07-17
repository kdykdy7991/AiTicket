<template>
  <div class="categories-view">
    <div class="page-header">
      <div>
        <h2 class="page-title">问题分类管理</h2>
        <p class="page-subtitle">维护工单的一级分类和二级细分，创建页下拉选项会实时同步</p>
      </div>
    </div>

    <div class="columns">
      <!-- 一级分类 -->
      <el-card shadow="never" class="section-card l1-card">
        <template #header>
          <div class="section-header">
            <h3 class="section-title">一级分类</h3>
            <el-button type="primary" size="small" @click="openCreate(1)">新建一级分类</el-button>
          </div>
        </template>
        <el-table
          :data="l1Categories"
          :key="l1Key"
          v-loading="loading"
          stripe
          highlight-current-row
          @row-click="selectL1"
        >
          <el-table-column label="名称" prop="name" />
          <el-table-column label="排序" prop="sort_order" width="80" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_active !== false" size="small" type="success">启用</el-tag>
              <el-tag v-else size="small" type="info">禁用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click.stop="openEdit(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click.stop="onRemove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>

      <!-- 二级分类 -->
      <el-card shadow="never" class="section-card l2-card">
        <template #header>
          <div class="section-header">
            <div>
              <h3 class="section-title">二级细分</h3>
              <span v-if="selectedL1" class="section-hint">隶属于「{{ selectedL1.name }}」</span>
              <span v-else class="section-hint">请先选择左侧一级分类</span>
            </div>
            <el-button type="primary" size="small" :disabled="!selectedL1" @click="openCreate(2)">新建二级细分</el-button>
          </div>
        </template>
        <el-table :data="l2Categories" :key="l2Key" v-loading="loading" stripe empty-text="暂无二级细分">
          <el-table-column label="名称" prop="name" />
          <el-table-column label="排序" prop="sort_order" width="80" />
          <el-table-column label="状态" width="80">
            <template #default="{ row }">
              <el-tag v-if="row.is_active !== false" size="small" type="success">启用</el-tag>
              <el-tag v-else size="small" type="info">禁用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="150" fixed="right">
            <template #default="{ row }">
              <el-button text size="small" @click="openEdit(row)">编辑</el-button>
              <el-button text size="small" type="danger" @click="onRemove(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>

    <!-- 新建/编辑对话框 -->
    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="480px" align-center :close-on-click-modal="false">
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="分类名称" prop="name">
          <el-input v-model="form.name" placeholder="如：设备故障" />
        </el-form-item>
        <el-form-item v-if="formLevel === 2" label="所属一级" prop="parent_id">
          <el-select v-model="form.parent_id" placeholder="请选择一级分类" style="width: 100%" :disabled="editing">
            <el-option
              v-for="c in l1Categories"
              :key="c.id"
              :label="c.name"
              :value="c.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="排序号" prop="sort_order">
          <el-input-number v-model="form.sort_order" :min="0" :step="1" style="width: 100%" />
        </el-form-item>
        <el-form-item label="启用状态" prop="is_active">
          <el-switch v-model="form.is_active" active-text="启用" inactive-text="禁用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="onSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance, type FormRules } from 'element-plus'
import { categoryApi, type CategoryNode } from '@/api/categories'

const loading = ref(false)
const saving = ref(false)
const categories = ref<CategoryNode[]>([])
const l1Key = ref(0)
const l2Key = ref(0)

const selectedL1 = ref<CategoryNode | null>(null)

const l1Categories = computed(() => categories.value.filter(c => c.level === 1).sort((a, b) => a.sort_order - b.sort_order))
const l2Categories = computed(() => {
  if (!selectedL1.value) return []
  return (selectedL1.value.children || []).slice().sort((a, b) => a.sort_order - b.sort_order)
})

const dialogVisible = ref(false)
const formLevel = ref<1 | 2>(1)
const editing = ref(false)
const editingId = ref<number | null>(null)
const formRef = ref<FormInstance>()

const form = reactive({
  name: '',
  parent_id: null as number | null,
  sort_order: 0,
  is_active: true,
})

const rules: FormRules = {
  name: [{ required: true, message: '请输入分类名称', trigger: 'blur' }],
  parent_id: [{ required: true, message: '请选择所属一级分类', trigger: 'change' }],
}

const dialogTitle = computed(() => {
  const levelLabel = formLevel.value === 1 ? '一级分类' : '二级细分'
  return `${editing.value ? '编辑' : '新建'}${levelLabel}`
})

async function loadCategories() {
  loading.value = true
  try {
    categories.value = await categoryApi.list(true)
    l1Key.value++
    l2Key.value++
  } finally { loading.value = false }
}

function selectL1(row: CategoryNode) {
  selectedL1.value = row
}

function openCreate(level: 1 | 2) {
  formLevel.value = level
  editing.value = false
  editingId.value = null
  form.name = ''
  form.parent_id = level === 2 ? (selectedL1.value?.id ?? null) : null
  form.sort_order = 0
  form.is_active = true
  dialogVisible.value = true
}

function openEdit(row: CategoryNode) {
  formLevel.value = row.level as 1 | 2
  editing.value = true
  editingId.value = row.id
  form.name = row.name
  form.parent_id = row.parent_id
  form.sort_order = row.sort_order ?? 0
  form.is_active = row.is_active !== false
  dialogVisible.value = true
}

async function onSubmit() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const payload = {
      name: form.name,
      sort_order: form.sort_order,
      is_active: form.is_active,
    }
    if (editing.value && editingId.value) {
      await categoryApi.update(editingId.value, payload)
      ElMessage.success('已更新')
    } else {
      await categoryApi.create({
        ...payload,
        parent_id: formLevel.value === 2 ? form.parent_id : null,
      })
      ElMessage.success('已创建')
    }
    dialogVisible.value = false
    await loadCategories()
  } finally { saving.value = false }
}

async function onRemove(row: CategoryNode) {
  const levelLabel = row.level === 1 ? '一级分类' : '二级细分'
  try {
    await ElMessageBox.confirm(`确定要删除${levelLabel}「${row.name}」吗？有子分类或关联工单时无法删除。`, `删除${levelLabel}`, { type: 'warning' })
  } catch { return }
  try {
    await categoryApi.remove(row.id)
    ElMessage.success('已删除')
    if (selectedL1.value?.id === row.id) {
      selectedL1.value = null
    }
    await loadCategories()
  } catch (e: any) {
    const msg = e?.response?.data?.error?.message || e?.response?.data?.detail
    if (msg) ElMessage.error(msg)
  }
}

onMounted(() => {
  loadCategories()
})
</script>

<style scoped>
.page-header { margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.page-subtitle { font-size: 13px; color: var(--color-text-tertiary); margin-top: 4px; }
.columns { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
.section-card { border-radius: var(--radius-lg); }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.section-title { font-size: 15px; font-weight: 600; margin: 0; }
.section-hint { font-size: 12px; color: var(--color-text-tertiary); }
@media (max-width: 900px) {
  .columns { grid-template-columns: 1fr; }
}
</style>
