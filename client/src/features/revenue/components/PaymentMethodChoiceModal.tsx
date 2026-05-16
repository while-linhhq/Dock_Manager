import React from 'react';
import { Banknote, QrCode } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import type { InvoiceRead } from '../../../types/api.types';
import { formatMoney } from './revenue-invoice-display';

export type PaymentMethodChoice = 'transfer' | 'cash';

export type PaymentMethodChoiceModalProps = {
  isOpen: boolean;
  onClose: () => void;
  invoice: InvoiceRead | null;
  onSelect: (method: PaymentMethodChoice) => void;
};

export const PaymentMethodChoiceModal: React.FC<PaymentMethodChoiceModalProps> = ({
  isOpen,
  onClose,
  invoice,
  onSelect,
}) => {
  if (!invoice) {
    return null;
  }

  const amount = Number(invoice.total_amount ?? 0);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Chọn Phương Thức Thanh Toán">
      <div className="space-y-4">
        <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-white/5 dark:bg-white/5">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">Hóa đơn</p>
          <p className="mt-1 font-mono text-sm font-bold text-gray-900 dark:text-white">
            {invoice.invoice_number}
          </p>
          <p className="mt-2 text-lg font-bold text-blue-600 dark:text-blue-400">
            {formatMoney(amount)} ₫
          </p>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <button
            type="button"
            onClick={() => onSelect('transfer')}
            className={cn(
              'flex flex-col items-start gap-3 rounded-2xl border p-5 text-left transition-all',
              'border-blue-200 bg-blue-50/50 hover:border-blue-400 hover:bg-blue-50',
              'dark:border-blue-500/30 dark:bg-blue-500/10 dark:hover:border-blue-400/50',
            )}
          >
            <div className="rounded-xl bg-blue-600 p-2.5 text-white shadow-lg shadow-blue-600/20">
              <QrCode className="h-5 w-5" />
            </div>
            <p className="text-sm font-bold text-gray-900 dark:text-white">Chuyển khoản</p>
            <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
              QR + thông tin CK. Tự xác nhận qua webhook SEPay khi khách chuyển tiền.
            </p>
          </button>

          <button
            type="button"
            onClick={() => onSelect('cash')}
            className={cn(
              'flex flex-col items-start gap-3 rounded-2xl border p-5 text-left transition-all',
              'border-emerald-200 bg-emerald-50/50 hover:border-emerald-400 hover:bg-emerald-50',
              'dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:hover:border-emerald-400/50',
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
