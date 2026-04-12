import React from 'react';
import { Loader2, Plus, Tag, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import type { VesselTypeRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type VesselTypesSectionProps = {
  typeQ: string;
  setTypeQ: (v: string) => void;
  resetTypeFilters: () => void;
  typeFilterCount: number;
  onOpenAddType: () => void;
  vesselTypes: VesselTypeRead[];
  filteredTypes: VesselTypeRead[];
  isLoading: boolean;
  onEditType: (t: VesselTypeRead) => void;
  onDeleteType: (id: string) => void;
};

export const VesselTypesSection: React.FC<VesselTypesSectionProps> = ({
  typeQ,
  setTypeQ,
  resetTypeFilters,
  typeFilterCount,
  onOpenAddType,
  vesselTypes,
  filteredTypes,
  isLoading,
  onEditType,
  onDeleteType,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel
        title="Bộ lọc loại tàu"
        onReset={resetTypeFilters}
        activeCount={typeFilterCount}
      >
        <FilterField label="Tên / mô tả" className="sm:col-span-2 lg:col-span-2">
          <input
            type="text"
            value={typeQ}
            onChange={(e) => setTypeQ(e.target.value)}
            placeholder="Lọc theo tên hoặc mô tả..."
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-between items-center">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Danh Mục Loại Tàu
        </h3>
        <Button
          type="button"
          onClick={onOpenAddType}
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
        ) : filteredTypes.length > 0 ? (
          filteredTypes.map((type) => (
            <div
              key={type.id}
              className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4"
            >
              <div className="p-3 bg-blue-600/10 rounded-xl w-fit">
                <Tag className="w-6 h-6 text-blue-600" />
              </div>
              <div>
                <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">
                  {type.type_name}
                </h4>
                <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-1">
                  {type.description || 'Không có mô tả'}
                </p>
              </div>
              <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => onEditType(type)}
                  className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest transition-colors"
                >
                  Chỉnh Sửa
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteType(type.id)}
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
            {vesselTypes.length === 0
              ? 'Chưa có loại tàu nào'
              : 'Không có loại tàu khớp bộ lọc'}
          </div>
        )}
      </div>
    </div>
  );
};
