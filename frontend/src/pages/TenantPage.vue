<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { Message } from "@arco-design/web-vue";
import { useRoute } from "vue-router";
import { organizationsApi } from "../api/organizations";
import { rbacApi } from "../api/rbac";
import AiWorkspaceHero from "../components/ai/AiWorkspaceHero.vue";
import { listTablePagination } from "../constants/listPagination";
import { usePlatformStore } from "../state/platform";
import type { BillingInvoice, Organization, OrganizationMember, OrganizationQuota, User } from "../types";

const store = usePlatformStore();
const tablePagination = listTablePagination(10);
const route = useRoute();
const canMembers = computed(() => store.hasPermission("org.member.read"));
const canManageMembers = computed(() => store.hasPermission("org.member.manage"));
const canBilling = computed(() => store.hasPermission("billing.read"));
const canManageBilling = computed(() => store.hasPermission("billing.manage"));

const resolveDefaultTab = () => {
  if (route.path.includes("/billing/") && canBilling.value) return "billing";
  if (canMembers.value) return "members";
  if (canBilling.value) return "billing";
  return "members";
};

const activeTab = ref(resolveDefaultTab());
const organizations = ref<Organization[]>([]);
const selectedOrgId = ref<number | null>(null);
const orgReady = ref(false);
const quota = ref<OrganizationQuota | null>(null);
const members = ref<OrganizationMember[]>([]);
const invoices = ref<BillingInvoice[]>([]);
const allUsers = ref<User[]>([]);

const memberForm = reactive({
  user_id: undefined as number | undefined,
  role_names: ["member"] as string[],
});
const invoicePeriod = ref("");
const roles = ref<{ name: string; description?: string | null }[]>([]);

const TENANT_ROLE_PRESETS = ["org_admin", "member", "viewer"];

const roleOptions = computed(() => {
  const fromApi = roles.value.map((r) => r.name);
  const merged = [...new Set([...TENANT_ROLE_PRESETS, ...fromApi])];
  return merged.map((name) => ({
    value: name,
    label: name,
    hint: roles.value.find((r) => r.name === name)?.description ?? undefined,
  }));
});

const bindableUsers = computed(() =>
  allUsers.value.filter((u) => !members.value.some((m) => m.user_id === u.id)),
);

const isPlatformAdmin = computed(() => currentUserOrgId.value == null);
const currentUserOrgId = computed(() => store.currentUser.value?.organization_id ?? null);

const selectedOrg = computed(() => organizations.value.find((o) => o.id === selectedOrgId.value) ?? null);

const memberColumns = [
  { title: "用户", dataIndex: "username" },
  { title: "显示名", dataIndex: "display_name" },
  { title: "邮箱", dataIndex: "email" },
  { title: "角色", slotName: "roles" },
  { title: "状态", slotName: "active" },
  { title: "操作", slotName: "actions", width: 100 },
];

const invoiceColumns = [
  { title: "账期", dataIndex: "period", width: 100 },
  { title: "Token 用量", dataIndex: "token_usage" },
  { title: "金额", slotName: "amount" },
  { title: "状态", slotName: "status" },
  { title: "创建时间", dataIndex: "created_at", width: 180 },
  { title: "操作", slotName: "invActions", width: 220 },
];

const formatMoney = (cents: number, currency: string) =>
  `${(cents / 100).toFixed(2)} ${currency.toUpperCase()}`;

const statusColor = (status: string) => {
  if (status === "paid") return "green";
  if (status === "issued") return "arcoblue";
  return "gray";
};

const loadOrganizations = async () => {
  organizations.value = await organizationsApi.listOrganizations();
  if (!selectedOrgId.value && organizations.value.length) {
    const preferred =
      currentUserOrgId.value != null
        ? organizations.value.find((o) => o.id === currentUserOrgId.value)
        : organizations.value[0];
    selectedOrgId.value = preferred?.id ?? organizations.value[0].id;
  }
};

const loadQuota = async () => {
  if (!selectedOrgId.value) return;
  quota.value = await organizationsApi.getOrganizationQuota(selectedOrgId.value);
};

