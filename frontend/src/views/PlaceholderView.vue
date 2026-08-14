<script setup lang="ts">
import { useRoute } from 'vue-router'
import { RouterLink } from 'vue-router'

const route = useRoute()
const text: string = (route.meta?.ph as string) ?? '本功能开发中'
</script>

<template>
  <div class="ph-wrap">
    <div class="ph panel">
      <div class="ph-diamond"><span>◈</span></div>
      <h1 class="ph-title">开发中</h1>
      <p class="ph-text">{{ text }}</p>
      <RouterLink to="/" class="btn">← 返回作战总览</RouterLink>
    </div>
  </div>
</template>

<style scoped>
.ph-wrap {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 24px 26px;
}
.ph.panel {
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border-default);
  position: relative;
  padding: 64px 32px;
  text-align: center;
}
.ph-diamond {
  width: 48px; height: 48px;
  margin: 0 auto 20px;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid var(--color-brand-strong);
  transform: rotate(45deg);
  color: var(--color-brand);
  font-size: 18px;
}
.ph-diamond span { transform: rotate(-45deg); display: block; }
.ph-title {
  font-size: var(--font-size-hero);
  margin-bottom: var(--spacing-sm);
  letter-spacing: var(--font-tracking-wide);
}
.ph-text {
  color: var(--color-text-secondary);
  font-size: var(--font-size-md);
  margin-bottom: var(--spacing-2xl);
}
.btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 18px;
  border: 1px solid var(--color-border-strong);
  background: var(--color-bg-subtle);
  color: var(--color-text-primary);
  font-size: var(--font-size-md);
  transition: all var(--motion-duration-normal) var(--motion-easing-standard);
}
.btn:hover { border-color: var(--color-brand-strong); color: var(--color-brand); box-shadow: var(--shadow-glow-sm); }
</style>
