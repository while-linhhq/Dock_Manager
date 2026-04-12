import React from 'react';
import { FileSpreadsheet, Search, Ship } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type StatisticsFiltersBarProps = {
  shipId: string;
  setShipId: (v: string) => void;
  trackQ: string;
  setTrackQ: (v: string) => void;
  dateFrom: string;
  setDateFrom: (v: string) => void;
  dateTo: string;
  setDateTo: (v: string) => void;
  minConf: string;
  setMinConf: (v: string) => void;
  resetFilters: () => void;
  filterCount: number;
  onReloadFromServer: () => void;
  onExport: () => void;
};

export const StatisticsFiltersBar: React.FC<StatisticsFiltersBarProps> = ({
  shipId,
  setShipId,
  trackQ,
  setTrackQ,
  dateFrom,
  setDateFrom,
  dateTo,
  setDateTo,
  minConf,
  setMinConf,
  resetFilters,
  filterCount,
  onReloadFromServer,
  onExport,
}) => {
  return (
    <>
      <TableFilterPanel onReset={resetFilters} activeCount={filterCount}>
        <FilterField label="Mã tàu (voted_ship_id)">
          <div className="relative">
            <Ship className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500 pointer-events-none" />
            <input
              type="text"
              value={shipId}
              onChange={(e) => setShipId(e.target.value)}
              placeholder="Lọc client + nút tải theo tàu..."
              className={`${filterControlClass} pl-10`}
            />
          </div>
        </FilterField>
        <FilterField label="Track ID (chứa)">
          <input
            type="text"
            value={trackQ}
            onChange={(e) => setTrackQ(e.target.value)}
            placeholder="06-04-2026_15-39_000024"
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Từ ngày (logged_at)">
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
        <FilterField label="Độ tin cậy tối thiểu (0–1)">
          <input
            type="number"
            step="0.01"
            min={0}
            max={1}
            value={minConf}
            onChange={(e) => setMinConf(e.target.value)}
            placeholder="VD: 0.75"
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label=" " className="flex items-end">
          <Button
            type="button"
            onClick={onReloadFromServer}
            className="w-full bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Search className="w-4 h-4 mr-2" />
            Tải lại từ server (theo mã tàu)
          </Button>
        </FilterField>
      </TableFilterPanel>

      <div className="flex flex-wrap gap-2 justify-between items-center">
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400 max-w-xl leading-relaxed">
          Bảng ẩn <span className="font-mono">schema_version</span> và <span className="font-mono">seq</span>{' '}
          (vẫn có trong API / xuất Excel). Cột <span className="font-mono">ships_today</span> tương ứng{' '}
          <span className="font-mono">ships_completed_today</span>, fallback nội bộ theo{' '}
          <span className="font-mono">seq</span> nếu thiếu.
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={onExport}
          className="border-emerald-500/50 text-emerald-500 hover:bg-emerald-500/10 shrink-0"
        >
          <FileSpreadsheet className="w-4 h-4 mr-2" />
          Xuất Excel
        </Button>
      </div>
    </>
  );
};
