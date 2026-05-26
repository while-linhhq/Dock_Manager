import React from 'react';
import { Banknote, Loader2 } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';
import { formatMoney } from './revenue-invoice-display';

export type BulkPaymentConfirmModalProps = {
  isOpen: boolean;
  onClose: () => void;
  invoiceCount: number;
  totalAmount: number;
  hasActiveFilters: boolean;
  isLoading: boolean;
  onConfirm: () => void;
};

export const BulkPaymentConfirmModal: React.FC<BulkPaymentConfirmModalProps> = ({
  isOpen,
  onClose,
  invoiceCount,
  totalAmount,
  hasActiveFilters,
  isLoading,
  onConfirm,
}) => {
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Thanh Toán Tiền Mặt">
      <div className="space-y-4">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4 dark:border-emerald-500/30 dark:bg-emerald-500/10">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            {hasActiveFilters ? 'Theo bộ lọc hiện tại' : 'Tất cả hóa đơn chờ thanh toán'}
          </p>
          <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="font-bold text-gray-900 dark:text-white">{invoiceCount}</span> hóa đơn
          </p>
          <p className="mt-3 text-2xl font-bold text-emerald-700 dark:text-emerald-400">
            {formatMoney(totalAmount)} ₫
          </p>
        </div>

        <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
          Ghi nhận thanh toán đủ số tiền còn lại cho từng hóa đơn (kể cả thanh toán một phần).
        </p>

        <div className="flex gap-3 pt-2">
          <Button type="button" variant="outline" onClick={onClose} className="flex-1" disabled={isLoading}>
            Hủy
          </Button>
          <Button
            type="button"
            onClick={onConfirm}
            disabled={isLoading || invoiceCount === 0}
            className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <>
                <Banknote className="mr-2 h-4 w-4 inline" />
                Xác Nhận Thanh Toán
              </>
            )}
          </Button>
        </div>
      </div>
    </Modal>
  );
};
