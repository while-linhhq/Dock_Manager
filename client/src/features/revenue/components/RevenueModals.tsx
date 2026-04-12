import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { VesselTypeRead } from '../../../types/api.types';
import type { InvoiceCreate, PaymentCreate } from '../services/revenueApi';
import type { FeeFormValues } from '../revenue-schemas';
import {
  FEE_BILLING_UNIT_AMOUNT_LABELS,
  FEE_BILLING_UNIT_LABELS,
  FEE_BILLING_UNITS,
  normalizeFeeBillingUnit,
} from '../../../utils/fee-billing-unit';
import type { OrderRead } from '../../../types/api.types';

export type RevenueModalsProps = {
  isInvoiceModalOpen: boolean;
  onCloseInvoice: () => void;
  invoiceForm: UseFormReturn<InvoiceCreate>;
  onInvoiceSubmit: (data: InvoiceCreate) => void | Promise<void>;
  orders: OrderRead[];
  isPaymentModalOpen: boolean;
  onClosePayment: () => void;
  paymentForm: UseFormReturn<PaymentCreate>;
  onPaymentSubmit: (data: PaymentCreate) => void | Promise<void>;
  isFeeModalOpen: boolean;
  onCloseFee: () => void;
  feeForm: UseFormReturn<FeeFormValues>;
  onFeeSubmit: (data: FeeFormValues) => void | Promise<void>;
  editingFeeId: string | number | null;
  vesselTypes: VesselTypeRead[];
  feeUnit: FeeFormValues['unit'];
  isLoading: boolean;
};

export const RevenueModals: React.FC<RevenueModalsProps> = ({
  isInvoiceModalOpen,
  onCloseInvoice,
  invoiceForm,
  onInvoiceSubmit,
  orders,
  isPaymentModalOpen,
  onClosePayment,
  paymentForm,
  onPaymentSubmit,
  isFeeModalOpen,
  onCloseFee,
  feeForm,
  onFeeSubmit,
  editingFeeId,
  vesselTypes,
  feeUnit,
  isLoading,
}) => {
  return (
    <>
      <Modal isOpen={isInvoiceModalOpen} onClose={onCloseInvoice} title="Tạo Hóa Đơn Mới">
        <form onSubmit={invoiceForm.handleSubmit(onInvoiceSubmit)} className="space-y-4">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Đơn Hàng
            </label>
            <select
              {...invoiceForm.register('order_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn đơn hàng...</option>
              {orders.map((o) => (
                <option key={o.id} value={String(o.id)}>
                  {String(o.id).split('-')[0]} - {o.vessel?.name}
                </option>
              ))}
            </select>
            {invoiceForm.formState.errors.order_id && (
              <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">
                {invoiceForm.formState.errors.order_id.message}
              </p>
            )}
          </div>

          <div className="space-y-3">
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest ml-1">
              Chi Tiết Hạng Mục
            </p>
            {invoiceForm.watch('items').map((_, index) => (
              <div key={index} className="grid grid-cols-12 gap-2">
                <div className="col-span-6">
                  <Input
                    placeholder="Mô tả"
                    {...invoiceForm.register(`items.${index}.description` as const)}
                  />
                </div>
                <div className="col-span-2">
                  <Input
                    type="number"
                    placeholder="SL"
                    {...invoiceForm.register(`items.${index}.quantity` as const, {
                      valueAsNumber: true,
                    })}
                  />
                </div>
                <div className="col-span-4">
                  <Input
                    type="number"
                    placeholder="Đơn giá"
                    {...invoiceForm.register(`items.${index}.unit_price` as const, {
                      valueAsNumber: true,
                    })}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseInvoice} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Tạo Hóa Đơn'}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal isOpen={isPaymentModalOpen} onClose={onClosePayment} title="Ghi Nhận Thanh Toán">
        <form onSubmit={paymentForm.handleSubmit(onPaymentSubmit)} className="space-y-4">
          <Input
            label="Số Tiền"
            type="number"
            {...paymentForm.register('amount', { valueAsNumber: true })}
            error={paymentForm.formState.errors.amount?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Phương Thức
            </label>
            <select
              {...paymentForm.register('payment_method')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="transfer">Chuyển Khoản</option>
              <option value="cash">Tiền Mặt</option>
              <option value="card">Thẻ Tín Dụng</option>
            </select>
          </div>
          <Input
            label="Mã Tham Chiếu"
            placeholder="VD: Mã giao dịch ngân hàng"
            {...paymentForm.register('reference_number')}
          />
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onClosePayment} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                'Xác Nhận Thanh Toán'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={isFeeModalOpen}
        onClose={onCloseFee}
        title={editingFeeId ? 'Chỉnh Sửa Cấu Hình Phí' : 'Thêm Cấu Hình Phí Mới'}
      >
        <form onSubmit={feeForm.handleSubmit(onFeeSubmit)} className="space-y-4">
          <Input
            label="Tên Phí"
            placeholder="VD: Phí Cập Cảng"
            {...feeForm.register('fee_name')}
            error={feeForm.formState.errors.fee_name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Loại Tàu Áp Dụng
            </label>
            <select
              {...feeForm.register('vessel_type_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn loại tàu...</option>
              {vesselTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.type_name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Đơn vị tính phí
            </label>
            <select
              {...feeForm.register('unit')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm dark:text-white transition-all"
            >
              {FEE_BILLING_UNITS.map((u) => (
                <option key={u} value={u}>
                  {FEE_BILLING_UNIT_LABELS[u]}
                </option>
              ))}
            </select>
          </div>
          <Input
            label={
              FEE_BILLING_UNIT_AMOUNT_LABELS[
                normalizeFeeBillingUnit(feeUnit) as keyof typeof FEE_BILLING_UNIT_AMOUNT_LABELS
              ]
            }
            type="number"
            disabled={feeUnit === 'none'}
            {...feeForm.register('base_fee', { valueAsNumber: true })}
            error={feeForm.formState.errors.base_fee?.message}
          />
          {feeUnit === 'none' && (
            <p className="text-[10px] text-gray-500 ml-1">
              Mức phí cố định 0 — áp dụng cho tàu công ty / miễn phí.
            </p>
          )}
          <div className="space-y-1.5 ml-1">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="fee_is_active"
                {...feeForm.register('is_active')}
                className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <label
                htmlFor="fee_is_active"
                className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
              >
                Đang áp dụng (định giá / hiển thị phí tham chiếu)
              </label>
            </div>
            <p className="text-[10px] text-gray-500 dark:text-gray-400 pl-6 leading-relaxed">
              Bỏ chọn = tạm ngừng, bản ghi vẫn lưu. Để gỡ hoàn toàn, dùng nút «Xóa» trên thẻ cấu hình
              (xóa vĩnh viễn trong cơ sở dữ liệu).
            </p>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseFee} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : editingFeeId ? (
                'Cập Nhật'
              ) : (
                'Thêm Mới'
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};
