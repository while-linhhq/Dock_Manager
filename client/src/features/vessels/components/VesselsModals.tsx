import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { VesselTypeRead } from '../../../types/api.types';
import type { VesselCreate, VesselTypeCreate } from '../services/vesselsApi';

export type VesselsModalsProps = {
  isVesselModalOpen: boolean;
  onCloseVessel: () => void;
  vesselForm: UseFormReturn<VesselCreate>;
  onVesselSubmit: (data: VesselCreate) => void | Promise<void>;
  editingId: string | null;
  vesselTypes: VesselTypeRead[];
  isLoading: boolean;
  isTypeModalOpen: boolean;
  onCloseType: () => void;
  typeForm: UseFormReturn<VesselTypeCreate>;
  onTypeSubmit: (data: VesselTypeCreate) => void | Promise<void>;
};

export const VesselsModals: React.FC<VesselsModalsProps> = ({
  isVesselModalOpen,
  onCloseVessel,
  vesselForm,
  onVesselSubmit,
  editingId,
  vesselTypes,
  isLoading,
  isTypeModalOpen,
  onCloseType,
  typeForm,
  onTypeSubmit,
}) => {
  return (
    <>
      <Modal
        isOpen={isVesselModalOpen}
        onClose={onCloseVessel}
        title={editingId ? 'Chỉnh Sửa Thông Tin Tàu' : 'Đăng Ký Tàu Mới'}
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
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Loại Tàu
            </label>
            <select
              {...vesselForm.register('vessel_type_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn loại tàu...</option>
              {vesselTypes.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.type_name}
                </option>
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
            <label
              htmlFor="is_active"
              className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
            >
              Đang Hoạt Động
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseVessel} className="flex-1">
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
                'Đăng Ký'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={isTypeModalOpen}
        onClose={onCloseType}
        title={editingId ? 'Chỉnh Sửa Loại Tàu' : 'Thêm Loại Tàu Mới'}
      >
        <form onSubmit={typeForm.handleSubmit(onTypeSubmit)} className="space-y-4">
          <Input
            label="Tên Loại Tàu"
            placeholder="VD: Tàu Container"
            {...typeForm.register('type_name')}
            error={typeForm.formState.errors.type_name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Mô Tả
            </label>
            <textarea
              {...typeForm.register('description')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all min-h-[100px]"
              placeholder="Nhập mô tả loại tàu..."
            />
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseType} className="flex-1">
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
                'Thêm Mới'
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};