const loadMembers = async () => {
  if (!selectedOrgId.value || !canMembers.value) return;
  members.value = await organizationsApi.listOrganizationMembers(selectedOrgId.value);
};

const loadInvoices = async () => {
  if (!selectedOrgId.value || !canBilling.value) return;
  invoices.value = await organizationsApi.listBillingInvoices(selectedOrgId.value);
};

const loadUsers = async () => {
  if (store.hasPermission("user.manage")) {
    allUsers.value = await rbacApi.listUsers();
  }
  if (store.hasPermission("role.manage")) {
    roles.value = await rbacApi.listRoles();
  }
};

const resetMemberForm = () => {
  memberForm.user_id = undefined;
  memberForm.role_names = ["member"];
};

const addMember = () => {
  const uid = memberForm.user_id;
  if (!uid) {
    Message.warning("请选择要绑定的用户");
    return;
  }
  if (!memberForm.role_names.length) {
    Message.warning("请至少选择一个角色");
    return;
  }
  void store.wrap(async () => {
    if (!selectedOrgId.value) return;
    await organizationsApi.addOrganizationMemberByRoles(selectedOrgId.value, {
      user_id: uid,
      role_names: memberForm.role_names,
    });
    resetMemberForm();
    await loadMembers();
    Message.success("成员已绑定到当前租户");
  });
};

const reloadOrgData = () =>
  store.wrap(async () => {
    if (!selectedOrgId.value) return;
    await Promise.all([loadQuota(), loadMembers(), loadInvoices()]);
    store.setOut({
      org_id: selectedOrgId.value,
      quota: quota.value,
      members: members.value.length,
      invoices: invoices.value.length,
    });
  });

const removeMember = (userId: number) =>
  store.wrap(async () => {
    if (!selectedOrgId.value) return;
    await organizationsApi.removeOrganizationMember(selectedOrgId.value, userId);
    await loadMembers();
    Message.success("成员已移除");
  });

const init = () =>
  store.wrap(async () => {
    await loadOrganizations();
    await loadUsers();
    await reloadOrgData();
    orgReady.value = true;
  });

const generateInvoice = () =>
  store.wrap(async () => {
    if (!selectedOrgId.value) return;
    const inv = await organizationsApi.generateBillingInvoice(
      selectedOrgId.value,
      invoicePeriod.value.trim() || undefined,
    );
    invoicePeriod.value = "";
    store.setOut({ invoice: inv });
    await loadInvoices();
    await loadQuota();
  });

const downloadPdf = (invoiceId: number) =>
  store.wrap(async () => {
    if (!selectedOrgId.value) return;
    await organizationsApi.downloadBillingInvoicePdf(selectedOrgId.value, invoiceId);
  });

const payWithStripe = (invoice: BillingInvoice) =>
  store.wrap(async () => {
    if (!selectedOrgId.value) return;
    const origin = window.location.origin;
    const result = await organizationsApi.createBillingCheckout(selectedOrgId.value, {
      invoice_id: invoice.id,
      success_url: `${origin}/billing/success`,
      cancel_url: `${origin}/billing/cancel`,
    });
    if (result.mock) {
      Message.success("开发环境模拟支付完成，账单已标记为已支付");
      await loadInvoices();
      await loadQuota();
      return;
    }
    window.open(result.checkout_url, "_blank", "noopener,noreferrer");
  });

watch(selectedOrgId, () => {
  if (!orgReady.value || !selectedOrgId.value) return;
  void reloadOrgData();
});

onMounted(() => {
  if (route.name === "billing-success") {
    activeTab.value = "billing";
    Message.success("支付流程已完成；账单状态将在 Stripe Webhook 回调后更新");
  } else if (route.name === "billing-cancel") {
    activeTab.value = "billing";
    Message.warning("已取消支付");
  } else {
    activeTab.value = resolveDefaultTab();
  }
  void init();
});
</script>

