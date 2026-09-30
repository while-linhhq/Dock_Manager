import React from 'react';
import { Banknote, QrCode } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { formatMoney } from './revenue-invoice-display';
import { PageScopeNotice } from './PageScopeNotice';
import type { PaymentMethodChoice } from './PaymentMethodChoiceModal';

export type BulkPaymentMethodChoiceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  invoiceCount: number;
  totalAmount: number;
  hasActiveFilters: boolean;
  /**
   * Tổng số hoá đơn chờ thanh toán khớp tab + bộ lọc hiện tại (server trả qua
   * `X-Total-Count`). Lớn hơn `invoiceCount` nghĩa là danh sách chỉ tải được một
   * trang → hộp thoại phải nói rõ phạm vi thay vì ngụ ý toàn bộ tập lọc.
   */
  filteredTotal?: number;
  onSelect: (method: PaymentMethodChoice) => void;
};

export const BulkPaymentMethodChoiceModal: React.FC<BulkPaymentMethodChoiceModalProps> = ({
  isOpen,
  onClose,
  invoiceCount,
  totalAmount,
  hasActiveFilters,
  filteredTotal,
  onSelect,
}) => {
  const isPageScoped = typeof filteredTotal === 'number' && filteredTotal > invoiceCount;
  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Chọn Phương Thức Thanh Toán">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-white/5 dark:bg-white/5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
            {isPageScoped
              ? hasActiveFilters
                ? 'Thanh toán theo bộ lọc (trang hiện tại)'
                : 'Thanh toán theo trang hiện tại'
              : hasActiveFilters
                ? 'Thanh toán tất cả (theo bộ lọc)'
                : 'Thanh toán tất cả'}
          </p>
          <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
            <span className="font-bold text-gray-900 dark:text-white">{invoiceCount}</span> hóa
            đơn chờ thanh toán{isPageScoped ? ' trên trang này' : ''}
          </p>
          <p className="mt-2 text-lg font-bold text-blue-600 dark:text-blue-400">
            {formatMoney(totalAmount)} ₫
          </p>
        </div>

        <PageScopeNotice
          shownCount={invoiceCount}
          filteredTotal={filteredTotal ?? invoiceCount}
          action="payment"
        />

        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelect('transfer')}
            disabled={invoiceCount === 0}
            className={cn(
              'flex flex-col items-start gap-3 rounded-2xl border p-5 text-left transition-all',
              'border-blue-200 bg-blue-50/50 hover:border-blue-400 hover:bg-blue-50',
              'dark:border-blue-500/30 dark:bg-blue-500/10 dark:hover:border-blue-400/50',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            <div className="rounded-xl bg-blue-600 p-2.5 text-white shadow-lg shadow-blue-600/20">
              <QrCode className="h-5 w-5" />
            </div>
            <p className="text-sm font-bold text-gray-900 dark:text-white">Chuyển khoản</p>
            <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
              Một mã QR cho tổng tiền — nội dung CK mã gộp. Tự xác nhận qua SEPay khi khách chuyển.
            </p>
          </button>

          <button
            type="button"
            onClick={() => onSelect('cash')}
            disabled={invoiceCount === 0}
            className={cn(
              'flex flex-col items-start gap-3 rounded-2xl border p-5 text-left transition-all',
              'border-emerald-200 bg-emerald-50/50 hover:border-emerald-400 hover:bg-emerald-50',
              'dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:hover:border-emerald-400/50',
              'disabled:cursor-not-allowed disabled:opacity-50',
            )}
          >
            <div className="rounded-xl bg-emerald-600 p-2.5 text-white shadow-lg shadow-emerald-600/20">
              <Banknote className="h-5 w-5" />
            </div>
            <p className="text-sm font-bold text-gray-900 dark:text-white">Tiền mặt</p>
            <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
              Xác nhận thủ công sau khi đã thu tiền mặt tại quầy.
            </p>
          </button>
        </div>
      </div>
    </Modal>
  );
};
