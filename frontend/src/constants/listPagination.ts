import type { PaginationProps } from "@arco-design/web-vue";

export const LIST_PAGE_SIZE_OPTIONS = [10, 20, 50, 100];

/**
 * 功能模块列表页统一分页：总数、翻页、每页条数、跳转。
 * 使用 defaultPageSize / defaultCurrent，勿传 pageSize / current——
 * 否则 a-table 会受控锁定，切换每页条数或页码后选中失效。
 */
export function listTablePagination(pageSize = 10): PaginationProps {
  return {
    defaultPageSize: pageSize,
    defaultCurrent: 1,
    showTotal: true,
    showPageSize: true,
    showJumper: true,
    pageSizeOptions: LIST_PAGE_SIZE_OPTIONS,
    pageSizeProps: {
      style: { width: "116px" },
    },
  };
}

/** 独立 a-pagination 组件（非 a-table 内嵌时使用） */
export function listStandalonePagination(pageSize = 10): PaginationProps {
  return listTablePagination(pageSize);
}
