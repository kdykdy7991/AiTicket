<template>
  <div>
    <div class="page-header"><div><h1>我的草稿</h1><p>继续完善尚未提交审批的 POC 问题</p></div><el-button type="primary" @click="router.push('/tickets/new')">新建草稿</el-button></div>
    <el-card shadow="never">
      <el-table v-loading="loading" :data="drafts" @row-click="edit">
        <el-table-column prop="title" label="问题名称" min-width="240"><template #default="{ row }">{{ row.title || '未命名问题' }}</template></el-table-column>
        <el-table-column prop="customer_name" label="客户名称" min-width="150" />
        <el-table-column prop="product_line" label="产品线" min-width="140" />
        <el-table-column label="级别" width="110"><template #default="{ row }">{{ priorityLabel(row.priority) }}</template></el-table-column>
        <el-table-column label="更新时间" width="170"><template #default="{ row }">{{ dayjs(row.updated_at).format('YYYY-MM-DD HH:mm') }}</template></el-table-column>
        <el-table-column label="操作" width="150" fixed="right"><template #default="{ row }"><el-button text @click.stop="edit(row)">继续编辑</el-button><el-button text type="danger" @click.stop="remove(row)">删除</el-button></template></el-table-column>
      </el-table>
      <el-empty v-if="!loading && !drafts.length" description="暂无草稿" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/api'
import { pocTicketApi } from '@/api/pocTickets'
import { priorityLabel } from '@/domain/pocWorkflow'
import type { PocTicketBrief } from '@/types/poc'

const router=useRouter(), loading=ref(false), drafts=ref<PocTicketBrief[]>([])
async function load(){loading.value=true;try{const response:{data:PocTicketBrief[]}=await api.get('/tickets/drafts');drafts.value=response.data}finally{loading.value=false}}
function edit(row:PocTicketBrief){router.push({path:'/tickets/new',query:{draft_id:String(row.id)}})}
async function remove(row:PocTicketBrief){await ElMessageBox.confirm(`确定删除草稿“${row.title||'未命名问题'}”吗？`,'删除草稿',{type:'warning'});await pocTicketApi.removeDraft(row.id);ElMessage.success('草稿已删除');await load()}
onMounted(load)
</script>

<style scoped>
.page-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px}.page-header h1{margin:0;font-size:24px}.page-header p{margin:6px 0 0;color:var(--color-text-tertiary)}:deep(.el-table__row){cursor:pointer}
</style>
