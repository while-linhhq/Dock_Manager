import React, { useEffect, useState } from 'react';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';

export type DiscountRejectModalProps = {
  isOpen: boolean;
  invoiceNumber: string | null;
  isLoading: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
};

export const DiscountRejectModal: React.FC<DiscountRejectModalProps> = ({
  isOpen,
  invoiceNumber,
  isLoading,
  onClose,
  onConfirm,
}) => {
  const [reason, setReason] = useState('');

  useEffect(() => {
    if (!isOpen) {
      setReason('');
    }
  }, [isOpen]);

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="Từ chối giảm giá">
      <div className="space-y-4">
        <p className="text-sm text-gray-600 dark:text-gray-300">
          Hóa đơn{' '}
          <span className="font-mono font-semibold text-gray-900 dark:text-white">
            {invoiceNumber ?? '—'}
          </span>
        </p>
        <div>
          <label className="mb-1 block text-[10px] font-bold uppercase tracking-widest text-gray-500">
            Lý do (tuỳ chọn)
          </label>
          <textarea
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2 text-sm text-gray-900 outline-none focus:border-rose-500 focus:ring-1 focus:ring-rose-500/30 dark:border-white/10 dark:bg-[#1a1a1e] dark:text-white"
            placeholder="Nhập lý do từ chối..."
          />
        </div>
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
            Hủy
          </Button>
          <Button
            type="button"
            onClick={() => onConfirm(reason)}
            disabled={isLoading}
            className="bg-rose-600 hover:bg-rose-700 text-white"
          >
            Từ chối
          </Button>
        </div>
      </div>
    </Modal>
  );
};
