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
import type { InvoiceRead, OrderRead } from '../../../types/api.types';
import { InvoicePaymentSummary } from './InvoicePaymentSummary';
import { FeeOperatingHoursEditor } from './FeeOperatingHoursEditor';
import type { OperatingHours } from '../types/fee-operating-hours';
import {
  FeeField,
  FeeSection,
  feeControlClass,
  feeErrorClass,
  feeMonoControlClass,
} from './fee-config-form-ui';

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
  paymentModalTitle?: string;
  lockPaymentMethod?: 'cash';
  paymentInvoice?: InvoiceRead | null;
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
  paymentModalTitle = 'Ghi Nhận Thanh Toán',
  lockPaymentMethod,
  paymentInvoice = null,
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

      <Modal
        isOpen={isPaymentModalOpen}
        onClose={onClosePayment}
        title={paymentModalTitle}
        className="max-w-md sm:max-w-lg"
      >
        <form onSubmit={paymentForm.handleSubmit(onPaymentSubmit)} className="space-y-3">
          {paymentInvoice ? <InvoicePaymentSummary invoice={paymentInvoice} /> : null}
          <Input
            label="Số Tiền"
            type="number"
            {...paymentForm.register('amount', { valueAsNumber: true })}
            error={paymentForm.formState.errors.amount?.message}
          />
          {lockPaymentMethod === 'cash' ? (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 px-4 py-3 dark:border-emerald-500/30 dark:bg-emerald-500/10">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
                Phương thức
              </p>
              <p className="mt-1 text-sm font-bold text-emerald-700 dark:text-emerald-400">
                Tiền mặt
              </p>
            </div>
          ) : (
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
          )}
          {lockPaymentMethod !== 'cash' ? (
            <Input
              label="Mã Tham Chiếu"
              placeholder="VD: Mã giao dịch ngân hàng"
              {...paymentForm.register('reference_number')}
            />
          ) : null}
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
        className="max-w-[min(100vw-1.5rem,40rem)]"
        bodyClassName="flex min-h-0 flex-1 flex-col overflow-hidden p-0"
      >
        <form
          onSubmit={feeForm.handleSubmit(onFeeSubmit)}
          className="flex min-h-0 flex-1 flex-col"
        >
          <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <FeeSection title="Thông tin phí">
            <FeeField
              label="Tên phí"
              error={feeForm.formState.errors.fee_name?.message}
            >
              <input
                type="text"
                placeholder="VD: Phí cập cảng"
                className={feeControlClass}
                {...feeForm.register('fee_name')}
              />
            </FeeField>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <FeeField label="Loại tàu">
                <select
                  {...feeForm.register('vessel_type_id')}
                  className={feeControlClass}
                >
                  <option value="">Chọn loại tàu...</option>
                  {vesselTypes.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.type_name}
                    </option>
                  ))}
                </select>
              </FeeField>
              <FeeField label="Đơn vị phí">
                <select {...feeForm.register('unit')} className={feeControlClass}>
                  {FEE_BILLING_UNITS.map((u) => (
                    <option key={u} value={u}>
                      {FEE_BILLING_UNIT_LABELS[u]}
                    </option>
                  ))}
                </select>
              </FeeField>
              <FeeField
                label={
                  FEE_BILLING_UNIT_AMOUNT_LABELS[
                    normalizeFeeBillingUnit(feeUnit) as keyof typeof FEE_BILLING_UNIT_AMOUNT_LABELS
                  ]
                }
                error={feeForm.formState.errors.base_fee?.message}
              >
                <input
                  type="number"
                  disabled={feeUnit === 'none'}
                  className={feeMonoControlClass}
                  {...feeForm.register('base_fee', { valueAsNumber: true })}
                />
              </FeeField>
            </div>
          </FeeSection>

          <FeeSection title="Giới hạn & phạt">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <FeeField label="Số lượng">
                <input
                  type="number"
                  min={1}
                  placeholder="∞"
                  title="Để trống = không giới hạn"
                  className={feeMonoControlClass}
                  {...feeForm.register('berth_limit_count', { valueAsNumber: true })}
                />
              </FeeField>
              <FeeField label="Đơn vị">
                <select
                  {...feeForm.register('berth_limit_unit')}
                  className={feeControlClass}
                >
                  <option value="">—</option>
                  <option value="day">Ngày</option>
                  <option value="month">Tháng</option>
                </select>
              </FeeField>
              <FeeField label="Phạt vượt (₫)">
                <input
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="0"
                  className={feeMonoControlClass}
                  {...feeForm.register('over_limit_penalty_amount', { valueAsNumber: true })}
                />
              </FeeField>
              <FeeField
                label="Phạt ngoài giờ (₫)"
                error={feeForm.formState.errors.outside_hours_penalty_amount?.message}
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="0"
                  className={feeMonoControlClass}
                  {...feeForm.register('outside_hours_penalty_amount', { valueAsNumber: true })}
                />
              </FeeField>
            </div>
            {(feeForm.formState.errors.berth_limit_count ||
              feeForm.formState.errors.berth_limit_unit ||
              feeForm.formState.errors.over_limit_penalty_amount) && (
              <p className={feeErrorClass}>
                {feeForm.formState.errors.berth_limit_count?.message ||
                  feeForm.formState.errors.berth_limit_unit?.message ||
                  feeForm.formState.errors.over_limit_penalty_amount?.message}
              </p>
            )}
          </FeeSection>

          <FeeSection title="Giờ neo đậu">
            <FeeOperatingHoursEditor
              value={(feeForm.watch('operating_hours') ?? {}) as OperatingHours}
              onChange={(next) =>
                feeForm.setValue('operating_hours', next, { shouldValidate: true })
              }
              disabled={isLoading}
            />
          </FeeSection>
          </div>

          <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-gray-200 bg-white px-4 py-3 dark:border-white/10 dark:bg-[#121214]">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                id="fee_is_active"
                {...feeForm.register('is_active')}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                Đang áp dụng
              </span>
            </label>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={onCloseFee} className="min-w-[5.5rem]">
                Hủy
              </Button>
              <Button
                type="submit"
                disabled={isLoading}
                className="min-w-[5.5rem] bg-blue-600 text-white hover:bg-blue-700"
              >
                {isLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : editingFeeId ? (
                  'Cập Nhật'
                ) : (
                  'Thêm Mới'
                )}
              </Button>
            </div>
          </div>
        </form>
      </Modal>
    </>
  );
};
