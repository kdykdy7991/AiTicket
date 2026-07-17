<template>
  <el-tooltip :content="fullTime" placement="top">
    <time class="relative-time" :datetime="datetime">{{ relativeText }}</time>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import dayjs from 'dayjs'
import relativeTime from 'dayjs/plugin/relativeTime'
import 'dayjs/locale/zh-cn'

dayjs.extend(relativeTime)
dayjs.locale('zh-cn')

const props = defineProps<{ datetime: string }>()

const relativeText = computed(() => dayjs(props.datetime).fromNow())
const fullTime = computed(() => dayjs(props.datetime).format('YYYY-MM-DD HH:mm:ss'))
</script>

<style scoped>
.relative-time {
  font-size: 12.5px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
