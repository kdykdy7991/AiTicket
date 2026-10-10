<template>
  <AuthLayout v-if="route.meta.layout === 'auth'">
    <RouterView />
  </AuthLayout>
  <DefaultLayout v-else>
    <AgentAssistantView v-if="assistantStarted" v-show="route.name === 'AgentAssistant'" />
    <RouterView v-if="route.name !== 'AgentAssistant'" />
  </DefaultLayout>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import AuthLayout from '@/layouts/AuthLayout.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'
import AgentAssistantView from '@/views/AgentAssistantView.vue'

const route = useRoute()
const assistantStarted = ref(false)
watch(() => route.name, (name) => {
  if (route.meta.layout === 'auth') assistantStarted.value = false
  else if (name === 'AgentAssistant') assistantStarted.value = true
}, { immediate: true })
</script>
