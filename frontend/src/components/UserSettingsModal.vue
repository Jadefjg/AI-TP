<script setup lang="ts">
import { Message } from "@arco-design/web-vue";
import { reactive, ref, watch } from "vue";
import { useRouter } from "vue-router";
import { API_BASE_URL, API_DISPLAY_URL } from "../api/config";
import { authApi } from "../api/auth";
import { usePlatformStore } from "../state/platform";

const props = defineProps<{
  visible: boolean;
  initialTab?: "profile" | "password" | "api";
}>();

const emit = defineEmits<{
  (e: "update:visible", value: boolean): void;
}>();

const router = useRouter();
const store = usePlatformStore();
const activeTab = ref<"profile" | "password" | "api">("profile");
const saving = ref(false);

const profileForm = reactive({
  username: "",
  display_name: "",
  email: "",
});

const passwordForm = reactive({
  current_password: "",
  new_password: "",
  confirm_password: "",
});

const syncProfileForm = () => {
  const user = store.currentUser.value;
  if (!user) return;
  profileForm.username = user.username;
  profileForm.display_name = user.display_name || "";
  profileForm.email = user.email || "";
};

const syncPasswordForm = () => {
  passwordForm.current_password = "";
  passwordForm.new_password = "";
  passwordForm.confirm_password = "";
};

watch(
  () => props.visible,
  (open) => {
    if (!open) return;
    activeTab.value = props.initialTab || "profile";
    syncProfileForm();
    syncPasswordForm();
  },
);

watch(activeTab, (tab) => {
  if (tab === "password" && props.visible) {
    syncPasswordForm();
  }
});

const close = () => emit("update:visible", false);

const saveProfile = async () => {
  saving.value = true;
  try {
    await authApi.updateProfile({
      display_name: profileForm.display_name.trim() || null,
      email: profileForm.email.trim() || null,
    });
    await store.refreshCurrentUser();
    Message.success("基本信息已保存");
    close();
  } catch (error) {
    Message.error(error instanceof Error ? error.message : String(error));
  } finally {
    saving.value = false;
  }
};

const savePassword = async () => {
  if (!passwordForm.current_password) {
    Message.warning("请输入旧密码");
    return;
  }
  if (passwordForm.current_password.length < 8) {
    Message.warning("旧密码至少 8 位");
    return;
  }
  if (passwordForm.new_password.length < 8) {
    Message.warning("新密码至少 8 位");
    return;
  }
  if (passwordForm.new_password !== passwordForm.confirm_password) {
    Message.warning("两次输入的新密码不一致");
    return;
  }
  saving.value = true;
  try {
    const username = profileForm.username || store.currentUser.value?.username || "";
    await authApi.changePassword({
      current_password: passwordForm.current_password,
      new_password: passwordForm.new_password,
    });
    close();
    Message.success("密码修改成功，请使用新密码重新登录");
    await store.logout();
    await router.replace({
      name: "login",
      query: username ? { username } : undefined,
    });
  } catch (error) {
    Message.error(error instanceof Error ? error.message : String(error));
  } finally {
    saving.value = false;
  }
};

const onSave = () => {
  if (activeTab.value === "profile") {
    void saveProfile();
    return;
  }
  if (activeTab.value === "password") {
    void savePassword();
  }
};
</script>

<template>
  <a-modal
    :visible="visible"
    title="用户设置"
    :width="520"
    unmount-on-close
    @cancel="close"
  >
    <a-tabs v-model:active-key="activeTab">
      <a-tab-pane key="profile" title="基本信息">
        <a-form layout="vertical">
          <a-form-item label="用户名">
            <a-input v-model="profileForm.username" disabled />
          </a-form-item>
          <a-form-item label="显示名">
            <a-input v-model="profileForm.display_name" placeholder="显示名称" allow-clear />
          </a-form-item>
          <a-form-item label="邮箱">
            <a-input v-model="profileForm.email" placeholder="name@example.com" allow-clear />
          </a-form-item>
        </a-form>
      </a-tab-pane>
      <a-tab-pane key="password" title="修改密码">
        <a-form layout="vertical">
          <a-form-item label="旧密码" required>
            <a-input-password
              v-model="passwordForm.current_password"
              placeholder="请输入当前登录的旧密码"
              allow-clear
            />
          </a-form-item>
          <a-form-item label="新密码" required>
            <a-input-password v-model="passwordForm.new_password" placeholder="至少 8 位" />
          </a-form-item>
          <a-form-item label="确认新密码" required>
            <a-input-password v-model="passwordForm.confirm_password" placeholder="再次输入新密码" />
          </a-form-item>
        </a-form>
      </a-tab-pane>
      <a-tab-pane key="api" title="接口信息">
        <a-descriptions :column="1" bordered size="medium" class="api-info">
          <a-descriptions-item label="后端 API">
            <a-typography-paragraph copyable :ellipsis="{ rows: 1 }">
              {{ API_DISPLAY_URL }}
            </a-typography-paragraph>
          </a-descriptions-item>
          <a-descriptions-item v-if="API_BASE_URL !== API_DISPLAY_URL" label="前端请求前缀">
            <a-typography-paragraph copyable :ellipsis="{ rows: 1 }">
              {{ API_BASE_URL }}
            </a-typography-paragraph>
          </a-descriptions-item>
        </a-descriptions>
        <a-typography-text type="secondary" class="api-info__hint">
          开发环境下前端通过 Vite 代理访问后端；生产环境请在 .env 中配置 VITE_API_BASE_URL。
        </a-typography-text>
      </a-tab-pane>
    </a-tabs>

    <template #footer>
      <div class="modal-footer">
        <a-space>
          <a-button @click="close">{{ activeTab === "api" ? "关闭" : "取消" }}</a-button>
          <a-button
            v-if="activeTab !== 'api'"
            type="primary"
            :loading="saving"
            @click="onSave"
          >
            保存
          </a-button>
        </a-space>
      </div>
    </template>
  </a-modal>
</template>

<style scoped>
.modal-footer {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}

.api-info {
  margin-bottom: 12px;
}

.api-info :deep(.arco-descriptions-item-value) {
  word-break: break-all;
}

.api-info__hint {
  display: block;
  font-size: 12px;
  line-height: 1.5;
}
</style>
