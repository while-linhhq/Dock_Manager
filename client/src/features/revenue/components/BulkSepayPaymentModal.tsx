import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Copy, Loader2 } from 'lucide-react';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { InvoiceRead } from '../../../types/api.types';
import { ApiError } from '../../../services/httpClient';
import { revenueApi, type BulkSepaySessionRead, type SepayBankInfo } from '../services/revenueApi';
import { formatMoney } from './revenue-invoice-display';
import { buildSepayQrUrl } from '../utils/sepay-payment-utils';

const POLL_INTERVAL_MS = 3000;

export type BulkSepayPaymentModalProps = {
  isOpen: boolean;
  onClose: () => void;
  invoices: InvoiceRead[];
  hasActiveFilters: boolean;
  onPaid: () => void;
};

export const BulkSepayPaymentModal: React.FC<BulkSepayPaymentModalProps> = ({
  isOpen,
  onClose,
  invoices,
  hasActiveFilters,
  onPaid,
}) => {
  const [bankInfo, setBankInfo] = useState<SepayBankInfo | null>(null);
  const [session, setSession] = useState<BulkSepaySessionRead | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const isCompleted = session?.status === 'completed';

  const qrUrl = useMemo(() => {
    if (!bankInfo || !session?.reference_code) {
      return null;
    }
    const amount = Number(session.total_amount ?? 0);
    return buildSepayQrUrl(bankInfo, amount, session.reference_code);
  }, [bankInfo, session?.reference_code, session?.total_amount]);

  const invoiceIdsKey = useMemo(
    () => invoices.map((inv) => String(inv.id)).sort().join(','),
    [invoices],
  );

  const resetState = useCallback(() => {
    setBankInfo(null);
    setSession(null);
    setLoadError(null);
    setCopied(false);
  }, []);

  useEffect(() => {
    if (!isOpen) {
      resetState();
      return;
    }
    if (!invoiceIdsKey) {
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    setLoadError(null);

    const invoiceIds = invoiceIdsKey.split(',').map((id) => Number(id));

    void Promise.all([
      revenueApi.getSepayBankInfo(),
      revenueApi.createBulkSepaySession(invoiceIds),
    ])
      .then(([info, sess]) => {
        if (!cancelled) {
          setBankInfo(info);
          setSession(sess);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          const base =
            err instanceof Error ? err.message : 'Không tạo được phiên thanh toán gộp';
          const msg =
            err instanceof ApiError && (err.status === 405 || err.status === 404)
              ? `${base} — API chưa có endpoint bulk SEPay. Restart/deploy server backend mới rồi thử lại.`
              : base;
          setLoadError(msg);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isOpen, invoiceIdsKey, resetState]);

  useEffect(() => {
    if (!isOpen || !session?.reference_code || isCompleted) {
      return;
    }

    const poll = () => {
      void revenueApi.getBulkSepaySessionStatus(session.reference_code).then((next) => {
        setSession(next);
      });
    };

    poll();
    const timer = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [isOpen, session?.reference_code, isCompleted]);

  useEffect(() => {
    if (!isCompleted || !isOpen) {
      return;
    }
    onPaid();
    const timer = window.setTimeout(() => {
      onClose();
    }, 2500);
    return () => window.clearTimeout(timer);
  }, [isCompleted, isOpen, onPaid, onClose]);

  const handleCopy = async () => {
    if (!session?.reference_code) {
      return;
    }
    try {
      await navigator.clipboard.writeText(session.reference_code);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  if (invoices.length === 0) {
    return null;
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Thanh Toán Chuyển Khoản (SEPay)"
      className="max-w-md"
    >
      {isCompleted ? (
        <div className="flex flex-col items-center gap-4 py-6 text-center">
          <CheckCircle2 className="h-16 w-16 text-emerald-500" />
          <p className="text-sm font-bold uppercase tracking-widest text-emerald-600 dark:text-emerald-400">
            Thanh toán thành công
          </p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {session?.invoice_count ?? invoices.length} hóa đơn đã được ghi nhận.
          </p>
        </div>
      ) : (
        <div className="space-y-5">
          <div className="rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-white/5 dark:bg-white/5">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
              {hasActiveFilters ? 'Thanh toán gộp (theo bộ lọc)' : 'Thanh toán gộp'}
            </p>
            <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">
              <span className="font-bold text-gray-900 dark:text-white">
                {session?.invoice_count ?? invoices.length}
              </span>{' '}
              hóa đơn · một lần chuyển khoản
            </p>
            <p className="mt-2 text-lg font-bold text-blue-600 dark:text-blue-400">
              {formatMoney(session?.total_amount ?? 0)} ₫
            </p>
          </div>

          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
            </div>
          ) : null}

          {loadError ? (
            <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
              {loadError}
            </p>
          ) : null}

          {bankInfo && session && !loadError ? (
            <>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between gap-4">
                  <span className="text-gray-500">Ngân hàng</span>
                  <span className="font-medium text-gray-900 dark:text-white">
                    {bankInfo.bank_name}
                  </span>
                </div>
                <div className="flex justify-between gap-4">
                  <span className="text-gray-500">Số tài khoản</span>
                  <span className="font-mono font-medium text-gray-900 dark:text-white">
                    {bankInfo.bank_account}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2 pt-1">
                  <span className="text-gray-500">Nội dung CK</span>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-semibold text-gray-900 dark:text-white">
                      {session.reference_code}
                    </span>
                    <button
                      type="button"
                      onClick={() => void handleCopy()}
                      className="rounded-lg p-1.5 text-gray-500 hover:bg-gray-100 dark:hover:bg-white/10"
                      title="Sao chép nội dung chuyển khoản"
                    >
                      <Copy className="h-4 w-4" />
                    </button>
                    {copied ? (
                      <span className="text-[10px] font-bold uppercase text-emerald-600">
                        Đã copy
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>

              {qrUrl ? (
                <div className="flex flex-col items-center gap-2">
                  <img
                    src={qrUrl}
                    alt="Mã QR thanh toán gộp"
                    className="h-56 w-56 rounded-xl border border-gray-200 bg-white object-contain p-2 dark:border-white/10"
                  />
                  <p className="text-center text-[10px] text-gray-500">
                    Quét mã — chuyển đúng số tiền và nội dung CK ở trên
                  </p>
                </div>
              ) : null}

              <details className="text-xs text-gray-500 dark:text-gray-400">
                <summary className="cursor-pointer font-medium text-gray-700 dark:text-gray-300">
                  Danh sách hóa đơn ({session.invoice_count})
                </summary>
                <ul className="mt-2 max-h-32 space-y-1 overflow-y-auto font-mono">
                  {invoices.map((inv) => (
                    <li key={inv.id}>{inv.invoice_number}</li>
                  ))}
                </ul>
              </details>
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

          <Button type="button" variant="outline" onClick={onClose} className="w-full">
            Đóng
          </Button>
        </div>
      )}
    </Modal>
  );
};
