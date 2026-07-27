<script setup lang="ts">
import { onMounted, watch } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import { usePlatformStore } from "./state/platform";

const route = useRoute();
const router = useRouter();
const store = usePlatformStore();

onMounted(() => {
  void store.bootstrapSession();
});

watch(
  [() => store.authReady.value, () => store.isAuthenticated.value, () => route.name],
  ([ready, authenticated, routeName]) => {
    if (!ready || routeName === "login") {
      return;
    }
    const requiresAuth = route.matched.some((record) => Boolean(record.meta.requiresAuth));
    if (requiresAuth && !authenticated) {
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
