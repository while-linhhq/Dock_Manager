import React from 'react';
import { DollarSign, FileSpreadsheet, Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import type { FeeConfigRead, VesselTypeRead } from '../../../types/api.types';
import { formatFeeConfigDisplay } from '../../../utils/fee-billing-unit';
import { summarizeOperatingHours, operatingHoursFromApi } from '../types/fee-operating-hours';
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
  onExportExcel: () => void;
  isExporting: boolean;
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
  onExportExcel,
  isExporting,
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

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs sm:text-sm text-gray-500 dark:text-gray-400">
          Xuất Excel theo bộ lọc —{' '}
          <span className="font-semibold text-gray-700 dark:text-gray-200">
            {filteredFeeConfigs.length}
          </span>{' '}
          cấu hình phí
        </p>
        <Button
          type="button"
          variant="outline"
          onClick={onExportExcel}
          disabled={isExporting || filteredFeeConfigs.length === 0}
          className="border-emerald-500/50 text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10 shrink-0 disabled:opacity-50"
        >
          {isExporting ? (
            <Loader2 className="w-4 h-4 mr-2 animate-spin" />
          ) : (
            <FileSpreadsheet className="w-4 h-4 mr-2" />
          )}
          Xuất Excel
        </Button>
      </div>

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
                {fee.berth_limit_count != null && fee.berth_limit_count > 0 && fee.berth_limit_unit ? (
                  <p className="text-[10px] text-orange-600 dark:text-orange-400 uppercase tracking-widest mt-1">
                    Giới hạn mỗi tàu: {fee.berth_limit_count} lần/
                    {fee.berth_limit_unit === 'day' ? 'ngày' : 'tháng'}
                  </p>
                ) : null}
                {fee.over_limit_penalty_amount != null && Number(fee.over_limit_penalty_amount) > 0 ? (
                  <p className="text-[10px] text-rose-600 dark:text-rose-400 tracking-widest mt-1">
                    Phạt vượt giới hạn: {Number(fee.over_limit_penalty_amount).toLocaleString('vi-VN')} ₫/lượt
                  </p>
                ) : null}
                {fee.operating_hours ? (
                  <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1 leading-snug">
                    Giờ neo: {summarizeOperatingHours(operatingHoursFromApi(fee.operating_hours))}
                  </p>
                ) : null}
                {fee.outside_hours_penalty_amount != null &&
                Number(fee.outside_hours_penalty_amount) > 0 ? (
                  <p className="text-[10px] text-violet-600 dark:text-violet-400 tracking-widest mt-1">
                    Phạt ngoài giờ: {Number(fee.outside_hours_penalty_amount).toLocaleString('vi-VN')} ₫/lượt
                  </p>
                ) : null}
              </div>
              <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-between items-end gap-3">
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] font-mono text-gray-400 uppercase">Giá Cước</p>
                  <p className="text-xl font-extrabold text-blue-600">
                    {formatFeeConfigDisplay(fee.base_fee, fee.unit)}
                  </p>
                </div>
                <div className="flex items-end gap-1 shrink-0">
                  <button
                    type="button"
                    onClick={() => onEditFee(fee)}
                    className={cn(
                      'p-2 rounded-lg transition-colors',
                      'text-gray-500 hover:text-blue-600 hover:bg-blue-50 dark:text-gray-400 dark:hover:text-blue-400 dark:hover:bg-blue-500/10',
                    )}
                    title="Chỉnh sửa"
                    aria-label="Chỉnh sửa"
                  >
                    <Pencil className="w-4 h-4" />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeleteFee(fee)}
                    disabled={isLoading}
                    className={cn(
                      'p-2 rounded-lg transition-colors',
                      'text-red-600 hover:text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10 disabled:opacity-50',
                    )}
                    title="Xóa"
                    aria-label="Xóa"
                  >
                    <Trash2 className="w-4 h-4" />
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