<template>
  <div class="ai-workspace">
    <AiWorkspaceHero
      title="租户管理"
      subtitle="组织成员绑定、配额洞察与 AI 用量账单"
      badge="AI · TENANT"
      status-label="多租户就绪"
      status-tone="online"
    >
      <template #extra>
        <a-space>
          <a-select
            v-if="isPlatformAdmin"
            v-model="selectedOrgId"
            placeholder="选择租户"
            style="width: 260px"
            allow-search
          >
            <a-option v-for="org in organizations" :key="org.id" :value="org.id">
              {{ org.name }} ({{ org.slug }})
            </a-option>
          </a-select>
          <a-tag v-else-if="selectedOrg" color="arcoblue">{{ selectedOrg.name }}</a-tag>
          <a-button type="primary" class="ai-action-btn" :loading="store.loading.value" @click="init">
            刷新
          </a-button>
        </a-space>
      </template>
    </AiWorkspaceHero>

    <template v-if="selectedOrgId">
      <a-row v-if="quota" :gutter="[16, 16]" class="quota-row">
        <a-col :xs="12" :sm="12" :md="6">
          <a-card class="quota-card" :bordered="false">
            <a-statistic title="项目数" :value="quota.project_count" :suffix="`/ ${quota.max_projects || '∞'}`" />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card class="quota-card" :bordered="false">
            <a-statistic title="本月 Token" :value="quota.monthly_tokens_used" />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card class="quota-card" :bordered="false">
            <a-statistic
              title="Token 配额"
              :value="quota.monthly_ai_token_quota <= 0 ? '不限' : quota.monthly_ai_token_quota"
            />
          </a-card>
        </a-col>
        <a-col :xs="12" :sm="12" :md="6">
          <a-card class="quota-card" :bordered="false">
            <a-statistic
              title="剩余额度"
              :value="quota.monthly_tokens_remaining == null ? '不限' : quota.monthly_tokens_remaining"
            />
          </a-card>
        </a-col>
      </a-row>

      <a-tabs v-model:active-key="activeTab" class="tenant-tabs">
        <a-tab-pane v-if="canMembers" key="members" title="成员管理">
          <a-card title="成员列表" class="tenant-panel">
            <template #extra>
              <a-typography-text type="secondary">
                共 {{ members.length }} 人
              </a-typography-text>
            </template>

            <section v-if="canManageMembers" class="member-bind">
              <div class="member-bind__title">绑定新成员</div>
              <a-form :model="memberForm" layout="vertical" class="member-bind__form">
                <a-row :gutter="16" align="stretch">
                  <a-col :xs="24" :sm="24" :md="10" :lg="9">
                    <a-form-item label="用户" required>
                      <a-select
                        v-if="allUsers.length"
                        v-model="memberForm.user_id"
                        placeholder="搜索并选择用户"
                        allow-search
                        allow-clear
                      >
                        <a-option v-for="u in bindableUsers" :key="u.id" :value="u.id">
                          {{ u.username }}
                          <span v-if="u.display_name" class="option-muted"> · {{ u.display_name }}</span>
                        </a-option>
                      </a-select>
                      <a-input-number
                        v-else
                        v-model="memberForm.user_id"
                        placeholder="输入用户 ID"
                        :min="1"
                        style="width: 100%"
                      />
                    </a-form-item>
                  </a-col>
                  <a-col :xs="24" :sm="24" :md="10" :lg="9">
                    <a-form-item label="租户角色" required>
                      <a-select
                        v-model="memberForm.role_names"
                        placeholder="选择角色"
                        multiple
                        allow-clear
                      >
                        <a-option v-for="opt in roleOptions" :key="opt.value" :value="opt.value">
                          {{ opt.label }}
                        </a-option>
                      </a-select>
                    </a-form-item>
                  </a-col>
                  <a-col :xs="24" :sm="24" :md="4" :lg="6" class="member-bind__action-col">
                    <a-form-item label=" ">
                      <a-button type="primary" long :loading="store.loading.value" @click="addMember">
                        绑定到当前租户
                      </a-button>
                    </a-form-item>
                  </a-col>
                </a-row>
                <a-typography-text type="secondary" class="member-bind__hint">
                  常用角色：org_admin（租户管理员）、member（普通成员）、viewer（只读）。须先在用户管理模块创建对应 Role。
                </a-typography-text>
              </a-form>
            </section>

            <a-divider v-if="canManageMembers" />

            <a-table
              :columns="memberColumns"
              :data="members"
              :pagination="tablePagination"
              row-key="id"
              :bordered="false"
            >
              <template #roles="{ record }">
                <a-space wrap>
                  <a-tag v-for="r in record.role_names" :key="r" size="small" color="arcoblue">{{ r }}</a-tag>
                </a-space>
              </template>
              <template #active="{ record }">
                <a-tag :color="record.is_active ? 'green' : 'red'">
                  {{ record.is_active ? "启用" : "停用" }}
                </a-tag>
              </template>
              <template #actions="{ record }">
                <a-popconfirm
                  v-if="canManageMembers"
                  content="确定移出该成员？"
                  @ok="removeMember(record.user_id)"
                >
                  <a-button type="text" status="danger" size="small">移除</a-button>
                </a-popconfirm>
              </template>
              <template #empty>
                <a-empty description="暂无成员，可在上方绑定用户" />
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>

        <a-tab-pane v-if="canBilling" key="billing" title="账单">
          <a-card title="账单记录" class="tenant-panel">
            <section v-if="canManageBilling" class="billing-generate">
              <a-form layout="vertical" class="billing-generate__form">
                <a-row :gutter="16" align="stretch">
                  <a-col :xs="24" :sm="16" :md="10" :lg="8">
                    <a-form-item label="账期">
                      <a-input v-model="invoicePeriod" placeholder="YYYY-MM，留空为当月" allow-clear />
                    </a-form-item>
                  </a-col>
                  <a-col :xs="24" :sm="8" :md="6" :lg="4" class="billing-generate__action-col">
                    <a-form-item label=" ">
                      <a-button type="primary" long :loading="store.loading.value" @click="generateInvoice">
                        生成 / 更新账单
                      </a-button>
                    </a-form-item>
                  </a-col>
                </a-row>
              </a-form>
            </section>

            <a-divider v-if="canManageBilling" />

            <a-table
              :columns="invoiceColumns"
              :data="invoices"
              :pagination="tablePagination"
              row-key="id"
              :bordered="false"
            >
              <template #amount="{ record }">
                {{ formatMoney(record.amount_cents, record.currency) }}
              </template>
              <template #status="{ record }">
                <a-tag :color="statusColor(record.status)">{{ record.status }}</a-tag>
              </template>
              <template #invActions="{ record }">
                <a-space>
                  <a-button size="small" @click="downloadPdf(record.id)">PDF</a-button>
                  <a-button
                    v-if="canManageBilling && record.status !== 'paid'"
                    size="small"
                    type="primary"
                    @click="payWithStripe(record)"
                  >
                    Stripe 支付
                  </a-button>
                </a-space>
              </template>
              <template #empty>
                <a-empty description="暂无账单，可先生成当月账单" />
              </template>
            </a-table>
          </a-card>
        </a-tab-pane>
      </a-tabs>
    </template>

    <a-empty v-else description="暂无可用租户" />
  </div>
