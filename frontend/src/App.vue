<template>
  <AuthLayout v-if="route.meta.layout === 'auth'">
    <RouterView />
  </AuthLayout>
  <DefaultLayout v-else>
    <RouterView />
  </DefaultLayout>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import AuthLayout from '@/layouts/AuthLayout.vue'
import DefaultLayout from '@/layouts/DefaultLayout.vue'

const route = useRoute()
</script>
