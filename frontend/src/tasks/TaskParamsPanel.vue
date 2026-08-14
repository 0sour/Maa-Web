<script setup lang="ts">
/** 任务参数面板（作战总览 / 任务编排 两页复用）——按任务类型分发到对应表单。
 * 表单直接编辑该任务的 params（每任务独立参数，与 MAA 客户端设置选项一致）。 */
import type { QueueTask } from './taskTypes'
import StartUpForm from './forms/StartUpForm.vue'
import CloseDownForm from './forms/CloseDownForm.vue'
import FightForm from './forms/FightForm.vue'
import RecruitForm from './forms/RecruitForm.vue'
import InfrastForm from './forms/InfrastForm.vue'
import MallForm from './forms/MallForm.vue'
import AwardForm from './forms/AwardForm.vue'
import RoguelikeForm from './forms/RoguelikeForm.vue'
import CopilotForm from './forms/CopilotForm.vue'

defineProps<{
  selectedTask: QueueTask | undefined
}>()
</script>

<template>
  <StartUpForm v-if="selectedTask?.entry === 'StartUp'" :params="selectedTask.params" />
  <CloseDownForm v-else-if="selectedTask?.entry === 'CloseDown'" :params="selectedTask.params" />
  <FightForm v-else-if="selectedTask?.entry === 'Fight'" :params="selectedTask.params" />
  <RecruitForm v-else-if="selectedTask?.entry === 'Recruit'" :params="selectedTask.params" />
  <InfrastForm v-else-if="selectedTask?.entry === 'Infrast'" :params="selectedTask.params" />
  <MallForm v-else-if="selectedTask?.entry === 'Mall'" :params="selectedTask.params" />
  <AwardForm v-else-if="selectedTask?.entry === 'Award'" :params="selectedTask.params" />
  <RoguelikeForm v-else-if="selectedTask?.entry === 'Roguelike'" :params="selectedTask.params" />
  <CopilotForm v-else-if="selectedTask?.entry === 'Copilot'" :params="selectedTask.params" />
  <div v-else-if="selectedTask" class="params params-note">未知任务类型（{{ selectedTask.entry }}）</div>
  <div v-else class="params params-note">请选择任务以配置参数</div>
</template>

<style scoped>
.params { padding: 12px 18px 16px; border-top: 1px solid var(--color-border-default); }
.params-note { color: var(--color-text-tertiary); font-size: var(--font-size-sm); }
</style>
