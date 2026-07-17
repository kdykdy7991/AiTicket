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
    meta: { title: '仪表盘' },
  },
  {
    path: '/report',
    name: 'Report',
    component: () => import('@/views/ReportView.vue'),
    meta: { title: '统计报表' },
  },
  {
    path: '/tickets',
    name: 'TicketList',
    component: () => import('@/views/TicketListView.vue'),
    meta: { title: '工单列表' },
  },
  {
    path: '/tickets/new',
    name: 'TicketCreate',
    component: () => import('@/views/TicketCreateView.vue'),
    meta: { title: '新建工单' },
  },
  {
    path: '/tickets/drafts',
    name: 'TicketDrafts',
    component: () => import('@/views/TicketDraftsView.vue'),
    meta: { title: '我的草稿' },
  },
  {
    path: '/tickets/:id',
    name: 'TicketDetail',
    component: () => import('@/views/TicketDetailView.vue'),
    meta: { title: '工单详情' },
  },
  {
    path: '/search',
    name: 'Search',
    component: () => import('@/views/SearchView.vue'),
    meta: { title: '搜索' },
  },
  {
    path: '/admin',
    meta: { requiresAdmin: true },
    children: [
      { path: 'users', name: 'AdminUsers', component: () => import('@/views/admin/UsersView.vue'), meta: { title: '用户管理' } },
      { path: 'groups', name: 'AdminGroups', component: () => import('@/views/admin/GroupsView.vue'), meta: { title: '组管理' } },
      { path: 'triggers', name: 'AdminTriggers', component: () => import('@/views/admin/PlaceholderView.vue'), meta: { title: '触发器' } },
      { path: 'sla', name: 'AdminSLA', component: () => import('@/views/admin/SLAView.vue'), meta: { title: 'SLA 策略' } },
      { path: 'channels', name: 'AdminChannels', component: () => import('@/views/admin/PlaceholderView.vue'), meta: { title: '邮件渠道' } },
      { path: 'categories', name: 'AdminCategories', component: () => import('@/views/admin/CategoriesView.vue'), meta: { title: '问题分类' } },
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
    return { name: 'Dashboard' }
  }

  return true
})

export default router
