<script setup lang="ts">
import { computed } from "vue";
import { useRoute, useRouter } from "vue-router";

const route = useRoute();
const router = useRouter();

const permissionHint = computed(() => {
  const raw = route.query.permission;
  if (typeof raw === "string" && raw.trim()) {
    return `需要 ${raw} 权限`;
  }
  return "当前账号没有访问此页面的权限";
});
</script>

<template>
  <div class="ai-workspace forbidden-page">
    <div class="forbidden-hud ai-panel">
      <div class="ai-chip-rail">
        <span class="ai-chip">ACCESS DENIED</span>
        <span class="ai-chip">403</span>
      </div>
      <a-result status="403" title="无权访问" :subtitle="permissionHint">
        <template #extra>
          <a-space>
            <a-button type="primary" class="ai-action-btn" @click="router.push('/dashboard')">返回首页</a-button>
            <a-button @click="router.back()">返回上一页</a-button>
          </a-space>
        </template>
      </a-result>
    </div>
  </div>
</template>

<style scoped>
.forbidden-page {
  display: grid;
  place-items: center;
  min-height: 60vh;
}

.forbidden-hud {
  width: min(520px, 100%);
  padding: 8px 8px 20px;
}
</style>
