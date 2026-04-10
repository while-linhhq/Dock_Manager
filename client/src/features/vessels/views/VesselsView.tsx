import React, { useEffect, useState } from 'react';
import { 
  Ship, 
  Plus, 
  Search, 
  Filter, 
  CheckCircle2, 
  XCircle,
  Loader2,
  Tag,
  Trash2,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { useVesselStore } from '../store/vesselStore';
import type { VesselCreate, VesselTypeCreate } from '../services/vesselsApi';

const vesselSchema = z.object({
  ship_id: z.string().min(1, 'Mã tàu là bắt buộc'),
  name: z.string().min(1, 'Tên tàu là bắt buộc'),
  vessel_type_id: z.string().min(1, 'Loại tàu là bắt buộc'),
  owner_info: z.string().optional(),
  is_active: z.boolean().default(true),
});

const vesselTypeSchema = z.object({
  name: z.string().min(1, 'Tên loại tàu là bắt buộc'),
  description: z.string().optional(),
});

export const VesselsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'vessels' | 'types'>('vessels');
  const [isVesselModalOpen, setIsVesselModalOpen] = useState(false);
  const [isTypeModalOpen, setIsTypeModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { 
    vessels, 
    vesselTypes, 
    isLoading, 
    fetchVessels, 
    fetchVesselTypes,
    upsertVessel,
    upsertVesselType,
    deleteVessel,
    deleteVesselType,
  } = useVesselStore();

  const vesselForm = useForm<VesselCreate>({
    resolver: zodResolver(vesselSchema),
    defaultValues: { is_active: true }
  });

  const typeForm = useForm<VesselTypeCreate>({
    resolver: zodResolver(vesselTypeSchema)
  });

  useEffect(() => {
    if (activeTab === 'vessels') {
      fetchVessels();
      fetchVesselTypes(); // Need types for vessel form dropdown
    } else {
      fetchVesselTypes();
    }
  }, [activeTab, fetchVessels, fetchVesselTypes]);

  const onVesselSubmit = async (data: VesselCreate) => {
    try {
      await upsertVessel(editingId, data);
      setIsVesselModalOpen(false);
      vesselForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onTypeSubmit = async (data: VesselTypeCreate) => {
    try {
      await upsertVesselType(editingId, data);
      setIsTypeModalOpen(false);
      typeForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditVessel = (vessel: any) => {
    setEditingId(vessel.id);
    vesselForm.reset({
      ship_id: vessel.ship_id,
      name: vessel.name,
      vessel_type_id: vessel.vessel_type_id,
      owner_info: vessel.owner_info,
      is_active: vessel.is_active,
    });
    setIsVesselModalOpen(true);
  };

  const handleEditType = (type: any) => {
    setEditingId(type.id);
    typeForm.reset({
      name: type.name,
      description: type.description,
    });
    setIsTypeModalOpen(true);
  };

  const handleDeleteVessel = async (id: string) => {
    if (!window.confirm('Xác nhận xóa tàu này?')) {
      return;
    }
    await deleteVessel(id);
  };

  const handleDeleteType = async (id: string) => {
    if (!window.confirm('Xác nhận xóa loại tàu này?')) {
      return;
    }
    await deleteVesselType(id);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
        <button
          onClick={() => setActiveTab('vessels')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'vessels' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Ship className="w-4 h-4" />
          <span>Danh Sách Tàu</span>
        </button>
        <button
          onClick={() => setActiveTab('types')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'types' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Tag className="w-4 h-4" />
          <span>Loại Tàu</span>
        </button>
      </div>

      {activeTab === 'vessels' ? (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="text" 
                placeholder="Tìm mã tàu, tên tàu..." 
                className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
            <div className="flex items-center space-x-3">
              <Button variant="outline" className="border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white">
                <Filter className="w-4 h-4 mr-2" />
                Bộ Lọc
              </Button>
              <Button 
                onClick={() => {
                  setEditingId(null);
                  vesselForm.reset({ is_active: true });
                  setIsVesselModalOpen(true);
                }}
                className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
              >
                <Plus className="w-4 h-4 mr-2" />
                Đăng Ký Tàu
              </Button>
            </div>
          </div>

          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                    <th className="px-6 py-4">Mã Tàu (Ship ID)</th>
                    <th className="px-6 py-4">Tên Tàu</th>
                    <th className="px-6 py-4">Loại Tàu</th>
                    <th className="px-6 py-4">Trạng Thái</th>
                    <th className="px-6 py-4 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                  {isLoading && vessels.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center">
                        <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                      </td>
                    </tr>
                  ) : vessels.length > 0 ? (
                    vessels.map((v) => (
                      <tr key={v.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors">
                        <td className="px-6 py-4 font-mono text-xs font-bold text-blue-500">{v.ship_id}</td>
                        <td className="px-6 py-4 text-xs font-bold text-gray-900 dark:text-white uppercase">{v.name}</td>
                        <td className="px-6 py-4 text-[10px] font-bold text-gray-500 uppercase tracking-widest">
                          {v.vessel_type?.name || 'N/A'}
                        </td>
                        <td className="px-6 py-4">
                          <span className={cn(
                            "inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border",
                            v.is_active ? "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" : "text-red-500 bg-red-500/10 border-red-500/20"
                          )}>
                            {v.is_active ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
                            {v.is_active ? 'Hoạt Động' : 'Tạm Dừng'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <div className="inline-flex items-center gap-3">
                            <button 
                              onClick={() => handleEditVessel(v)}
                              className="text-[10px] font-bold text-blue-600 hover:text-blue-500 uppercase tracking-widest"
                            >
                              Chỉnh Sửa
                            </button>
                            <button
                              onClick={() => handleDeleteVessel(v.id)}
                              className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest"
                            >
                              Xóa
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="px-6 py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
                        Không có dữ liệu tàu
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
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Danh Mục Loại Tàu</h3>
            <Button 
              onClick={() => {
                setEditingId(null);
                typeForm.reset();
                setIsTypeModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Thêm Loại Tàu
            </Button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {isLoading && vesselTypes.length === 0 ? (
              <div className="col-span-full py-12 text-center">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
              </div>
            ) : vesselTypes.length > 0 ? (
              vesselTypes.map((type) => (
                <div key={type.id} className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4">
                  <div className="p-3 bg-blue-600/10 rounded-xl w-fit">
                    <Tag className="w-6 h-6 text-blue-600" />
                  </div>
                  <div>
                    <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">{type.name}</h4>
                    <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-1">
                      {type.description || 'Không có mô tả'}
                    </p>
                  </div>
                  <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-end gap-3">
                    <button 
                      onClick={() => handleEditType(type)}
                      className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                    >
                      Chỉnh Sửa
                    </button>
                    <button
                      onClick={() => handleDeleteType(type.id)}
                      className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest transition-colors inline-flex items-center gap-1"
                    >
                      <Trash2 className="w-3 h-3" />
                      Xóa
                    </button>
                  </div>
                </div>
              ))
            ) : (
              <div className="col-span-full py-12 text-center text-gray-500 text-xs uppercase tracking-widest font-mono">
                Chưa có loại tàu nào
              </div>
            )}
          </div>
        </div>
      )}

      {/* Vessel Modal */}
      <Modal
        isOpen={isVesselModalOpen}
        onClose={() => setIsVesselModalOpen(false)}
        title={editingId ? "Chỉnh Sửa Thông Tin Tàu" : "Đăng Ký Tàu Mới"}
      >
        <form onSubmit={vesselForm.handleSubmit(onVesselSubmit)} className="space-y-4">
          <Input
            label="Mã Tàu (Ship ID)"
            placeholder="VD: SHIP-001"
            {...vesselForm.register('ship_id')}
            error={vesselForm.formState.errors.ship_id?.message}
          />
          <Input
            label="Tên Tàu"
            placeholder="VD: Bason Express"
            {...vesselForm.register('name')}
            error={vesselForm.formState.errors.name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Loại Tàu</label>
            <select
              {...vesselForm.register('vessel_type_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn loại tàu...</option>
              {vesselTypes.map(t => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
            {vesselForm.formState.errors.vessel_type_id && (
              <p className="text-[10px] text-red-500 font-bold uppercase tracking-tighter ml-1">
                {vesselForm.formState.errors.vessel_type_id.message}
              </p>
            )}
          </div>
          <Input
            label="Thông Tin Chủ Tàu"
            placeholder="VD: Công ty Vận tải Bason"
            {...vesselForm.register('owner_info')}
          />
          <div className="flex items-center space-x-2 ml-1">
            <input
              type="checkbox"
              id="is_active"
              {...vesselForm.register('is_active')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label htmlFor="is_active" className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
              Đang Hoạt Động
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsVesselModalOpen(false)}
              className="flex-1"
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? "Cập Nhật" : "Đăng Ký")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Vessel Type Modal */}
      <Modal
        isOpen={isTypeModalOpen}
        onClose={() => setIsTypeModalOpen(false)}
        title={editingId ? "Chỉnh Sửa Loại Tàu" : "Thêm Loại Tàu Mới"}
      >
        <form onSubmit={typeForm.handleSubmit(onTypeSubmit)} className="space-y-4">
          <Input
            label="Tên Loại Tàu"
            placeholder="VD: Tàu Container"
            {...typeForm.register('name')}
            error={typeForm.formState.errors.name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Mô Tả</label>
            <textarea
              {...typeForm.register('description')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all min-h-[100px]"
              placeholder="Nhập mô tả loại tàu..."
            />
          </div>
          <div className="pt-4 flex space-x-3">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsTypeModalOpen(false)}
              className="flex-1"
            >
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? "Cập Nhật" : "Thêm Mới")}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
