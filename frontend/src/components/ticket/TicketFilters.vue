<template>
  <div class="filters-bar">
    <div class="filter-items">
      <el-select
        v-model="local.category_l2_id"
        placeholder="二级分类"
        clearable
        filterable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option
          v-for="c in l2Categories"
          :key="c.id"
          :label="`${c.parent_name ? c.parent_name + ' / ' : ''}${c.name}`"
          :value="c.id"
        />
      </el-select>
      <el-select
        v-model="local.priority_id"
        placeholder="优先级"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option v-for="p in priorities" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select
        v-model="local.creator_id"
        placeholder="创建人"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option v-for="c in creators" :key="c.id" :label="c.firstname" :value="c.id" />
      </el-select>
      <el-input
        v-model="local.keyword"
        placeholder="搜索工单号/客户/电话/SN/问题..."
        clearable
        @keyup.enter="emit('update:modelValue', local)"
        @clear="emit('update:modelValue', local)"
        class="filter-search"
      >
        <template #prefix>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity: 0.4">
            <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
        </template>
      </el-input>
      <div class="filter-spacer" />
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        range-separator="至"
        start-placeholder="开始"
        end-placeholder="结束"
        value-format="YYYY-MM-DD"
        placeholder="创建时间"
        class="filter-date"
        @change="onDateChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed, onMounted, ref, watch } from 'vue'
import { metaApi } from '@/api/overviews'
import type { TicketFilters, TicketPriority, User, TicketCategory } from '@/types'

interface L2CategoryOption {
  id: number
  name: string
  parent_name: string
}

const props = defineProps<{ modelValue: TicketFilters }>()
const emit = defineEmits<{ 'update:modelValue': [value: TicketFilters] }>()

const local = reactive<TicketFilters>({})
const dateRange = ref<[string, string] | null>(null)
const priorities = ref<TicketPriority[]>([])
const creators = ref<User[]>([])
const categories = ref<TicketCategory[]>([])

/** 二级分类下拉项：所有 L2（标注"一级 / 二级"）+ 没有 L2 子项的孤立 L1（仅显示一级名） */
const l2Categories = computed<L2CategoryOption[]>(() => {
  const active = categories.value.filter(c => c.active)
  const nameById = new Map<number, string>(active.map(c => [c.id, c.name]))
  const l1List = active.filter(c => c.parent_id == null)
  const l2List = active.filter(c => c.parent_id != null)
  // 已被 L2 引用的 L1 不再单独列出，避免和子项重复
  const l1WithChildren = new Set(l2List.map(c => c.parent_id!))
  const orphanL1 = l1List
    .filter(c => !l1WithChildren.has(c.id))
    .map(c => ({ id: c.id, name: c.name, parent_name: '' }))
  const l2 = l2List.map(c => ({
    id: c.id,
    name: c.name,
    parent_name: nameById.get(c.parent_id!) || '',
  }))
  return [...orphanL1, ...l2].sort((a, b) => {
    const ka = a.parent_name + a.name
    const kb = b.parent_name + b.name
    return ka.localeCompare(kb, 'zh-Hans-CN')
  })
})

/** 日期区间变化：拆成 date_from / date_to 写回 local */
function onDateChange(val: [string, string] | null) {
  local.date_from = val?.[0] || null
  local.date_to = val?.[1] || null
  emit('update:modelValue', local)
}

// 外部 modelValue 变化时同步到 local（如点快捷标签重置筛选）
watch(() => props.modelValue, (v) => {
  // 先清空 local 再重新赋值，确保外部删除的字段不会残留
  Object.keys(local).forEach(key => delete (local as any)[key])
  Object.assign(local, v)
  // 同步日期范围
  if (local.date_from && local.date_to) {
    dateRange.value = [local.date_from, local.date_to]
  } else {
    dateRange.value = null
  }
}, { immediate: true, deep: true })

onMounted(async () => {
  const [p, c, cats] = await Promise.all([
    metaApi.getPriorities(), metaApi.getCreators(), metaApi.getCategories(),
  ])
  priorities.value = p
  creators.value = c
  categories.value = cats
})
</script>

<style scoped>
.filters-bar {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  margin-bottom: 16px;
}

.filter-items {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
}

.filter-select {
  width: 140px;
}
.filter-date {
  width: 200px;
}
.filter-spacer {
  flex: 1;
  min-width: 0;
}
.filter-select :deep(.el-input__wrapper) {
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  box-shadow: none;
}
.filter-select :deep(.el-input__wrapper:hover) {
  border-color: var(--color-border);
}

.filter-search {
  width: 140px;
}
.filter-search :deep(.el-input__wrapper) {
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  box-shadow: none;
}
.filter-search :deep(.el-input__wrapper:hover) {
  border-color: var(--color-border);
}
</style>
