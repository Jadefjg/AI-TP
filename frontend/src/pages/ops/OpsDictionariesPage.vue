<script setup lang="ts">
import { Message, Modal } from "@arco-design/web-vue";
import { onMounted, reactive, ref } from "vue";
import { opsApi, type Dictionary } from "../../api/ops";
import { usePlatformStore } from "../../state/platform";

const store = usePlatformStore();
const dictionaries = ref<Dictionary[]>([]);
const selected = ref<Dictionary | null>(null);
const dictForm = reactive({ code: "", name: "", description: "" });
const itemForm = reactive({ item_key: "", item_label: "", item_value: "", sort_order: 0 });

const canWrite = () => store.hasPermission("dict.write");

const load = () =>
  store.wrap(async () => {
    dictionaries.value = await opsApi.listDictionaries();
    if (selected.value) {
      selected.value = dictionaries.value.find((d) => d.id === selected.value!.id) ?? null;
    }
  });

const selectDict = (row: Dictionary) => {
  selected.value = row;
};

const saveDict = () => {
  if (!canWrite()) return;
  void store.wrap(async () => {
    await opsApi.upsertDictionary({ ...dictForm });
    Message.success("字典已保存");
    dictForm.code = "";
    dictForm.name = "";
    dictForm.description = "";
    await load();
  });
};

const saveItem = () => {
  if (!canWrite() || !selected.value) return;
  void store.wrap(async () => {
    await opsApi.upsertDictionaryItem(selected.value!.id, { ...itemForm });
    Message.success("字典项已保存");
    itemForm.item_key = "";
    itemForm.item_label = "";
    itemForm.item_value = "";
    await load();
  });
};

const removeDict = (row: Dictionary) => {
  if (!canWrite()) return;
  Modal.confirm({
    title: "删除字典？",
    content: `将删除「${row.name}」及其全部字典项`,
    onOk: () =>
      store.wrap(async () => {
        await opsApi.deleteDictionary(row.id);
        if (selected.value?.id === row.id) selected.value = null;
        Message.success("已删除");
        await load();
      }),
  });
};

const seed = () =>
  store.wrap(async () => {
    await opsApi.seedDictionaries();
    Message.success("已种子化内置字典");
    await load();
  });

onMounted(() => {
  void load();
});
</script>

<template>
  <div>
    <a-space style="margin-bottom: 12px">
      <a-button type="primary" :disabled="!canWrite()" @click="saveDict">新建/更新字典</a-button>
      <a-button :disabled="!canWrite()" @click="seed">种子内置字典</a-button>
      <a-button @click="load">刷新</a-button>
    </a-space>

    <a-form layout="inline" style="margin-bottom: 12px">
      <a-form-item label="编码"><a-input v-model="dictForm.code" style="width: 140px" /></a-form-item>
      <a-form-item label="名称"><a-input v-model="dictForm.name" style="width: 160px" /></a-form-item>
      <a-form-item label="描述"><a-input v-model="dictForm.description" style="width: 220px" /></a-form-item>
    </a-form>

    <a-row :gutter="12">
      <a-col :span="10">
        <a-table
          :data="dictionaries"
          row-key="id"
          :pagination="false"
          :columns="[
            { title: '编码', dataIndex: 'code' },
            { title: '名称', dataIndex: 'name' },
            { title: '操作', slotName: 'actions', width: 140 },
          ]"
          @row-click="selectDict"
        >
          <template #actions="{ record }">
            <a-space>
              <a-button size="mini" @click.stop="selectDict(record)">项</a-button>
              <a-button size="mini" status="danger" :disabled="!canWrite()" @click.stop="removeDict(record)">
                删
              </a-button>
            </a-space>
          </template>
        </a-table>
      </a-col>
      <a-col :span="14">
        <a-card v-if="selected" :title="`字典项 · ${selected.name}`" size="small">
          <a-form layout="inline" style="margin-bottom: 8px">
            <a-form-item label="Key"><a-input v-model="itemForm.item_key" style="width: 100px" /></a-form-item>
            <a-form-item label="标签"><a-input v-model="itemForm.item_label" style="width: 120px" /></a-form-item>
            <a-form-item label="值"><a-input v-model="itemForm.item_value" style="width: 120px" /></a-form-item>
            <a-button type="primary" size="small" :disabled="!canWrite()" @click="saveItem">保存项</a-button>
          </a-form>
          <a-table
            :data="selected.items"
            row-key="id"
            :pagination="false"
            :columns="[
              { title: 'Key', dataIndex: 'item_key', width: 100 },
              { title: '标签', dataIndex: 'item_label' },
              { title: '值', dataIndex: 'item_value' },
              { title: '排序', dataIndex: 'sort_order', width: 70 },
            ]"
          />
        </a-card>
        <a-empty v-else description="选择左侧字典查看项" />
      </a-col>
    </a-row>
  </div>
</template>
