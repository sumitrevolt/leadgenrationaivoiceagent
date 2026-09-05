import type { ReactNode } from 'react';
import { ArrowDown, ArrowUp, ChevronsUpDown } from 'lucide-react';
import type { SortDirection } from '@/types';
import { cn } from '@/lib/utils';
import { Skeleton } from './primitives';

export interface Column<T> {
  key: string;
  header: string;
  sortable?: boolean;
  align?: 'left' | 'right' | 'center';
  /** Tailwind breakpoint prefix at/below which the column is hidden, e.g. 'md' hides on md and smaller. */
  hideBelow?: 'sm' | 'md' | 'lg' | 'xl';
  width?: string;
  render: (row: T) => ReactNode;
}

const HIDE: Record<NonNullable<Column<unknown>['hideBelow']>, string> = {
  sm: 'hidden sm:table-cell',
  md: 'hidden md:table-cell',
  lg: 'hidden lg:table-cell',
  xl: 'hidden xl:table-cell',
};

const ALIGN: Record<NonNullable<Column<unknown>['align']>, string> = {
  left: 'text-left',
  right: 'text-right',
  center: 'text-center',
};

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  sort,
  dir,
  onSortChange,
  loadingRows = 0,
  empty,
  selected,
  onToggleRow,
  onToggleAll,
  onRowClick,
  className,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  sort?: string;
  dir?: SortDirection;
  onSortChange?: (key: string) => void;
  loadingRows?: number;
  empty?: ReactNode;
  selected?: Set<string>;
  onToggleRow?: (id: string) => void;
  onToggleAll?: (checked: boolean) => void;
  onRowClick?: (row: T) => void;
  className?: string;
}) {
  const showCheckboxes = Boolean(selected && onToggleRow);
  const allChecked =
    rows.length > 0 && Boolean(selected && rows.every((r) => selected.has(rowKey(r))));
  const someChecked = Boolean(selected && rows.some((r) => selected.has(rowKey(r))) && !allChecked);

  if (loadingRows > 0) {
    return (
      <div className="overflow-x-auto">
        <table className={cn('w-full border-collapse text-sm', className)}>
          <thead>
            <tr className="border-b border-line bg-elevated/40">
              {showCheckboxes && <th className="w-10 px-4 py-2.5" />}
              {columns.map((c) => (
                <th key={c.key} className="px-4 py-2.5">
                  <Skeleton className="h-3 w-20" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: loadingRows }).map((_, i) => (
              <tr key={i} className="border-b border-line/60">
                {showCheckboxes && (
                  <td className="px-4 py-3">
                    <Skeleton className="h-4 w-4 rounded" />
                  </td>
                )}
                {columns.map((c) => (
                  <td key={c.key} className="px-4 py-3">
                    <Skeleton className="h-3.5 w-full max-w-[140px]" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="w-full overflow-x-auto">
      <table className={cn('w-full border-collapse text-sm', className)}>
        <thead>
          <tr className="border-b border-line bg-elevated/40">
            {showCheckboxes && (
              <th className="w-10 px-4 py-2.5">
                <input
                  type="checkbox"
                  aria-label="Select all rows on this page"
                  checked={allChecked}
                  ref={(el) => {
                    if (el) el.indeterminate = someChecked;
                  }}
                  onChange={(e) => onToggleAll?.(e.target.checked)}
                  className="h-4 w-4 cursor-pointer rounded border-line bg-elevated accent-[rgb(var(--brand))]"
                />
              </th>
            )}
            {columns.map((c) => {
              const active = sort === c.key;
              return (
                <th
                  key={c.key}
                  scope="col"
                  style={c.width ? { width: c.width } : undefined}
                  className={cn(
                    'whitespace-nowrap px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wide text-faint',
                    ALIGN[c.align ?? 'left'],
                    c.hideBelow && HIDE[c.hideBelow],
                  )}
                  aria-sort={active ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}
                >
                  {c.sortable ? (
                    <button
                      type="button"
                      onClick={() => onSortChange?.(c.key)}
                      className={cn(
                        'inline-flex items-center gap-1 rounded transition-colors hover:text-ink',
                        active && 'text-brand',
                        c.align === 'right' && 'flex-row-reverse',
                      )}
                    >
                      {c.header}
                      {active ? (
                        dir === 'asc' ? (
                          <ArrowUp className="h-3 w-3" />
                        ) : (
                          <ArrowDown className="h-3 w-3" />
                        )
                      ) : (
                        <ChevronsUpDown className="h-3 w-3 opacity-50" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length + (showCheckboxes ? 1 : 0)}>{empty}</td>
            </tr>
          ) : (
            rows.map((row) => {
              const id = rowKey(row);
              const isSelected = selected?.has(id) ?? false;
              return (
                <tr
                  key={id}
                  onClick={() => onRowClick?.(row)}
                  className={cn(
                    'border-b border-line/60 transition-colors last:border-0',
                    onRowClick && 'cursor-pointer hover:bg-elevated/60',
                    isSelected && 'bg-brand/[0.06]',
                  )}
                >
                  {showCheckboxes && (
                    <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        aria-label={`Select row ${id}`}
                        checked={isSelected}
                        onChange={() => onToggleRow?.(id)}
                        className="h-4 w-4 cursor-pointer rounded border-line bg-elevated accent-[rgb(var(--brand))]"
                      />
                    </td>
                  )}
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={cn(
                        'px-4 py-3 align-middle text-ink',
                        ALIGN[c.align ?? 'left'],
                        c.hideBelow && HIDE[c.hideBelow],
                      )}
                    >
                      {c.render(row)}
                    </td>
                  ))}
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
