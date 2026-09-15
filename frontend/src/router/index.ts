import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/views/LoginView.vue'),
    meta: { layout: 'auth', public: true },
  },
  {
    path: '/',
    redirect: '/dashboard',
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: () => import('@/views/DashboardView.vue'),
    meta: { title: '总览' },
  },
  {
    path: '/report',
    name: 'Report',
    component: () => import('@/views/PocTicketListView.vue'),
    meta: { title: '质量跟踪', requiresAgent: true },
  },
  {
    path: '/tickets',
    name: 'TicketList',
    component: () => import('@/views/PocTicketListView.vue'),
    meta: { title: 'POC 问题' },
  },
  {
    path: '/tickets/new',
    name: 'TicketCreate',
    component: () => import('@/views/PocTicketCreateView.vue'),
    meta: { title: '新建 POC 问题' },
  },
  {
    path: '/tickets/drafts',
    name: 'TicketDrafts',
    component: () => import('@/views/PocTicketDraftsView.vue'),
    meta: { title: '我的草稿' },
  },
  {
    path: '/tickets/:id',
    name: 'TicketDetail',
    component: () => import('@/views/PocTicketDetailView.vue'),
    meta: { title: 'POC 问题详情' },
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('@/views/PocTicketListView.vue'),
    meta: { title: '搜索' },
  },
  {
    path: '/admin',
    meta: { requiresAdmin: true },
    children: [
      { path: 'users', name: 'AdminUsers', component: () => import('@/views/admin/PocUsersView.vue'), meta: { title: '用户管理' } },
      { path: 'groups', name: 'AdminGroups', component: () => import('@/views/admin/PocSubsystemsView.vue'), meta: { title: '分系统管理' } },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.meta.public) return true

  if (!auth.isLoggedIn) {
    return { name: 'Login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'TicketList' }
  }

  // POC 跟踪报表仅质量、领导和系统管理员可访问
  if (to.meta.requiresAgent && !auth.canViewReport) {
    return { name: 'TicketList' }
  }

  // 我的草稿 / 新建问题仅售前和系统管理员可访问
  if ((to.path === '/tickets/new' || to.path === '/tickets/drafts') && !auth.canCreateTicket) {
    return { name: 'TicketList' }
  }

  return true
})

export default router
