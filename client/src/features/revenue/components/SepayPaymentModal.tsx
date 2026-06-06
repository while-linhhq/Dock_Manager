import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Copy, Loader2 } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { InvoiceRead } from '../../../types/api.types';
import { revenueApi, type SepayBankInfo } from '../services/revenueApi';
import { InvoicePaymentSummary } from './InvoicePaymentSummary';
import { buildSepayQrUrl } from '../utils/sepay-payment-utils';

const POLL_INTERVAL_MS = 3000;

export type SepayPaymentModalProps = {
  isOpen: boolean;
  onClose: () => void;
  invoice: InvoiceRead | null;
  onPaid: () => void;
};

export const SepayPaymentModal: React.FC<SepayPaymentModalProps> = ({
  isOpen,
  onClose,
  invoice,
  onPaid,
}) => {
  const [bankInfo, setBankInfo] = useState<SepayBankInfo | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoadingBank, setIsLoadingBank] = useState(false);
  const [isPaid, setIsPaid] = useState(false);
  const [copied, setCopied] = useState(false);

  const amount = useMemo(() => {
    const n = Number(invoice?.total_amount ?? 0);
    return Number.isFinite(n) ? n : 0;
  }, [invoice?.total_amount]);

  const qrUrl = useMemo(() => {
    if (!bankInfo || !invoice?.invoice_number) {
      return null;
    }
    return buildSepayQrUrl(bankInfo, amount, invoice.invoice_number);
  }, [bankInfo, amount, invoice?.invoice_number]);

  const resetState = useCallback(() => {
    setBankInfo(null);
    setLoadError(null);
    setIsPaid(false);
    setCopied(false);
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetState();
      return;
    }
    if (!invoice) {
      return;
    }

    let cancelled = false;
    setIsLoadingBank(true);
    setLoadError(null);

    void revenueApi
      .getSepayBankInfo()
      .then((info) => {
        if (!cancelled) {
          setBankInfo(info);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : 'Không tải được thông tin ngân hàng';
          setLoadError(msg);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingBank(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, invoice, resetState]);

  useEffect(() => {
    if (!isOpen || !invoice || isPaid) {
      return;
    }

    const poll = () => {
      void revenueApi.getInvoicePaymentStatus(invoice.id).then((status) => {
        if (status.payment_status?.toUpperCase() === 'PAID') {
          setIsPaid(true);
          onPaid();
        }
      });
    };

    poll();
    const timer = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isOpen, invoice, isPaid, onPaid]);

  useEffect(() => {
    if (!isPaid || !isOpen) {
      return;
    }
    const timer = window.setTimeout(() => {
      onClose();
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [isPaid, isOpen, onClose]);

  const handleCopyDescription = async () => {
    if (!invoice?.invoice_number) {
      return;
    }
    try {
      await navigator.clipboard.writeText(invoice.invoice_number);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  if (!invoice) {
    return null;
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Thanh Toán Chuyển Khoản (SEPay)"
      className="max-w-md sm:max-w-lg"
    >
      {isPaid ? (
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <CheckCircle2 className="h-16 w-16 text-emerald-500" />
          <p className="text-sm font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            Thanh toán thành công
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Hóa đơn{' '}
            <span className="font-mono font-semibold">{invoice.invoice_number}</span> đã được ghi
            nhận.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          <InvoicePaymentSummary invoice={invoice} />

          {isLoadingBank ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          ) : null}

          {loadError ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
              {loadError}
            </p>
          ) : null}

          {bankInfo && !loadError ? (
            <>
              <BankDetails
                bankInfo={bankInfo}
                invoiceNumber={invoice.invoice_number}
                copied={copied}
                onCopy={handleCopyDescription}
              />
              {qrUrl ? (
                <div className="flex flex-col items-center gap-2">
                  <img
                    src={qrUrl}
                    alt="Mã QR chuyển khoản SEPay"
                    className="h-40 w-40 max-w-[min(10rem,42vw)] rounded-xl border border-gray-200 bg-white object-contain p-2 sm:h-44 sm:w-44 dark:border-white/10"
                  />
                  <p className="text-center text-[10px] text-gray-500">
                    Quét mã bằng app ngân hàng — nội dung CK phải đúng số hóa đơn
                  </p>
                </div>
              ) : null}
            </>
          ) : null}

          <div
            className={cn(
              'flex items-center justify-center gap-2 rounded-lg border border-amber-200/80',
              'bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/40',
              'dark:bg-amber-950/20 dark:text-amber-200',
            )}
          >
            <Loader2 className="h-4 w-4 shrink-0 animate-spin" />
            Đang chờ xác nhận thanh toán từ ngân hàng…
          </div>

          <div className="flex flex-col gap-2 pt-2 sm:flex-row">
            <Button type="button" variant="outline" onClick={onClose} className="flex-1">
              Đóng
            </Button>
          </div>
        </div>
      )}
    </Modal>
  );
};

function BankDetails({
  bankInfo,
  invoiceNumber,
  copied,
  onCopy,
}: {
  bankInfo: SepayBankInfo;
  invoiceNumber: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="space-y-2 text-sm">
      <div className="flex justify-between gap-4">
        <span className="text-gray-500">Ngân hàng</span>
        <span className="font-medium text-gray-900 dark:text-white">{bankInfo.bank_name}</span>
      </div>
      <div className="flex justify-between gap-4">
        <span className="text-gray-500">Số tài khoản</span>
        <span className="font-mono font-medium text-gray-900 dark:text-white">
          {bankInfo.bank_account}
        </span>
      </div>
      {bankInfo.account_name ? (
        <div className="flex justify-between gap-4">
          <span className="text-gray-500">Chủ tài khoản</span>
          <span className="font-medium text-gray-900 dark:text-white">{bankInfo.account_name}</span>
        </div>
      ) : null}
      <div className="flex items-center justify-between gap-2 pt-1">
        <span className="text-gray-500">Nội dung CK</span>
        <CopyField invoiceNumber={invoiceNumber} copied={copied} onCopy={onCopy} />
      </div>
    </div>
  );
}

function CopyField({
  invoiceNumber,
  copied,
  onCopy,
}: {
  invoiceNumber: string;
  copied: boolean;
  onCopy: () => void;
}) {
  return (
    <div className="flex items-center gap-2">
        <span className="font-mono text-xs font-semibold text-gray-900 dark:text-white">
          {invoiceNumber}
        </span>
        <button
          type="button"
          onClick={onCopy}
          className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:hover:bg-white/10 dark:hover:text-white"
          title="Sao chép nội dung chuyển khoản"
        >
          <Copy className="h-4 w-4" />
        </button>
        {copied ? (
          <span className="text-[10px] font-bold uppercase text-emerald-600">Đã copy</span>
        ) : null}
    </div>
  );
}
