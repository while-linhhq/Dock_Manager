import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { VesselRead } from '../../../types/api.types';
import type { OrderCreate } from '../services/ordersApi';
import { statusLabels } from '../utils/order-status-display';

export type OrderFormModalProps = {
  isOpen: boolean;
  onClose: () => void;
  form: UseFormReturn<OrderCreate>;
  onSubmit: (data: OrderCreate) => void | Promise<void>;
  editingId: string | null;
  vessels: VesselRead[];
  isLoading: boolean;
};

export const OrderFormModal: React.FC<OrderFormModalProps> = ({
  isOpen,
  onClose,
  form,
  onSubmit,
  editingId,
  vessels,
  isLoading,
}) => {
  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editingId ? 'Chỉnh Sửa Đơn Hàng' : 'Tạo Đơn Hàng Mới'}
    >
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <div className="space-y-1">
          <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
            Tàu Cập Cảng
          </label>
          <select
            {...form.register('vessel_id')}
            className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
          >
            <option value="">Chọn tàu...</option>
            {vessels.map((v) => (
              <option key={v.id} value={v.id}>
                {v.ship_id} - {v.name}
              </option>
            ))}
          </select>
          {form.formState.errors.vessel_id && (
            <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">
              {form.formState.errors.vessel_id.message}
            </p>
          )}
        </div>
        <div className="space-y-1">
          <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
            Chi Tiết Hàng Hóa
          </label>
          <textarea
            {...form.register('cargo_details')}
            className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all min-h-[80px]"
            placeholder="Nhập thông tin hàng hóa..."
          />
        </div>
        <Input
          label="Tổng Số Tiền (VNĐ)"
          type="number"
          {...form.register('total_amount', { valueAsNumber: true })}
          error={form.formState.errors.total_amount?.message}
        />
        <div className="space-y-1">
          <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
            Trạng Thái
          </label>
          <select
            {...form.register('status')}
            className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
          >
            {Object.entries(statusLabels).map(([val, label]) => (
              <option key={val} value={val}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="pt-4 flex space-x-3">
          <Button type="button" variant="outline" onClick={onClose} className="flex-1">
            Hủy
          </Button>
          <Button
            type="submit"
            disabled={isLoading}
            className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
          >
            {isLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : editingId ? (
              'Cập Nhật'
            ) : (
              'Tạo Đơn'
            )}
          </Button>
        </div>
      </form>
    </Modal>
  );
};
