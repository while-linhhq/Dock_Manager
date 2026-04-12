import React from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { PortConfigRead } from '../services/portApi';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type PortConfigsSectionProps = {
  cfgKeyQ: string;
  setCfgKeyQ: (v: string) => void;
  cfgValQ: string;
  setCfgValQ: (v: string) => void;
  resetCfgFilters: () => void;
  cfgFilterCount: number;
  onOpenAddConfig: () => void;
  filteredConfigs: PortConfigRead[];
  configs: PortConfigRead[];
  onEditConfig: (cfg: PortConfigRead) => void;
  onDeleteConfig: (key: string) => void;
};

export const PortConfigsSection: React.FC<PortConfigsSectionProps> = ({
  cfgKeyQ,
  setCfgKeyQ,
  cfgValQ,
  setCfgValQ,
  resetCfgFilters,
  cfgFilterCount,
  onOpenAddConfig,
  filteredConfigs,
  configs,
  onEditConfig,
  onDeleteConfig,
}) => {
  return (
    <div className="space-y-4">
      <TableFilterPanel
        title="Bộ lọc cấu hình"
        onReset={resetCfgFilters}
        activeCount={cfgFilterCount}
      >
        <FilterField label="Key">
          <input
            type="text"
            value={cfgKeyQ}
            onChange={(e) => setCfgKeyQ(e.target.value)}
            placeholder="Chứa..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Giá trị / mô tả">
          <input
            type="text"
            value={cfgValQ}
            onChange={(e) => setCfgValQ(e.target.value)}
            placeholder="Chứa..."
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-white/5 flex items-center justify-between">
          <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
            Cấu Hình Cảng
          </h3>
          <Button
            type="button"
            onClick={onOpenAddConfig}
            className="bg-blue-600 hover:bg-blue-700 text-white"
          >
            <Plus className="w-4 h-4 mr-2" />
            Thêm Config
          </Button>
        </div>
        <div className="divide-y divide-gray-100 dark:divide-white/5">
          {filteredConfigs.length > 0 ? (
            filteredConfigs.map((cfg) => (
              <div
                key={cfg.key}
                className="p-6 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:bg-gray-50 dark:hover:bg-white/[0.01] transition-colors"
              >
                <div>
                  <p className="text-xs font-bold text-gray-900 dark:text-white uppercase font-mono">
                    {cfg.key}
                  </p>
                  <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-1">
                    {cfg.description || 'Không có mô tả'}
                  </p>
                </div>
                <div className="flex items-center space-x-4">
                  <span className="px-4 py-2 bg-gray-100 dark:bg-white/5 rounded-lg text-xs font-mono text-blue-500 font-bold">
                    {cfg.value}
                  </span>
                  <button
                    type="button"
                    onClick={() => onEditConfig(cfg)}
                    className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest"
                  >
                    Thay Đổi
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteConfig(cfg.key)}
                    className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest inline-flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    Xóa
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="p-12 text-center text-gray-500 text-xs uppercase font-mono">
              {configs.length === 0 ? 'Chưa có cấu hình' : 'Không có mục khớp bộ lọc'}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
