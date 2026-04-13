import React, { useMemo, useState } from 'react';
import { CheckCircle2, Eye, Loader2, RefreshCw, Trash2, X, XCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatDateTimeVN } from '../../../utils/date-time';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';
import type { DetectionMediaRead, DetectionRead } from '../../../types/api.types';
import { portApi } from '../services/portApi';
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
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareShipLabel, setCompareShipLabel] = useState<string>('—');
  const [compareMedia, setCompareMedia] = useState<DetectionMediaRead[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);

  const mediaOrigin = useMemo(() => {
    const apiBase = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1';
    try {
      return new URL(apiBase).origin;
    } catch {
      return '';
    }
  }, []);

  const resolveImageUrl = (det: DetectionRead): string | null => {
    const raw = (det.audit_image_url || det.audit_image_path || '').trim();
    if (!raw) {
      return null;
    }
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      return raw;
    }
    if (raw.startsWith('/runs/')) {
      return mediaOrigin ? `${mediaOrigin}${raw}` : raw;
    }
    return null;
  };

  const resolveMediaUrl = (filePath: string): string | null => {
    const raw = (filePath || '').trim();
    if (!raw) {
      return null;
    }
    if (raw.startsWith('http://') || raw.startsWith('https://')) {
      return raw;
    }
    const normalized = raw.replaceAll('\\', '/').replace(/^\.?\//, '');
    if (!normalized.startsWith('runs/')) {
      return null;
    }
    const relative = `/${normalized}`;
    return mediaOrigin ? `${mediaOrigin}${relative}` : relative;
  };

  const openCompareModal = async (det: DetectionRead) => {
    setCompareOpen(true);
    setCompareShipLabel(getDetectionShipLabel(det));
    setCompareLoading(true);
    try {
      const media = await portApi.getDetectionMedia(det.id);
      const fallback: DetectionMediaRead[] = [];
      if (det.audit_image_path || det.audit_image_url) {
        fallback.push({
          id: -1,
          detection_id: Number(det.id),
          media_type: 'image',
          file_path: det.audit_image_path || det.audit_image_url || '',
          file_size: null,
          created_at: det.created_at,
        });
      }
      if (det.video_path || det.video_url) {
        fallback.push({
          id: -2,
          detection_id: Number(det.id),
          media_type: 'video',
          file_path: det.video_path || det.video_url || '',
          file_size: null,
          created_at: det.created_at,
        });
      }
      const merged = [...media, ...fallback.filter((f) => !media.some((m) => m.file_path === f.file_path))];
      setCompareMedia(merged);
    } catch (error) {
      console.error(error);
      setCompareMedia([]);
    } finally {
      setCompareLoading(false);
    }
  };

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
                <th className={dt.pad}>Ảnh Xác Minh</th>
                <th className={dt.pad}>Trạng Thái</th>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && detections.length === 0 ? (
                <tr>
                  <td colSpan={6} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredDetections.length > 0 ? (
                filteredDetections.map((det) => (
                  <tr
                    key={det.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/2 transition-colors"
                  >
                    <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                      {(() => {
                        const iso = getDetectionDisplayTimeIso(det);
                        return formatDateTimeVN(iso);
                      })()}
                    </td>
                    <td className={cn(dt.pad, dt.body, 'font-bold uppercase')}>
                      {getDetectionShipLabel(det)}
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'text-blue-600 dark:text-blue-400')}>
                      {(((det.confidence ?? 0) as number) * 100).toFixed(1)}%
                    </td>
                    <td className={dt.pad}>
                      {(() => {
                        const imageUrl = resolveImageUrl(det);
                        if (!imageUrl) {
                          return <span className={cn(dt.meta, 'normal-case')}>Chưa có ảnh</span>;
                        }
                        return (
                          <button
                            type="button"
                            onClick={() => setPreviewImageUrl(imageUrl)}
                            className="inline-flex items-center gap-2 rounded-lg border border-blue-500/20 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-blue-600 hover:bg-blue-500/10 dark:text-blue-400"
                          >
                            <Eye className="h-3.5 w-3.5" />
                            Xem ảnh
                          </button>
                        );
                      })()}
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
                      <button
                        type="button"
                        onClick={() => void openCompareModal(det)}
                        className="rounded-lg border border-blue-500/25 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-blue-600 hover:bg-blue-500/10 dark:text-blue-400"
                      >
                        Đối chiếu
                      </button>
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
                    colSpan={6}
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

      {previewImageUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Đóng xem ảnh"
            onClick={() => setPreviewImageUrl(null)}
          />
          <div className="relative z-10 w-full max-w-5xl rounded-2xl border border-white/15 bg-black p-3">
            <button
              type="button"
              className="absolute right-3 top-3 rounded-full bg-black/60 p-2 text-white hover:bg-black/80"
              onClick={() => setPreviewImageUrl(null)}
              aria-label="Đóng"
            >
              <X className="h-4 w-4" />
            </button>
            <img
              src={previewImageUrl}
              alt="Ảnh xác minh nhận diện tàu"
              className="max-h-[78vh] w-full rounded-xl object-contain"
            />
          </div>
        </div>
      )}

      {compareOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 sm:p-6">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Đóng đối chiếu"
            onClick={() => setCompareOpen(false)}
          />
          <div className="relative z-10 h-[90vh] w-full max-w-7xl overflow-hidden rounded-2xl border border-white/15 bg-[#0e1014]">
            <div className="flex items-center justify-between border-b border-white/10 px-4 py-3">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wider text-white">
                  Đối chiếu nhận diện
                </p>
                <p className="text-xs text-gray-300">Tàu: {compareShipLabel}</p>
              </div>
              <button
                type="button"
                className="rounded-full bg-white/10 p-2 text-white hover:bg-white/20"
                onClick={() => setCompareOpen(false)}
                aria-label="Đóng"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="h-[calc(90vh-61px)] overflow-y-auto p-4">
              {compareLoading ? (
                <div className="flex h-full items-center justify-center">
                  <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
                </div>
              ) : compareMedia.length === 0 ? (
                <div className="flex h-full items-center justify-center text-sm uppercase tracking-wider text-gray-400">
                  Không có ảnh/video đối chiếu cho detection này
                </div>
              ) : (
                <div className="space-y-6">
                  <div className="space-y-3">
                    <h4 className="text-xs font-bold uppercase tracking-widest text-gray-300">Ảnh xác minh</h4>
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      {compareMedia
                        .filter((m) => (m.media_type || '').toLowerCase() !== 'video')
                        .map((m) => {
                          const src = resolveMediaUrl(m.file_path);
                          if (!src) {
                            return null;
                          }
                          return (
                            <button
                              key={`img-${m.id}-${m.file_path}`}
                              type="button"
                              onClick={() => setPreviewImageUrl(src)}
                              className="overflow-hidden rounded-xl border border-white/10 bg-black/40"
                            >
                              <img src={src} alt="Ảnh đối chiếu" className="h-72 w-full object-cover" />
                            </button>
                          );
                        })}
                    </div>
                  </div>
                  <div className="space-y-3">
                    <h4 className="text-xs font-bold uppercase tracking-widest text-gray-300">Video xác minh</h4>
                    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                      {compareMedia
                        .filter((m) => (m.media_type || '').toLowerCase() === 'video')
                        .map((m) => {
                          const src = resolveMediaUrl(m.file_path);
                          if (!src) {
                            return null;
                          }
                          return (
                            <div
                              key={`video-${m.id}-${m.file_path}`}
                              className="overflow-hidden rounded-xl border border-white/10 bg-black/40 p-2"
                            >
                              <video controls preload="metadata" className="h-72 w-full rounded-lg object-contain">
                                <source src={src} type="video/mp4" />
                              </video>
                            </div>
                          );
                        })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
