import React, { useEffect } from 'react';
import { useDiscountApprovalStore } from '../store/discountApprovalStore';
import { DiscountApprovalSection } from '../components/DiscountApprovalSection';

export const DiscountApprovalView: React.FC = () => {
  const {
    requests,
    statusTab,
    isLoading,
    error,
    setStatusTab,
    fetchRequests,
    approveRequest,
    rejectRequest,
  } = useDiscountApprovalStore();

  useEffect(() => {
    void fetchRequests();
  }, [fetchRequests]);

  return (
    <div className="space-y-4 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div>
        <h2 className="text-lg font-bold text-gray-900 dark:text-white">Duyệt giảm giá</h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Xem và phê duyệt yêu cầu giảm giá trên hóa đơn trước khi áp dụng vào thanh toán.
        </p>
      </div>
      {error ? (
        <p className="rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-600 dark:text-rose-400">
          {error}
        </p>
      ) : null}
      <DiscountApprovalSection
        statusTab={statusTab}
        onStatusTab={setStatusTab}
        requests={requests}
        isLoading={isLoading}
        onApprove={approveRequest}
        onReject={rejectRequest}
      />
    </div>
  );
};
