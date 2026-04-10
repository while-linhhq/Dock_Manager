import React, { useEffect, useState } from 'react';
import { 
  Plus, 
  Search, 
  Filter, 
  MoreVertical, 
  Clock, 
  CheckCircle2, 
  AlertCircle,
  Loader2,
  Trash2,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { useOrderStore } from '../store/orderStore';
import { useVesselStore } from '../../vessels/store/vesselStore';
import type { OrderCreate, OrderUpdate } from '../services/ordersApi';

const orderSchema = z.object({
  vessel_id: z.string().min(1, 'Mã tàu là bắt buộc'),
  cargo_details: z.string().optional(),
  total_amount: z.number().min(0, 'Số tiền không được âm'),
  status: z.string().default('pending'),
});

const statusColors: Record<string, string> = {
  'processing': 'text-blue-500 bg-blue-500/10 border-blue-500/20',
  'completed': 'text-emerald-500 bg-emerald-500/10 border-emerald-500/20',
  'pending': 'text-amber-500 bg-amber-500/10 border-amber-500/20',
  'cancelled': 'text-red-500 bg-red-500/10 border-red-500/20',
};

const statusLabels: Record<string, string> = {
  'processing': 'Đang Xử Lý',
  'completed': 'Hoàn Thành',
  'pending': 'Chờ Duyệt',
  'cancelled': 'Đã Hủy',
};

export const OrdersView: React.FC = () => {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  
  const { orders, isLoading, fetchOrders, createOrder, updateOrder, deleteOrder } = useOrderStore();
  const { vessels, fetchVessels } = useVesselStore();

  const form = useForm<OrderCreate>({
    resolver: zodResolver(orderSchema),
    defaultValues: { status: 'pending', total_amount: 0 }
  });

  useEffect(() => {
    fetchOrders();
    fetchVessels();
  }, [fetchOrders, fetchVessels]);

  const onSubmit = async (data: OrderCreate) => {
    try {
      if (editingId) {
        await updateOrder(editingId, data as OrderUpdate);
      } else {
        await createOrder(data);
      }
      setIsModalOpen(false);
      form.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEdit = (order: any) => {
    setEditingId(order.id);
    form.reset({
      vessel_id: order.vessel_id,
      cargo_details: order.cargo_details,
      total_amount: order.total_amount,
      status: order.status,
    });
    setIsModalOpen(true);
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm('Xác nhận xóa đơn hàng này?')) {
      return;
    }
    await deleteOrder(id);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Header Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
          <input 
            type="text" 
            placeholder="Tìm đơn hàng, mã tàu, hoặc khách hàng..." 
            className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
          />
        </div>
        <div className="flex items-center space-x-3">
          <Button variant="outline" className="border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-white/5">
            <Filter className="w-4 h-4 mr-2" />
            Bộ Lọc
          </Button>
          <Button 
            onClick={() => {
              setEditingId(null);
              form.reset({ status: 'pending', total_amount: 0 });
              setIsModalOpen(true);
            }}
            className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
          >
            <Plus className="w-4 h-4 mr-2" />
            Tạo Đơn Hàng
          </Button>
        </div>
      </div>

      {/* Orders Table */}
      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                <th className="px-6 py-4">Mã Đơn</th>
                <th className="px-6 py-4">Tàu / Hàng Hóa</th>
                <th className="px-6 py-4">Thời Gian</th>
                <th className="px-6 py-4">Trạng Thái</th>
                <th className="px-6 py-4">Số Tiền</th>
                <th className="px-6 py-4 text-right">Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && orders.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center">
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto mb-2" />
                    <span className="text-xs font-mono uppercase text-gray-500">Đang tải dữ liệu...</span>
                  </td>
                </tr>
              ) : orders.length > 0 ? (
                orders.map((order) => (
                  <tr key={order.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors group">
                    <td className="px-6 py-4">
                      <span className="text-xs font-mono font-bold text-blue-500">{order.id.split('-')[0]}</span>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex flex-col">
                        <span className="text-xs font-bold text-gray-900 dark:text-white uppercase">
                          {order.vessel?.ship_id || 'KHÔNG XÁC ĐỊNH'}
                        </span>
                        <span className="text-[10px] text-gray-500 uppercase tracking-tighter">
                          {order.cargo_details || 'Chi tiết hàng hóa'}
                        </span>
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <div className="flex items-center text-[10px] font-mono text-gray-400">
                        <Clock className="w-3 h-3 mr-1.5 opacity-50" />
                        {new Date(order.created_at).toLocaleString('vi-VN')}
                      </div>
                    </td>
                    <td className="px-6 py-4">
                      <span className={cn(
                        "inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border",
                        statusColors[order.status] || statusColors.pending
                      )}>
                        {order.status === 'completed' && <CheckCircle2 className="w-3 h-3 mr-1" />}
                        {order.status === 'processing' && <ActivityIndicator />}
                        {order.status === 'pending' && <Clock className="w-3 h-3 mr-1" />}
                        {order.status === 'cancelled' && <AlertCircle className="w-3 h-3 mr-1" />}
                        {statusLabels[order.status] || order.status}
                      </span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="text-xs font-mono font-bold text-gray-900 dark:text-white">
                        {order.total_amount.toLocaleString('vi-VN')} ₫
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button 
                          onClick={() => handleEdit(order)}
                          className="p-2 hover:bg-gray-100 dark:hover:bg-white/10 rounded-lg transition-all text-gray-500 hover:text-gray-900 dark:hover:text-white"
                        >
                          <MoreVertical className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => handleDelete(order.id)}
                          className="p-2 hover:bg-red-100 dark:hover:bg-red-500/10 rounded-lg transition-all text-red-500"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={6} className="px-6 py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
                    Không có đơn hàng nào
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        
        {/* Pagination Mock */}
        <div className="p-4 border-t border-gray-200 dark:border-white/5 flex items-center justify-between bg-gray-50 dark:bg-white/[0.01]">
          <p className="text-[10px] font-mono text-gray-500 uppercase">
            Hiển thị {orders.length} đơn hàng
          </p>
          <div className="flex space-x-2">
            <Button variant="outline" size="sm" className="border-gray-200 dark:border-white/10 text-xs py-1 px-3 h-auto opacity-50 cursor-not-allowed">Trước</Button>
            <Button variant="outline" size="sm" className="border-gray-200 dark:border-white/10 text-xs py-1 px-3 h-auto">Sau</Button>
          </div>
        </div>
      </div>

      {/* Order Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? "Chỉnh Sửa Đơn Hàng" : "Tạo Đơn Hàng Mới"}
      >
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Tàu Cập Cảng</label>
            <select
              {...form.register('vessel_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn tàu...</option>
              {vessels.map(v => (
                <option key={v.id} value={v.id}>{v.ship_id} - {v.name}</option>
              ))}
            </select>
            {form.formState.errors.vessel_id && (
              <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">
                {form.formState.errors.vessel_id.message}
              </p>
            )}
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Chi Tiết Hàng Hóa</label>
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
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Trạng Thái</label>
            <select
              {...form.register('status')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              {Object.entries(statusLabels).map(([val, label]) => (
                <option key={val} value={val}>{label}</option>
              ))}
            </select>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? "Cập Nhật" : "Tạo Đơn")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};

const ActivityIndicator = () => (
  <span className="flex space-x-0.5 mr-1.5">
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_0ms]" />
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_200ms]" />
    <span className="w-0.5 h-2 bg-current animate-[bounce_1s_infinite_400ms]" />
  </span>
);
