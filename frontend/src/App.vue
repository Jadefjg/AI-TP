<script setup lang="ts">
import { watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { authStore } from "./api/auth-store";
import { usePlatformStore } from "./state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();

watch(
  [() => store.authReady.value, () => store.currentUser.value, () => route.name],
  ([ready]) => {
    if (!ready) {
      return;
    }
    if (route.name === "login" || route.name === "register") {
      return;
    }
    const requiresAuth = route.matched.some((record) => Boolean(record.meta.requiresAuth));
    if (requiresAuth && !authStore.getToken()) {
      void router.replace({ name: "login", query: { redirect: route.fullPath } });
    }
  },
);
</script>

<template>
  <div class="app-root">
    <RouterView />
    <section v-if="!store.authReady.value" class="app-loading app-loading--overlay">
      <div class="card loading-card">
        <h3>登录态检查中</h3>
        <p class="muted">正在验证当前访问令牌。</p>
      </div>
    </section>
  </div>
</template>
