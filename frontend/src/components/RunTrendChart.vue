<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export type TrendPoint = { date: string; total: number; failed: number; completed: number };

const props = defineProps<{ points: TrendPoint[]; days?: number }>();

const option = computed(() => ({
  title: {
    text: `近 ${props.days ?? props.points.length} 天 Run 趋势`,
    left: "center",
    textStyle: { fontSize: 14 },
  },
  tooltip: { trigger: "axis" },
  legend: { data: ["总 Run", "失败", "完成"], bottom: 0 },
  grid: { left: 48, right: 24, top: 48, bottom: 48 },
  xAxis: { type: "category", data: props.points.map((p) => p.date) },
  yAxis: { type: "value", minInterval: 1 },
  series: [
    { name: "总 Run", type: "line", smooth: true, data: props.points.map((p) => p.total) },
    { name: "失败", type: "line", smooth: true, data: props.points.map((p) => p.failed) },
    { name: "完成", type: "line", smooth: true, data: props.points.map((p) => p.completed) },
  ],
}));
</script>

<template>
  <VChart class="run-trend-chart" :option="option" autoresize />
</template>

<style scoped>
.run-trend-chart {
  width: 100%;
  height: 320px;
}
</style>