</template>

<style scoped>
.quota-row {
  margin-bottom: 16px;
}

.quota-card {
  height: 100%;
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.28) !important;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.98)),
    #fff !important;
  box-shadow:
    0 10px 30px rgba(15, 23, 42, 0.05),
    inset 0 1px 0 rgba(255, 255, 255, 0.9) !important;
}

.quota-card :deep(.arco-statistic-title) {
  margin-bottom: 4px;
  color: var(--color-text-2);
  font-size: 13px;
}

.tenant-tabs :deep(.arco-tabs-content) {
  padding-top: 4px;
}

.tenant-panel {
  border-radius: 16px !important;
  border: 1px solid rgba(148, 163, 184, 0.28) !important;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.98)),
    #fff !important;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.05) !important;
}

.member-bind {
  padding: 4px 0 0;
}

.member-bind__title {
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-1);
}

.member-bind__form :deep(.arco-form-item) {
  margin-bottom: 0;
}

.member-bind__action-col {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.member-bind__hint {
  display: block;
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.billing-generate {
  padding-top: 4px;
}

.billing-generate__form :deep(.arco-form-item) {
  margin-bottom: 0;
}

.billing-generate__action-col {
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}

.option-muted {
  color: var(--color-text-3);
  font-size: 12px;
}
</style>
