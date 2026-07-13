import type { ReactNode } from "react";

export interface TableColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export interface TableProps<T> {
  columns: TableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  error?: string;
  emptyState: ReactNode;
  /**
   * When set, each row becomes a pointer target invoking this on click. For
   * keyboard access, render a real focusable control (e.g. a Link) inside one
   * of the columns as well - this handler is a convenience, not the only path.
   */
  onRowClick?: (row: T) => void;
}

/**
 * docs/design/frontend.md section 6: sticky header, row hover; loading
 * (skeleton rows), empty (EmptyState inside), error. Collapses to
 * horizontal scroll within the card at 768px (frontend.md section 8) via
 * the wrapping overflow-x-auto - never the page itself.
 */
export function Table<T>({
  columns,
  rows,
  rowKey,
  loading,
  error,
  emptyState,
  onRowClick,
}: TableProps<T>) {
  if (error) {
    return (
      <div className="rounded-lg border border-border bg-surface p-6 text-body-sm text-danger">
        {error}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-lg border border-border bg-surface">
      <table className="w-full text-body-sm">
        <thead className="sticky top-0 bg-surface-sunken">
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className="px-4 py-2 text-left font-medium text-text-secondary"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading ? (
            Array.from({ length: 3 }).map((_, index) => (
              <tr key={index} className="border-t border-border">
                <td colSpan={columns.length} className="px-4 py-3">
                  <div className="h-4 w-full animate-pulse rounded bg-surface-sunken" />
                </td>
              </tr>
            ))
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length}>{emptyState}</td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr
                key={rowKey(row)}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={`border-t border-border hover:bg-surface-sunken ${
                  onRowClick ? "cursor-pointer" : ""
                }`}
              >
                {columns.map((column) => (
                  <td key={column.key} className="px-4 py-3 text-text">
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
