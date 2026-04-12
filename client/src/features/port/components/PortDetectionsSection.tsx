import React from 'react';
import { CheckCircle2, Loader2, RefreshCw, Trash2, XCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import type { DetectionRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type PortDetectionsSectionProps = {
  detQ: string;
  setDetQ: (v: string) => void;
  detAccepted: 'all' | 'yes' | 'no';
  setDetAccepted: (v: 'all' | 'yes' | 'no') => void;
  detDateFrom: string;
  setDetDateFrom: (v: string) => void;
  detDateTo: string;
  setDetDateTo: (v: string) => void;
  detMinConfPct: string;
  setDetMinConfPct: (v: string) => void;
  resetDetFilters: () => void;
  detFilterCount: number;
  onRefresh: () => void;
  isLoading: boolean;
  detections: DetectionRead[];
  filteredDetections: DetectionRead[];
  onVerify: (id: string, data: { is_accepted: boolean }) => void;
  onDeleteDetection: (id: string) => void;
};

export const PortDetectionsSection: React.FC<PortDetectionsSectionProps> = ({
  detQ,
  setDetQ,
  detAccepted,
  setDetAccepted,
  detDateFrom,
  setDetDateFrom,
  detDateTo,
  setDetDateTo,
  detMinConfPct,
  setDetMinConfPct,
  resetDetFilters,
  detFilterCount,
  onRefresh,
  isLoading,
  detections,
  filteredDetections,
  onVerify,
  onDeleteDetection,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel onReset={resetDetFilters} activeCount={detFilterCount}>
        <FilterField label="Từ khóa (mã tàu / track / vessel id)">
          <input
            type="text"
            value={detQ}
            onChange={(e) => setDetQ(e.target.value)}
            placeholder="Lọc nhanh..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Trạng thái duyệt">
          <select
            value={detAccepted}
            onChange={(e) => setDetAccepted(e.target.value as 'all' | 'yes' | 'no')}
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="yes">Đã xác nhận</option>
            <option value="no">Chờ duyệt</option>
          </select>
        </FilterField>
        <FilterField label="Từ ngày (sự kiện)">
          <input
            type="date"
            value={detDateFrom}
            onChange={(e) => setDetDateFrom(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Đến ngày">
          <input
            type="date"
            value={detDateTo}
            onChange={(e) => setDetDateTo(e.target.value)}
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Độ tin cậy tối thiểu (%)">
          <input
            type="number"
            min={0}
            max={100}
            value={detMinConfPct}
            onChange={(e) => setDetMinConfPct(e.target.value)}
            placeholder="VD: 50"
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          onClick={() => onRefresh()}
          className="border-gray-200 dark:border-white/10 text-gray-500 dark:text-gray-400"
        >
          <RefreshCw className={cn('w-4 h-4 mr-2', isLoading && 'animate-spin')} />
          Làm Mới
        </Button>
      </div>

      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className={dt.headRow}>
                <th className={dt.pad}>Thời Gian</th>
                <th className={dt.pad}>Mã Tàu</th>
                <th className={dt.pad}>Độ Tin Cậy</th>
                <th className={dt.pad}>Trạng Thái</th>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && detections.length === 0 ? (
                <tr>
                  <td colSpan={5} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredDetections.length > 0 ? (
                filteredDetections.map((det) => (
                  <tr
                    key={det.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors"
                  >
                    <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                      {(() => {
                        const iso = getDetectionDisplayTimeIso(det);
                        return iso ? new Date(iso).toLocaleString('vi-VN') : '\u2014';
                      })()}
                    </td>
                    <td className={cn(dt.pad, dt.body, 'font-bold uppercase')}>
                      {getDetectionShipLabel(det)}
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'text-blue-600 dark:text-blue-400')}>
                      {(((det.confidence ?? 0) as number) * 100).toFixed(1)}%
                    </td>
                    <td className={dt.pad}>
                      <span
                        className={cn(
                          'inline-flex items-center px-2.5 py-1 rounded-full border',
                          dt.badge,
                          det.is_accepted === true
                            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                            : 'text-amber-600 dark:text-amber-400 bg-amber-500/10 border-amber-500/20',
                        )}
                      >
                        {det.is_accepted === true ? 'Đã Xác Nhận' : 'Chờ Duyệt'}
                      </span>
                    </td>
                    <td className={cn(dt.pad, 'text-right space-x-2')}>
                      {det.is_accepted !== true && (
                        <>
                          <button
                            type="button"
                            onClick={() => onVerify(det.id, { is_accepted: true })}
                            className="p-1.5 text-emerald-500 hover:bg-emerald-500/10 rounded-lg transition-all"
                          >
                            <CheckCircle2 className="w-4 h-4" />
                          </button>
                          <button
                            type="button"
                            onClick={() => onVerify(det.id, { is_accepted: false })}
                            className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                          >
                            <XCircle className="w-4 h-4" />
                          </button>
                        </>
                      )}
                      <button
                        type="button"
                        onClick={() => onDeleteDetection(det.id)}
                        className="p-1.5 text-red-500 hover:bg-red-500/10 rounded-lg transition-all"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={5}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {detections.length === 0
                      ? 'Không có dữ liệu nhận diện'
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
