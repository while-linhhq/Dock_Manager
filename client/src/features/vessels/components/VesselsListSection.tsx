import React from 'react';
import { CheckCircle2, Loader2, Plus, XCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import { formatApplicableFee, resolveVesselTypeName } from '../utils/vessel-display-helpers';

export type VesselsListSectionProps = {
  vesselQ: string;
  setVesselQ: (v: string) => void;
  vesselTypeFilter: string;
  setVesselTypeFilter: (v: string) => void;
  vesselActive: 'all' | 'active' | 'inactive';
  setVesselActive: (v: 'all' | 'active' | 'inactive') => void;
  vesselDateFrom: string;
  setVesselDateFrom: (v: string) => void;
  vesselDateTo: string;
  setVesselDateTo: (v: string) => void;
  resetVesselFilters: () => void;
  vesselFilterCount: number;
  onOpenAddVessel: () => void;
  vesselTypes: VesselTypeRead[];
  vessels: VesselRead[];
  filteredVessels: VesselRead[];
  isLoading: boolean;
  onEditVessel: (v: VesselRead) => void;
  onDeleteVessel: (id: string) => void;
};

export const VesselsListSection: React.FC<VesselsListSectionProps> = ({
  vesselQ,
  setVesselQ,
  vesselTypeFilter,
  setVesselTypeFilter,
  vesselActive,
  setVesselActive,
  vesselDateFrom,
  setVesselDateFrom,
  vesselDateTo,
  setVesselDateTo,
  resetVesselFilters,
  vesselFilterCount,
  onOpenAddVessel,
  vesselTypes,
  vessels,
  filteredVessels,
  isLoading,
  onEditVessel,
  onDeleteVessel,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel onReset={resetVesselFilters} activeCount={vesselFilterCount}>
        <FilterField label="Từ khóa (mã / tên / chủ / ĐK)">
          <input
            type="text"
            value={vesselQ}
            onChange={(e) => setVesselQ(e.target.value)}
            placeholder="Nhập để lọc..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Loại tàu">
          <select
            value={vesselTypeFilter}
            onChange={(e) => setVesselTypeFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vesselTypes.map((t) => (
              <option key={t.id} value={String(t.id)}>
                {t.type_name}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Trạng thái">
          <select
            value={vesselActive}
            onChange={(e) =>
              setVesselActive(e.target.value as 'all' | 'active' | 'inactive')
            }
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="active">Đang hoạt động</option>
            <option value="inactive">Tạm dừng</option>
          </select>
        </FilterField>
        <FilterField label="Từ ngày (tạo / cập nhật)">
          <input
            type="date"
            value={vesselDateFrom}
            onChange={(e) => setVesselDateFrom(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Đến ngày">
          <input
            type="date"
            value={vesselDateTo}
            onChange={(e) => setVesselDateTo(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-end">
        <Button
          type="button"
          onClick={onOpenAddVessel}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Đăng Ký Tàu
        </Button>
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className={dt.headRow}>
                <th className={dt.pad}>Mã Tàu (Ship ID)</th>
                <th className={dt.pad}>Tên Tàu</th>
                <th className={dt.pad}>Loại Tàu</th>
                <th className={dt.pad}>Chi Phí Theo Loại (tham chiếu)</th>
                <th className={dt.pad}>Chủ Tàu</th>
                <th className={dt.pad}>Trạng Thái</th>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && vessels.length === 0 ? (
                <tr>
                  <td colSpan={7} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredVessels.length > 0 ? (
                filteredVessels.map((v) => (
                  <tr
                    key={v.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors"
                  >
                    <td className={cn(dt.pad, dt.monoAccent)}>{v.ship_id}</td>
                    <td className={cn(dt.pad, dt.body, 'font-bold uppercase')}>
                      {v.name || '—'}
                    </td>
                    <td className={cn(dt.pad, dt.meta)}>
                      {resolveVesselTypeName(v, vesselTypes)}
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'max-w-[14rem]')}>
                      {formatApplicableFee(v)}
                    </td>
                    <td
                      className={cn(dt.pad, dt.bodyMuted, 'max-w-[12rem] truncate')}
                      title={v.owner ?? v.owner_info ?? ''}
                    >
                      {v.owner || v.owner_info || '—'}
                    </td>
                    <td className={dt.pad}>
                      <span
                        className={cn(
                          'inline-flex items-center px-2.5 py-1 rounded-full border',
                          dt.badge,
                          v.is_active
                            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                            : 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20',
                        )}
                      >
                        {v.is_active ? (
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 mr-1 shrink-0" />
                        )}
                        {v.is_active ? 'Hoạt Động' : 'Tạm Dừng'}
                      </span>
                    </td>
                    <td className={cn(dt.pad, 'text-right')}>
                      <div className="inline-flex items-center gap-3">
                        <button
                          type="button"
                          onClick={() => onEditVessel(v)}
                          className={cn(dt.action, 'text-blue-600 hover:text-blue-500 dark:text-blue-400')}
                        >
                          Chỉnh Sửa
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteVessel(String(v.id))}
                          className={cn(dt.action, 'text-red-600 hover:text-red-500 dark:text-red-400')}
                        >
                          Xóa
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={7}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {vessels.length === 0
                      ? 'Không có dữ liệu tàu'
                      : 'Không có bản ghi khớp bộ lọc'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
