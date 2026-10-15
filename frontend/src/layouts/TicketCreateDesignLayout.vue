<template>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand"><span class="brand-mark">◩</span><strong>星联科技</strong></div>
      <nav aria-label="主导航">
        <router-link to="/tickets" class="nav-item"><span>⌂</span>首页</router-link>
        <router-link to="/admin/users" class="nav-item"><span>♙</span>客户管理 <b>⌄</b></router-link>
        <div class="nav-item nav-parent"><span>▣</span>工单管理 <b>⌃</b></div>
        <div class="subnav"><router-link to="/tickets">工单列表</router-link><router-link to="/tickets/new" class="active">创建工单</router-link><router-link to="/tickets/drafts">我的工单</router-link><router-link to="/report">工单统计</router-link></div>
        <router-link to="/knowledge" class="nav-item"><span>▤</span>知识库 <b>⌄</b></router-link>
        <router-link to="/tickets" class="nav-item"><span>▧</span>设备管理 <b>⌄</b></router-link>
        <router-link to="/tickets" class="nav-item"><span>▣</span>业务管理 <b>⌄</b></router-link>
        <router-link to="/report" class="nav-item"><span>▥</span>数据报表</router-link>
        <router-link to="/admin/users" class="nav-item"><span>⚙</span>系统设置 <b>⌄</b></router-link>
      </nav>
    </aside>
    <div class="main-shell"><header class="topbar"><button class="menu" aria-label="菜单">☰</button><div class="search"><span>⌕</span><input aria-label="搜索" placeholder="搜索客户、工单、设备或其他内容..." /></div><div class="top-spacer"></div><button class="icon-button" aria-label="消息">♧<i></i></button><button class="icon-button" aria-label="帮助">ⓘ</button><div class="user"><div class="avatar">{{ userName.slice(0,1) }}</div><div><strong>{{ userName }}</strong><small>{{ groupName }}</small></div><span>⌄</span></div></header><slot /></div>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
const userName = computed(() => auth.displayName || '张晓婷')
const groupName = computed(() => auth.user?.groups?.[0]?.name || '客服一组')
</script>
<style scoped>
.shell{display:flex;min-height:100vh;background:#fff;color:#1b2940}.sidebar{width:176px;flex:none;background:#fbfcfb;border-right:1px solid #ebefed}.brand{height:54px;display:flex;align-items:center;gap:10px;padding:0 18px;border-bottom:1px solid #edf0ee;color:#172435;font-size:17px}.brand-mark{color:#087e41;font-size:28px}.sidebar nav{padding:14px 8px}.nav-item{height:46px;display:flex;align-items:center;gap:16px;padding:0 12px;border-radius:5px;color:#26344b;font-size:14px}.nav-item span{width:18px;font-size:20px;text-align:center}.nav-item b{margin-left:auto;font-weight:400}.nav-parent{background:#eaf3ec}.subnav{display:grid;gap:2px;margin:3px 0 10px}.subnav a{height:36px;display:flex;align-items:center;padding-left:44px;border-radius:5px;color:#26344b;font-size:14px}.subnav a.active{background:#dcebe0;border-left:4px solid #058145;padding-left:40px;color:#087941;font-weight:700}.nav-item:hover,.subnav a:hover{background:#e9f3eb}.main-shell{flex:1;min-width:0}.topbar{height:54px;display:flex;align-items:center;gap:18px;padding:0 18px;border-bottom:1px solid #eef0f2}.menu,.icon-button{border:0;background:transparent;color:#27354b;cursor:pointer}.menu{font-size:18px}.search{height:36px;max-width:740px;flex:1;display:flex;align-items:center;gap:12px;padding:0 12px;border-radius:5px;background:#f1f3f5;color:#7d8798;font-size:24px}.search input{width:100%;border:0;outline:0;background:transparent;color:#28364c;font-size:13px}.top-spacer{flex:1}.icon-button{position:relative;font-size:20px}.icon-button i{position:absolute;top:1px;right:3px;width:6px;height:6px;border-radius:50%;background:#fa5039}.user{display:flex;align-items:center;gap:10px;padding-left:16px;border-left:1px solid #e9ecef;font-size:13px;white-space:nowrap}.user strong,.user small{display:block}.user small{margin-top:2px;color:#8490a2}.avatar{display:grid;place-items:center;width:33px;height:33px;border-radius:50%;background:#e7efe8;color:#247a49;font-weight:700}@media(max-width:800px){.sidebar{width:56px}.brand{padding:0 13px}.brand strong,.nav-item:not(.nav-parent),.nav-parent b,.subnav{display:none}.nav-parent{font-size:0;padding:0;justify-content:center}.nav-parent span{font-size:22px}.topbar{gap:10px}.user small{display:none}}
</style>
