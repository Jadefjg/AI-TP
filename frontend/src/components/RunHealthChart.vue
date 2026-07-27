<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

const props = defineProps<{
  failed: number;
  running: number;
  pending: number;
  completed?: number;
}>();

const option = computed(() => ({
  tooltip: { trigger: "axis" },
  grid: { left: 40, right: 16, top: 24, bottom: 32 },
  xAxis: {
    type: "category",
    data: ["失败", "运行中", "排队", "已完成"],
  },
  yAxis: { type: "value", minInterval: 1 },
  series: [
    {
      type: "bar",
      data: [
        { value: props.failed, itemStyle: { color: "#f53f3f" } },
        { value: props.running, itemStyle: { color: "#165dff" } },
        { value: props.pending, itemStyle: { color: "#86909c" } },
        { value: props.completed ?? 0, itemStyle: { color: "#00b42a" } },
      ],
      barMaxWidth: 48,
    },
  ],
}));
</script>

<template>
  <VChart class="run-health-chart" :option="option" autoresize />
</template>

<style scoped>
.run-health-chart {
  width: 100%;
  height: 260px;
}
</style>
