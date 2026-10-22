<template>
  <el-container class="default-layout" :class="{ 'ticket-dark-theme': route.name === 'TicketList' || route.name === 'TicketDetail' || route.name === 'TicketCreate' || route.name === 'TicketCreateDesign' || route.name === 'TicketDrafts' || route.name === 'VisitRecords' || route.name === 'Report' || route.name === 'OpportunityAnalysis' || route.name === 'AdminUsers' || route.name === 'AdminGroups' || route.name === 'AdminSLA' || route.name === 'KnowledgeBase', 'ticket-detail-theme': route.name === 'TicketDetail', 'ticket-create-theme': route.name === 'TicketCreate' || route.name === 'TicketCreateDesign' }">
    <TheSidebar />
    <el-container direction="vertical">
      <TheTopbar />
      <el-main class="main-content">
        <div class="content-wrapper" :class="{ 'content-wrapper--assistant': route.name === 'AgentAssistant', 'content-wrapper--knowledge': route.name === 'KnowledgeBase', 'content-wrapper--ticket-create': route.name === 'TicketCreate' || route.name === 'TicketCreateDesign' }">
          <slot />
        </div>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { useRoute } from 'vue-router'
import TheSidebar from './TheSidebar.vue'
import TheTopbar from './TheTopbar.vue'

const route = useRoute()
</script>

<style scoped>
.default-layout {
  height: 100vh;
}
.main-content {
  background: var(--color-bg-page);
  padding: 0;
  overflow-y: auto;
  min-height: 0;
}
.content-wrapper {
  max-width: 1400px;
  margin: 0 auto;
  padding: 28px 32px;
  animation: page-in 0.35s var(--ease-out) both;
}
.content-wrapper--assistant {
  width: 100%;
  height: 100%;
  max-width: none;
  padding: 0;
  animation: none;
}
.content-wrapper--knowledge { max-width: none; padding: 0; animation: none; }
.content-wrapper--ticket-create {
  box-sizing: border-box;
  width: 100%;
  max-width: 1480px;
  margin-inline: auto;
  padding: 24px clamp(16px, 2.5vw, 36px);
}
.ticket-dark-theme .main-content {
  background: #020d20;
  border-left: 1px solid #0b65a7;
}
.ticket-dark-theme .content-wrapper {
  max-width: none;
  padding: 16px clamp(16px, 1.7vw, 30px) 24px;
}
.ticket-detail-theme .content-wrapper { max-width: 1600px; }
.ticket-create-theme .content-wrapper--ticket-create { max-width: 1600px; padding: 18px clamp(16px, 1.7vw, 30px) 30px; }
.ticket-dark-theme .content-wrapper--knowledge { padding: 0; }

@keyframes page-in {
  from { opacity: 0; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}
</style>
