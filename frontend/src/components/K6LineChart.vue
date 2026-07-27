<script setup lang="ts">
import { computed } from "vue";
import VChart from "vue-echarts";
import { use } from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, LegendComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

use([LineChart, GridComponent, TooltipComponent, LegendComponent, CanvasRenderer]);

export type K6Point = {
  t_sec: number;
  rt_ms?: number;
  tps?: number;
  error_rate?: number;
};

const props = withDefaults(
  defineProps<{
    series: K6Point[];
    title?: string;
    subtitle?: string;
    height?: string;
  }>(),
  { title: "k6 性能时序", subtitle: "", height: "360px" },
);

const option = computed(() => {
  const data = props.series || [];
  return {
    title: {
      text: props.title,
      subtext: props.subtitle,
      left: "center",
      textStyle: { fontSize: 14, fontWeight: 500 },
      subtextStyle: { fontSize: 12 },
    },
    tooltip: { trigger: "axis" },
    legend: { data: ["RT (ms)", "TPS", "错误率 (%)"], bottom: 0 },
    grid: { left: 48, right: 48, top: 56, bottom: 48 },
    xAxis: {
      type: "category",
      boundaryGap: false,
      data: data.map((p) => `${p.t_sec}s`),
    },
    yAxis: [
      { type: "value", name: "RT / TPS", scale: true },
      { type: "value", name: "错误率", max: 100, axisLabel: { formatter: "{value}%" } },
    ],
    series: [
      {
        name: "RT (ms)",
        type: "line",
        smooth: true,
        showSymbol: data.length <= 24,
        data: data.map((p) => p.rt_ms ?? 0),
      },
      {
        name: "TPS",
        type: "line",
        smooth: true,
        showSymbol: false,
        data: data.map((p) => p.tps ?? 0),
      },
      {
        name: "错误率 (%)",
        type: "line",
        smooth: true,
        yAxisIndex: 1,
        showSymbol: false,
        data: data.map((p) => p.error_rate ?? 0),
      },
    ],
  };
});
</script>

<template>
  <VChart class="k6-line-chart" :option="option" autoresize />
</template>

<style scoped>
.k6-line-chart {
  width: 100%;
  height: v-bind(height);
}
</style>
