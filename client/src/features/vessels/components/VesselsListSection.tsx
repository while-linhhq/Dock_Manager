import React from 'react';
import { CheckCircle2, Loader2, Pencil, Plus, Trash2, Upload, XCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import { useTableSort, type SortAccessors } from '../../../hooks/useTableSort';
import { formatApplicableFee, resolveVesselTypeName } from '../utils/vessel-display-helpers';

export type VesselsListSectionProps = {
  vesselQ: string;
  setVesselQ: (v: string) => void;
  vesselTypeFilter: string;
  setVesselTypeFilter: (v: string) => void;
  vesselActive: 'all' | 'active' | 'inactive';
  setVesselActive: (v: 'all' | 'active' | 'inactive') => void;
  vesselDateFrom: string;
  setVesselDateFrom: (v: string) => void;
  vesselDateTo: string;
  setVesselDateTo: (v: string) => void;
  resetVesselFilters: () => void;
  vesselFilterCount: number;
  /** Tab phân loại đang mở — quyết định cột hiển thị (spot bỏ Loại Tàu, thêm STT). */
  activeTab: 'spot' | 'monthly' | 'unclassified';
  onOpenAddVessel: () => void;
  vesselTypes: VesselTypeRead[];
  vessels: VesselRead[];
  filteredVessels: VesselRead[];
  isLoading: boolean;
  onEditVessel: (v: VesselRead) => void;
  onDeleteVessel: (id: string) => void;
  onOpenUploadModal: (v: VesselRead) => void;
};

export const VesselsListSection: React.FC<VesselsListSectionProps> = ({
  vesselQ,
  setVesselQ,
  vesselTypeFilter,
  setVesselTypeFilter,
  vesselActive,
  setVesselActive,
  vesselDateFrom,
  setVesselDateFrom,
  vesselDateTo,
  setVesselDateTo,
  resetVesselFilters,
  vesselFilterCount,
  activeTab,
  onOpenAddVessel,
  vesselTypes,
  vessels,
  filteredVessels,
  isLoading,
  onEditVessel,
  onDeleteVessel,
  onOpenUploadModal,
}) => {
  // Tàu lẻ gắn phí per-tàu, không dùng loại tàu → ẩn cột Loại Tàu.
  const isSpot = activeTab === 'spot';
  // STT hiển thị ở tab Tàu Lẻ và Tàu Tháng (danh sách cấu hình cố định).
  const showIndex = activeTab === 'spot' || activeTab === 'monthly';
  // Số cột thực tế: 8 cột gốc (có Loại Tàu) +STT nếu bật, -Loại Tàu nếu spot.
  const colCount = 8 + (showIndex ? 1 : 0) - (isSpot ? 1 : 0);

  // Sắp xếp client-side theo cột. STT đánh số theo thứ tự SAU khi đã sort.
  const sortAccessors: SortAccessors<VesselRead> = {
    ship_id: (v) => v.ship_id,
    name: (v) => v.name ?? '',
    vessel_type: (v) => resolveVesselTypeName(v, vesselTypes),
    visual_reference_count: (v) => v.visual_reference_count ?? 0,
    owner: (v) => v.owner ?? v.owner_info ?? '',
    is_active: (v) => v.is_active,
  };
  const { sorted: sortedVessels, sort, toggle } = useTableSort(filteredVessels, sortAccessors);

  return (
    <div className="space-y-6">
      <TableFilterPanel onReset={resetVesselFilters} activeCount={vesselFilterCount}>
        <FilterField label="Từ khóa (mã / tên / chủ / ĐK)">
          <input
            type="text"
            value={vesselQ}
            onChange={(e) => setVesselQ(e.target.value)}
            placeholder="Nhập để lọc..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Loại tàu">
          <select
            value={vesselTypeFilter}
            onChange={(e) => setVesselTypeFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vesselTypes.map((t) => (
              <option key={t.id} value={String(t.id)}>
                {t.type_name}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Trạng thái">
          <select
            value={vesselActive}
            onChange={(e) =>
              setVesselActive(e.target.value as 'all' | 'active' | 'inactive')
            }
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="active">Đang hoạt động</option>
            <option value="inactive">Tạm dừng</option>
          </select>
        </FilterField>
        <FilterField label="Từ ngày (tạo / cập nhật)">
          <input
            type="date"
            value={vesselDateFrom}
            onChange={(e) => setVesselDateFrom(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Đến ngày">
          <input
            type="date"
            value={vesselDateTo}
            onChange={(e) => setVesselDateTo(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-end">
        <Button
          type="button"
          onClick={onOpenAddVessel}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Đăng Ký Tàu
        </Button>
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className={dt.headRow}>
                {showIndex && <th className={cn(dt.pad, 'w-12 text-center')}>STT</th>}
                <SortableTh sortKey="ship_id" sort={sort} onSort={toggle}>
                  Mã Tàu
                </SortableTh>
                <SortableTh sortKey="name" sort={sort} onSort={toggle}>
                  Tên Tàu
                </SortableTh>
                {!isSpot && (
                  <SortableTh sortKey="vessel_type" sort={sort} onSort={toggle}>
                    Loại Tàu
                  </SortableTh>
                )}
                <SortableTh sortKey="visual_reference_count" sort={sort} onSort={toggle}>
                  Ảnh Mẫu
                </SortableTh>
                <th className={dt.pad}>Chi Phí Theo Loại (tham chiếu)</th>
                <SortableTh sortKey="owner" sort={sort} onSort={toggle}>
                  Chủ Tàu
                </SortableTh>
                <SortableTh sortKey="is_active" sort={sort} onSort={toggle}>
                  Trạng Thái
                </SortableTh>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && vessels.length === 0 ? (
                <tr>
                  <td colSpan={colCount} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : sortedVessels.length > 0 ? (
                sortedVessels.map((v, idx) => (
                  <tr
                    key={v.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors"
                  >
                    {showIndex && (
                      <td className={cn(dt.pad, dt.mono, 'text-center text-gray-500')}>
                        {idx + 1}
                      </td>
                    )}
                    <td className={cn(dt.pad, dt.monoAccent)}>{v.ship_id}</td>
                    <td className={cn(dt.pad, dt.body, 'font-bold uppercase')}>
                      {v.name || '—'}
                    </td>
                    {!isSpot && (
                      <td className={cn(dt.pad, dt.meta)}>
                        {resolveVesselTypeName(v, vesselTypes)}
                      </td>
                    )}
                    <td className={cn(dt.pad, dt.mono)}>
                      {typeof v.visual_reference_count === 'number' ? v.visual_reference_count : 0}
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'max-w-[14rem]')}>
                      {formatApplicableFee(v)}
                    </td>
                    <td
                      className={cn(dt.pad, dt.bodyMuted, 'max-w-[12rem] truncate')}
                      title={v.owner ?? v.owner_info ?? ''}
                    >
                      {v.owner || v.owner_info || '—'}
                    </td>
                    <td className={dt.pad}>
                      <span
                        className={cn(
                          'inline-flex items-center px-2.5 py-1 rounded-full border',
                          dt.badge,
                          v.is_active
                            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                            : 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20',
                        )}
                      >
                        {v.is_active ? (
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 mr-1 shrink-0" />
                        )}
                        {v.is_active ? 'Hoạt Động' : 'Tạm Dừng'}
                      </span>
                    </td>
                    <td className={cn(dt.pad, 'text-right')}>
                      <div className="inline-flex items-center gap-1">
                        <button
                          type="button"
                          onClick={() => onEditVessel(v)}
                          className={cn(
                            'p-2 rounded-lg transition-colors',
                            'text-blue-600 hover:text-blue-500 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10',
                          )}
                          title="Chỉnh sửa"
                          aria-label="Chỉnh sửa"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onOpenUploadModal(v)}
                          className={cn(
                            'p-2 rounded-lg transition-colors',
                            'text-emerald-600 hover:text-emerald-500 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-500/10',
                          )}
                          title="Upload ảnh mẫu"
                          aria-label="Upload ảnh mẫu"
                        >
                          <Upload className="w-4 h-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => onDeleteVessel(String(v.id))}
                          className={cn(
                            'p-2 rounded-lg transition-colors',
                            'text-red-600 hover:text-red-500 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10',
                          )}
                          title="Xóa tàu"
                          aria-label="Xóa tàu"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={colCount}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {vessels.length === 0
                      ? 'Không có dữ liệu tàu'
                      : 'Không có bản ghi khớp bộ lọc'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
