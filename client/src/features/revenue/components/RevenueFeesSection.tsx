import React from 'react';
import { DollarSign, Loader2, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import type { FeeConfigRead, VesselTypeRead } from '../../../types/api.types';
import { formatFeeConfigDisplay } from '../../../utils/fee-billing-unit';
import { feeConfigVesselTypeLabel } from '../utils/revenue-fee-helpers';

export type RevenueFeesSectionProps = {
  feeQ: string;
  setFeeQ: (v: string) => void;
  feeTypeId: string;
  setFeeTypeId: (v: string) => void;
  feeActive: 'all' | 'on' | 'off';
  setFeeActive: (v: 'all' | 'on' | 'off') => void;
  feeDateFrom: string;
  setFeeDateFrom: (v: string) => void;
  feeDateTo: string;
  setFeeDateTo: (v: string) => void;
  resetFeeFilters: () => void;
  feeFilterCount: number;
  vesselTypes: VesselTypeRead[];
  filteredFeeConfigs: FeeConfigRead[];
  feeConfigs: FeeConfigRead[];
  isLoading: boolean;
  onOpenAddFee: () => void;
  onEditFee: (fee: FeeConfigRead) => void;
  onDeleteFee: (fee: FeeConfigRead) => void;
};

export const RevenueFeesSection: React.FC<RevenueFeesSectionProps> = ({
  feeQ,
  setFeeQ,
  feeTypeId,
  setFeeTypeId,
  feeActive,
  setFeeActive,
  feeDateFrom,
  setFeeDateFrom,
  feeDateTo,
  setFeeDateTo,
  resetFeeFilters,
  feeFilterCount,
  vesselTypes,
  filteredFeeConfigs,
  feeConfigs,
  isLoading,
  onOpenAddFee,
  onEditFee,
  onDeleteFee,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel
        title="Bộ lọc cấu hình phí"
        onReset={resetFeeFilters}
        activeCount={feeFilterCount}
      >
        <FilterField label="Tên phí / loại tàu (chữ)">
          <input
            type="text"
            value={feeQ}
            onChange={(e) => setFeeQ(e.target.value)}
            placeholder="Lọc theo tên hoặc nhãn loại tàu..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Loại tàu (ID)">
          <select
            value={feeTypeId}
            onChange={(e) => setFeeTypeId(e.target.value)}
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
        <FilterField label="Áp dụng">
          <select
            value={feeActive}
            onChange={(e) => setFeeActive(e.target.value as 'all' | 'on' | 'off')}
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="on">Đang áp dụng</option>
            <option value="off">Tạm dừng</option>
          </select>
        </FilterField>
        <FilterField label="Từ ngày (tạo / cập nhật)">
          <input
            type="date"
            value={feeDateFrom}
            onChange={(e) => setFeeDateFrom(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Đến ngày">
          <input
            type="date"
            value={feeDateTo}
            onChange={(e) => setFeeDateTo(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
            Bảng Giá Cước Tàu
          </h3>
          <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1 max-w-xl leading-relaxed">
            <span className="font-bold text-gray-700 dark:text-gray-300">Tạm dừng áp dụng:</span>{' '}
            chỉnh sửa cấu hình và bỏ chọn «Đang áp dụng» — bản ghi vẫn còn, có thể bật lại.{' '}
            <span className="font-bold text-gray-700 dark:text-gray-300">Xóa:</span> nút trên thẻ — xóa
            hẳn khỏi hệ thống.
          </p>
        </div>
        <Button
          type="button"
          onClick={onOpenAddFee}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20 shrink-0 self-start sm:self-center"
        >
          <Plus className="w-4 h-4 mr-2" />
          Thêm Cấu Hình
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {isLoading && feeConfigs.length === 0 ? (
          <div className="col-span-full py-12 text-center">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
          </div>
        ) : filteredFeeConfigs.length > 0 ? (
          filteredFeeConfigs.map((fee) => (
            <div
              key={fee.id}
              className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4"
            >
              <div className="flex justify-between items-start">
                <div className="p-3 bg-blue-600/10 rounded-xl">
                  <DollarSign className="w-6 h-6 text-blue-600" />
                </div>
                <span
                  className={cn(
                    'text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter',
                    fee.is_active
                      ? 'bg-green-500/10 text-green-500'
                      : 'bg-gray-500/10 text-gray-500',
                  )}
                >
                  {fee.is_active ? 'Đang Áp Dụng' : 'Tạm Dừng'}
                </span>
              </div>
              <div>
                <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">
                  {fee.fee_name}
                </h4>
                <p className="text-[10px] text-gray-500 uppercase tracking-widest">
                  Loại tàu: {feeConfigVesselTypeLabel(fee, vesselTypes)}
                </p>
              </div>
              <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-between items-end gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] font-mono text-gray-400 uppercase">Giá Cước</p>
                  <p className="text-xl font-extrabold text-blue-600">
                    {formatFeeConfigDisplay(fee.base_fee, fee.unit)}
                  </p>
                </div>
                <div className="flex flex-col items-end gap-2 shrink-0">
                  <button
                    type="button"
                    onClick={() => onEditFee(fee)}
                    className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                  >
                    Chỉnh Sửa
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteFee(fee)}
                    disabled={isLoading}
                    className="inline-flex items-center gap-1 text-[10px] font-bold text-red-600/90 hover:text-red-500 uppercase tracking-widest transition-colors disabled:opacity-50"
                  >
                    <Trash2 className="w-3 h-3" />
                    Xóa
                  </button>
                </div>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
            {feeConfigs.length === 0
              ? 'Chưa có cấu hình phí nào'
              : 'Không có cấu hình phí khớp bộ lọc'}
          </div>
        )}
      </div>
    </div>
  );
};
