import React from 'react';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type BackupFiltersBarProps = {
  q: string;
  setQ: (v: string) => void;
  tableQ: string;
  setTableQ: (v: string) => void;
  actionQ: string;
  setActionQ: (v: string) => void;
  dateFrom: string;
  setDateFrom: (v: string) => void;
  dateTo: string;
  setDateTo: (v: string) => void;
  onReset: () => void;
  filterCount: number;
};

export const BackupFiltersBar: React.FC<BackupFiltersBarProps> = ({
  q,
  setQ,
  tableQ,
  setTableQ,
  actionQ,
  setActionQ,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  onReset,
  filterCount,
}) => {
  return (
    <TableFilterPanel onReset={onReset} activeCount={filterCount}>
      <FilterField label="Từ khóa (hành động / bảng / record / user)">
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Lọc nhanh..."
          className={filterControlClass}
        />
      </FilterField>
      <FilterField label="Tên bảng (chứa)">
        <input
          type="text"
          value={tableQ}
          onChange={(e) => setTableQ(e.target.value)}
          placeholder="invoices..."
          className={filterControlClass}
        />
      </FilterField>
      <FilterField label="Hành động (chứa)">
        <input
          type="text"
          value={actionQ}
          onChange={(e) => setActionQ(e.target.value)}
          placeholder="CREATE..."
          className={filterControlClass}
        />
      </FilterField>
      <FilterField label="Từ ngày">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          className={filterControlClass}
        />
      </FilterField>
      <FilterField label="Đến ngày">
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          className={filterControlClass}
        />
      </FilterField>
    </TableFilterPanel>
  );
};
