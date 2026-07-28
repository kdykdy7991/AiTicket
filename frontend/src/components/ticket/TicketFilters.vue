<template>
  <div class="filters-bar">
    <div class="filter-items">
      <el-select
        v-model="local.state_id"
        placeholder="状态"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <!--
          7 个状态硬编码，跟后端 STATE_ID_TO_KEY (1..7) 对应：
          1=pending 待受理 / 2=open 处理中 / 3=resolved 已处理 /
          4=on_hold 暂缓处理 / 5=archived 已归档 / 6=returned 已退回 /
          7=cancelled 已撤销
        -->
        <el-option v-for="s in STATE_FILTER_OPTIONS" :key="s.id" :label="s.name" :value="s.id" />
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
        v-model="local.group_id"
        placeholder="客服组"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option v-for="g in groups" :key="g.id" :label="g.name" :value="g.id" />
      </el-select>
      <el-select
        v-model="local.owner_id"
        placeholder="负责人"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option v-for="a in agents" :key="a.id" :label="`${a.firstname}${a.lastname}`" :value="a.id" />
      </el-select>
      <el-select
        v-model="local.is_callbacked"
        placeholder="是否回访"
        clearable
        @change="emit('update:modelValue', local)"
        class="filter-select"
      >
        <el-option label="已回访" :value="true" />
        <el-option label="未回访" :value="false" />
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted, ref, watch } from 'vue'
import { metaApi } from '@/api/overviews'
import type { TicketFilters, TicketPriority, Group, User } from '@/types'

const props = defineProps<{ modelValue: TicketFilters }>()
const emit = defineEmits<{ 'update:modelValue': [value: TicketFilters] }>()

const local = reactive<TicketFilters>({})
const priorities = ref<TicketPriority[]>([])
const groups = ref<Group[]>([])
const agents = ref<User[]>([])

/** 工单状态过滤选项（硬编码 7 个，id 与后端 STATE_ID_TO_KEY 对应） */
const STATE_FILTER_OPTIONS: { id: number; name: string }[] = [
  { id: 1, name: '待受理' },
  { id: 2, name: '处理中' },
  { id: 3, name: '已处理' },
  { id: 4, name: '暂缓处理' },
  { id: 5, name: '已归档' },
  { id: 6, name: '已退回' },
  { id: 7, name: '已撤销' },
]

// 外部 modelValue 变化时同步到 local（如点快捷标签重置筛选）
watch(() => props.modelValue, (v) => {
  Object.assign(local, v)
}, { immediate: true, deep: true })

onMounted(async () => {
  const [p, g, a] = await Promise.all([
    metaApi.getPriorities(), metaApi.getGroups(), metaApi.getAgents(),
  ])
  priorities.value = p
  groups.value = g
  agents.value = a
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
.filter-select :deep(.el-input__wrapper) {
  background: var(--color-bg-subtle);
  border: 1px solid transparent;
  box-shadow: none;
}
.filter-select :deep(.el-input__wrapper:hover) {
  border-color: var(--color-border);
}

.filter-search {
  width: 180px;
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
