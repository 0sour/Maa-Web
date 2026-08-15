import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '@/views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView,
      meta: { title: '作战总览 · Maa-Web' },
    },
    {
      path: '/tasks',
      name: 'tasks',
      component: () => import('@/views/TasksView.vue'),
      meta: { title: '任务编排 · Maa-Web' },
    },
    {
      path: '/devices',
      name: 'devices',
      component: () => import('@/views/DevicesView.vue'),
      meta: { title: '设备管理 · Maa-Web' },
    },
    {
      path: '/auto-tasks',
      name: 'auto-tasks',
      component: () => import('@/views/AutoTaskView.vue'),
      meta: { title: '自动任务 · Maa-Web' },
    },
    {
      path: '/schedule',
      redirect: '/auto-tasks',
    },
    {
      path: '/toolbox',
      name: 'toolbox',
      component: () => import('@/views/PlaceholderView.vue'),
      meta: { title: '工具箱 · Maa-Web', ph: 'M5 交付：公招/干员/仓库识别 + 抽卡 + 窥屏 + 小游戏' },
    },
    {
      path: '/logs',
      name: 'logs',
      component: () => import('@/views/LogsView.vue'),
      meta: { title: '作战日志 · Maa-Web' },
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('@/views/SettingsView.vue'),
      meta: { title: '设置 · Maa-Web' },
    },
    {
      path: '/notifications',
      name: 'notifications',
      component: () => import('@/views/NotificationsView.vue'),
      meta: { title: '通知 · Maa-Web' },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: () => import('@/views/PlaceholderView.vue'),
      meta: { title: '404 · Maa-Web', ph: '页面不存在' },
    },
  ],
})

router.afterEach((to) => {
  const t = to.meta?.title
  if (typeof t === 'string') document.title = t
})

export default router
