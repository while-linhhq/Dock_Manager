import React from 'react';
import { FileSpreadsheet, Loader2 } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';

export type RevenueExcelExportScope = 'all' | 'filtered';

export type RevenueExcelExportChoiceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  onExportAll: () => void;
  onExportFiltered: () => void;
  totalCount: number;
  filteredCount: number;
  tabCount: number;
  isExporting: boolean;
};

export const RevenueExcelExportChoiceModal: React.FC<RevenueExcelExportChoiceModalProps> = ({
  isOpen,
  onClose,
  onExportAll,
  onExportFiltered,
  totalCount,
  filteredCount,
  tabCount,
  isExporting,
}) => {
  const allLabel =
    totalCount > 0 ? `Xuất tất cả (${totalCount})` : 'Xuất tất cả (đang tải…)';
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Xuất Excel">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-white/5 dark:bg-white/5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            Chọn phạm vi xuất
          </p>
          <p className="mt-2 text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
            <span className="font-bold text-gray-900 dark:text-white">Tất cả:</span>{' '}
            toàn bộ hóa đơn tạo tay + tự động, mọi trạng thái (chờ / đã thanh toán / đã xóa), từ
            trước tới nay
            {totalCount > 0 ? (
              <>
                {' '}
                — <span className="font-bold">{totalCount}</span> hóa đơn
              </>
            ) : null}
          </p>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Tab hiện tại: {tabCount} hóa đơn · Khớp filter: {filteredCount}
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Button
            type="button"
            variant="outline"
            onClick={onExportAll}
            disabled={isExporting || totalCount === 0}
            className={cn(
              'h-full rounded-2xl border-emerald-500/40',
              'text-emerald-700 dark:text-emerald-300',
            )}
          >
            {isExporting ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <FileSpreadsheet className="w-4 h-4 mr-2" />
            )}
            {allLabel}
          </Button>

          <Button
            type="button"
            variant="outline"
            onClick={onExportFiltered}
            disabled={isExporting || filteredCount === 0}
            className={cn(
              'h-full rounded-2xl border-emerald-500/40',
              'text-emerald-700 dark:text-emerald-300',
            )}
          >
            {isExporting ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <FileSpreadsheet className="w-4 h-4 mr-2" />
            )}
            Xuất theo filter ({filteredCount})
          </Button>
        </div>

        <div className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
          «Xuất theo filter» chỉ gồm hóa đơn đang hiển thị trên tab và bộ lọc hiện tại.
        </div>
      </div>
    </Modal>
  );
};

