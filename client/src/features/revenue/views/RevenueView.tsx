import React, { useEffect, useState } from 'react';
import { 
  Wallet, 
  FileText, 
  Settings, 
  Plus, 
  Search, 
  Filter, 
  CheckCircle2, 
  Clock, 
  AlertCircle,
  Loader2,
  DollarSign
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { useRevenueStore } from '../store/revenueStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import { useOrderStore } from '../../orders/store/orderStore';
import type { InvoiceCreate, PaymentCreate, FeeConfigCreate } from '../services/revenueApi';

const invoiceSchema = z.object({
  order_id: z.string().min(1, 'Mã đơn hàng là bắt buộc'),
  items: z.array(z.object({
    description: z.string().min(1, 'Mô tả là bắt buộc'),
    quantity: z.number().min(1, 'Số lượng ít nhất là 1'),
    unit_price: z.number().min(0, 'Đơn giá không được âm'),
  })).min(1, 'Cần ít nhất một hạng mục'),
});

const paymentSchema = z.object({
  amount: z.number().min(1, 'Số tiền thanh toán phải lớn hơn 0'),
  payment_method: z.string().min(1, 'Phương thức thanh toán là bắt buộc'),
  reference_number: z.string().optional(),
  notes: z.string().optional(),
});

const feeSchema = z.object({
  name: z.string().min(1, 'Tên phí là bắt buộc'),
  vessel_type_id: z.string().min(1, 'Loại tàu là bắt buộc'),
  fee_amount: z.number().min(0, 'Mức phí không được âm'),
  is_active: z.boolean().default(true),
});

const paymentStatusColors: Record<string, string> = {
  'paid': 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  'partial': 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  'unpaid': 'text-amber-500 bg-amber-500/10 border-amber-500/20',
};

const paymentStatusLabels: Record<string, string> = {
  'paid': 'Đã Thanh Toán',
  'partial': 'Thanh Toán Một Phần',
  'unpaid': 'Chưa Thanh Toán',
};

export const RevenueView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'invoices' | 'fees'>('invoices');
  const [isInvoiceModalOpen, setIsInvoiceModalOpen] = useState(false);
  const [isPaymentModalOpen, setIsPaymentModalOpen] = useState(false);
  const [isFeeModalOpen, setIsFeeModalOpen] = useState(false);
  const [selectedInvoiceId, setSelectedInvoiceId] = useState<string | null>(null);
  const [editingFeeId, setEditingFeeId] = useState<string | null>(null);

  const { 
    invoices, feeConfigs, isLoading, 
    fetchInvoices, fetchFeeConfigs, 
    createInvoice, recordPayment, upsertFeeConfig 
  } = useRevenueStore();
  
  const { vesselTypes, fetchVesselTypes } = useVesselStore();
  const { orders, fetchOrders } = useOrderStore();

  const invoiceForm = useForm<InvoiceCreate>({
    resolver: zodResolver(invoiceSchema),
    defaultValues: { items: [{ description: '', quantity: 1, unit_price: 0 }] }
  });

  const paymentForm = useForm<PaymentCreate>({
    resolver: zodResolver(paymentSchema)
  });

  const feeForm = useForm<FeeConfigCreate>({
    resolver: zodResolver(feeSchema),
    defaultValues: { is_active: true }
  });

  useEffect(() => {
    if (activeTab === 'invoices') {
      fetchInvoices();
      fetchOrders();
    } else {
      fetchFeeConfigs();
      fetchVesselTypes();
    }
  }, [activeTab, fetchInvoices, fetchFeeConfigs, fetchOrders, fetchVesselTypes]);

  const onInvoiceSubmit = async (data: InvoiceCreate) => {
    try {
      await createInvoice(data);
      setIsInvoiceModalOpen(false);
      invoiceForm.reset();
    } catch (err) {
      console.error(err);
    }
  };

  const onPaymentSubmit = async (data: PaymentCreate) => {
    try {
      if (selectedInvoiceId) {
        await recordPayment(selectedInvoiceId, data);
        setIsPaymentModalOpen(false);
        paymentForm.reset();
        setSelectedInvoiceId(null);
      }
    } catch (err) {
      console.error(err);
    }
  };

  const onFeeSubmit = async (data: FeeConfigCreate) => {
    try {
      await upsertFeeConfig(editingFeeId, data);
      setIsFeeModalOpen(false);
      feeForm.reset();
      setEditingFeeId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditFee = (fee: any) => {
    setEditingFeeId(fee.id);
    feeForm.reset({
      name: fee.name,
      vessel_type_id: fee.vessel_type_id,
      fee_amount: fee.fee_amount,
      is_active: fee.is_active,
    });
    setIsFeeModalOpen(true);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
        <button
          onClick={() => setActiveTab('invoices')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'invoices' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <FileText className="w-4 h-4" />
          <span>Hóa Đơn</span>
        </button>
        <button
          onClick={() => setActiveTab('fees')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'fees' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Settings className="w-4 h-4" />
          <span>Cấu Hình Phí</span>
        </button>
      </div>

      {activeTab === 'invoices' ? (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="text" 
                placeholder="Tìm hóa đơn, mã đơn hàng..." 
                className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
            <div className="flex items-center space-x-3">
              <Button variant="outline" className="border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
                <Filter className="w-4 h-4 mr-2" />
                Bộ Lọc
              </Button>
              <Button 
                onClick={() => setIsInvoiceModalOpen(true)}
                className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
              >
                <Plus className="w-4 h-4 mr-2" />
                Tạo Hóa Đơn
              </Button>
            </div>
          </div>

          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                    <th className="px-6 py-4">Số Hóa Đơn</th>
                    <th className="px-6 py-4">Mã Đơn Hàng</th>
                    <th className="px-6 py-4">Thời Gian</th>
                    <th className="px-6 py-4">Trạng Thái</th>
                    <th className="px-6 py-4">Tổng Tiền</th>
                    <th className="px-6 py-4 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                  {isLoading && invoices.length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center">
                        <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                      </td>
                    </tr>
                  ) : invoices.length > 0 ? (
                    invoices.map((inv) => (
                      <tr key={inv.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors">
                        <td className="px-6 py-4 font-mono text-xs font-bold text-blue-500">{inv.invoice_number}</td>
                        <td className="px-6 py-4 font-mono text-xs text-gray-500">{inv.order_id.split('-')[0]}</td>
                        <td className="px-6 py-4 text-[10px] font-mono text-gray-400">
                          {new Date(inv.created_at).toLocaleString('vi-VN')}
                        </td>
                        <td className="px-6 py-4">
                          <span className={cn(
                            "inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border",
                            paymentStatusColors[inv.payment_status] || paymentStatusColors.unpaid
                          )}>
                            {inv.payment_status === 'paid' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                            {inv.payment_status === 'partial' && <Clock className="w-3 h-3 mr-1" />}
                            {inv.payment_status === 'unpaid' && <AlertCircle className="w-3 h-3 mr-1" />}
                            {paymentStatusLabels[inv.payment_status] || inv.payment_status}
                          </span>
                        </td>
                        <td className="px-6 py-4 font-mono text-xs font-bold text-gray-900 dark:text-white">
                          {inv.total_amount.toLocaleString('vi-VN')} ₫
                        </td>
                        <td className="px-6 py-4 text-right">
                          {inv.payment_status !== 'paid' && (
                            <button 
                              onClick={() => {
                                setSelectedInvoiceId(inv.id);
                                paymentForm.reset({ amount: inv.total_amount });
                                setIsPaymentModalOpen(true);
                              }}
                              className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest"
                            >
                              Thanh Toán
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="px-6 py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
                        Không có hóa đơn nào
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Bảng Giá Cước Tàu</h3>
            <Button 
              onClick={() => {
                setEditingFeeId(null);
                feeForm.reset({ is_active: true });
                setIsFeeModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Thêm Cấu Hình
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {isLoading && feeConfigs.length === 0 ? (
              <div className="col-span-full py-12 text-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
              </div>
            ) : feeConfigs.length > 0 ? (
              feeConfigs.map((fee) => (
                <div key={fee.id} className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4">
                  <div className="flex justify-between items-start">
                    <div className="p-3 bg-blue-600/10 rounded-xl">
                      <DollarSign className="w-6 h-6 text-blue-600" />
                    </div>
                    <span className={cn(
                      "text-[10px] font-bold px-2 py-1 rounded-full uppercase tracking-tighter",
                      fee.is_active ? "bg-green-500/10 text-green-500" : "bg-gray-500/10 text-gray-500"
                    )}>
                      {fee.is_active ? 'Đang Áp Dụng' : 'Tạm Dừng'}
                    </span>
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">{fee.name}</h4>
                    <p className="text-[10px] text-gray-500 uppercase tracking-widest">Loại tàu: {fee.vessel_type?.name || 'Tất cả'}</p>
                  </div>
                  <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-between items-end">
                    <div>
                      <p className="text-[10px] font-mono text-gray-400 uppercase">Giá Cước</p>
                      <p className="text-xl font-extrabold text-blue-600">{fee.fee_amount.toLocaleString('vi-VN')} ₫</p>
                    </div>
                    <button 
                      onClick={() => handleEditFee(fee)}
                      className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                    >
                      Chỉnh Sửa
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-full py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
                Chưa có cấu hình phí nào
              </div>
            )}
          </div>
        </div>
      )}

      {/* Invoice Modal */}
      <Modal
        isOpen={isInvoiceModalOpen}
        onClose={() => setIsInvoiceModalOpen(false)}
        title="Tạo Hóa Đơn Mới"
      >
        <form onSubmit={invoiceForm.handleSubmit(onInvoiceSubmit)} className="space-y-4">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Đơn Hàng</label>
            <select
              {...invoiceForm.register('order_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn đơn hàng...</option>
              {orders.map(o => (
                <option key={o.id} value={o.id}>{o.id.split('-')[0]} - {o.vessel?.name}</option>
              ))}
            </select>
            {invoiceForm.formState.errors.order_id && (
              <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">
                {invoiceForm.formState.errors.order_id.message}
              </p>
            )}
          </div>
          
          <div className="space-y-3">
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest ml-1">Chi Tiết Hạng Mục</p>
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
                    {...invoiceForm.register(`items.${index}.quantity` as const, { valueAsNumber: true })}
                  />
                </div>
                <div className="col-span-4">
                  <Input
                    type="number"
                    placeholder="Đơn giá"
                    {...invoiceForm.register(`items.${index}.unit_price` as const, { valueAsNumber: true })}
                  />
                </div>
              </div>
            ))}
          </div>

          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsInvoiceModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Tạo Hóa Đơn"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Payment Modal */}
      <Modal
        isOpen={isPaymentModalOpen}
        onClose={() => setIsPaymentModalOpen(false)}
        title="Ghi Nhận Thanh Toán"
      >
        <form onSubmit={paymentForm.handleSubmit(onPaymentSubmit)} className="space-y-4">
          <Input
            label="Số Tiền"
            type="number"
            {...paymentForm.register('amount', { valueAsNumber: true })}
            error={paymentForm.formState.errors.amount?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Phương Thức</label>
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
            <Button type="button" variant="outline" onClick={() => setIsPaymentModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Xác Nhận Thanh Toán"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Fee Modal */}
      <Modal
        isOpen={isFeeModalOpen}
        onClose={() => setIsFeeModalOpen(false)}
        title={editingFeeId ? "Chỉnh Sửa Cấu Hình Phí" : "Thêm Cấu Hình Phí Mới"}
      >
        <form onSubmit={feeForm.handleSubmit(onFeeSubmit)} className="space-y-4">
          <Input
            label="Tên Phí"
            placeholder="VD: Phí Cập Cảng"
            {...feeForm.register('name')}
            error={feeForm.formState.errors.name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Loại Tàu Áp Dụng</label>
            <select
              {...feeForm.register('vessel_type_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn loại tàu...</option>
              {vesselTypes.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          </div>
          <Input
            label="Mức Phí (VNĐ)"
            type="number"
            {...feeForm.register('fee_amount', { valueAsNumber: true })}
            error={feeForm.formState.errors.fee_amount?.message}
          />
          <div className="flex items-center space-x-2 ml-1">
            <input
              type="checkbox"
              id="fee_is_active"
              {...feeForm.register('is_active')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="fee_is_active" className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
              Đang Áp Dụng
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsFeeModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingFeeId ? "Cập Nhật" : "Thêm Mới")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
