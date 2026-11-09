import React, { useMemo, useState } from 'react';
import {
  CheckCircle2,
  Loader2,
  Pencil,
  RefreshCw,
  Trash2,
  X,
  XCircle,
} from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { OverBerthLimitBadge } from '../../../components/Badge/OverBerthLimitBadge';
import { DataPagination } from '../../../components/DataPagination';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import { formatDateTimeVN } from '../../../utils/date-time';
import {
  formatBerthDuration,
  getBerthDurationRange,
  getDetectionDisplayTimeIso,
  getDetectionShipLabel,
} from '../../../utils/detection-display';
import type { DetectionMediaRead, DetectionRead, VesselRead, VesselTypeRead } from '../../../types/api.types';
import {
  isDetectionSortKey,
  portApi,
  type DetectionSort,
  type DetectionUpdate,
} from '../services/portApi';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import {
  useTableSort,
  type SortAccessors,
  type SortDirection,
  type SortState,
} from '../../../hooks/useTableSort';

export type PortDetectionsSectionProps = {
  detQ: string;
  setDetQ: (v: string) => void;
  detAccepted: 'all' | 'yes' | 'no';
  setDetAccepted: (v: 'all' | 'yes' | 'no') => void;
  detShipIdFilter: string;
  setDetShipIdFilter: (v: string) => void;
  detVesselTypeFilter: string;
  setDetVesselTypeFilter: (v: string) => void;
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
  error: string | null;
  /** Đúng MỘT trang nhận diện lấy từ server (không phải toàn bộ tập kết quả). */
  detections: DetectionRead[];
  /** Phân trang phía server — state do `usePagedQuery` ở PortView giữ. */
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  /** Đổi cột sắp xếp → server nạp lại trang 1 với `sort`/`order` mới. */
  onSortChange: (sort: DetectionSort) => void;
  vessels: VesselRead[];
  vesselTypes: VesselTypeRead[];
  onVerify: (id: string, data: { is_accepted: boolean }) => void;
  onDeleteDetection: (id: string) => void;
  onUpdateDetection: (id: string, data: DetectionUpdate) => Promise<void>;
};

/**
 * Mặc định của bảng: không cột nào được chọn nên không gửi `sort`/`order` —
 * server trả về đúng thứ tự `berth desc` như trước. Cột "neo đậu" không có tiêu
 * đề để gắn mũi tên nên không cột nào hiện trạng thái sắp xếp là đúng.
 */
const INITIAL_DET_SORT: SortState = { key: null, direction: 'asc' };

export const PortDetectionsSection: React.FC<PortDetectionsSectionProps> = ({
  detQ,
  setDetQ,
  detAccepted,
  setDetAccepted,
  detShipIdFilter,
  setDetShipIdFilter,
  detVesselTypeFilter,
  setDetVesselTypeFilter,
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
  error,
  detections,
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  onSortChange,
  vessels,
  vesselTypes,
  onVerify,
  onDeleteDetection,
  onUpdateDetection,
}) => {
  const [previewImageUrl, setPreviewImageUrl] = useState<string | null>(null);
  const [editDet, setEditDet] = useState<DetectionRead | null>(null);
  const [editForm, setEditForm] = useState<{
    vessel_id: string;
    start_time: string;
    end_time: string;
    berth_in_time: string;
    berth_out_time: string;
    confidence: string;
  }>({
    vessel_id: '',
    start_time: '',
    end_time: '',
    berth_in_time: '',
    berth_out_time: '',
    confidence: '',
  });
  const [editSaving, setEditSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [compareOpen, setCompareOpen] = useState(false);
  const [compareShipLabel, setCompareShipLabel] = useState<string>('—');
  const [compareMedia, setCompareMedia] = useState<DetectionMediaRead[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);

  // Sắp xếp do SERVER thực hiện (Task 12): `useTableSort` chỉ giữ trạng thái mũi
  // tên trên tiêu đề (`sorted` không dùng — thứ tự trong trang là của server).
  const sortAccessors: SortAccessors<DetectionRead> = {
    time: (d) => {
      const iso = getDetectionDisplayTimeIso(d);
      return iso ? new Date(iso) : null;
    },
    ship_id: (d) => getDetectionShipLabel(d),
    confidence: (d) => Number(d.confidence ?? 0),
    camera: (d) => d.berth_in_camera_name ?? '',
    status: (d) => (d.is_accepted === true ? 'Đã Xác Nhận' : 'Chờ Duyệt'),
  };
  const { sort, setSort } = useTableSort(detections, sortAccessors, INITIAL_DET_SORT);

  /**
   * Đổi cột/chiều: cập nhật mũi tên trên tiêu đề rồi báo server nạp lại trang 1
   * với `sort`/`order` mới (khóa cột trùng whitelist của API).
   *
   * Dùng `setSort` của `useTableSort` (thay vì `toggle`) để trạng thái mũi tên và
   * tham số gửi server luôn tính từ CÙNG một giá trị `direction`.
   */
  const handleSortChange = (key: string) => {
    if (!isDetectionSortKey(key)) {
      return;
    }
    const direction: SortDirection =
      sort.key === key && sort.direction === 'asc' ? 'desc' : 'asc';
    setSort({ key, direction });
    onSortChange({ key, order: direction });
  };

  const mediaOrigin = useMemo(() => {
    const apiBase = (import.meta.env.VITE_API_BASE_URL || '').trim();
    const proxyTarget = (import.meta.env.VITE_API_PROXY_TARGET || '').trim();

    if (/^https?:\/\//i.test(apiBase)) {
      try {
        return new URL(apiBase).origin;
      } catch {
        // ignore invalid env and continue fallback chain
      }
    }

    if (proxyTarget && !/^https?:\/\//i.test(apiBase)) {
      try {
        return new URL(proxyTarget).origin;
      } catch {
        // ignore invalid env and continue fallback chain
      }
    }

    if (typeof window !== 'undefined' && window.location?.origin) {
      return window.location.origin;
    }
    return '';
  }, []);

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
      if (media.length > 0) {
        setCompareMedia(media);
      } else {
        // Fallback to detection-level paths only when the media table has no records
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
        setCompareMedia(fallback);
      }
    } catch (error) {
      console.error(error);
      setCompareMedia([]);
    } finally {
      setCompareLoading(false);
    }
  };

  // ISO (UTC) -> giá trị input datetime-local (giờ địa phương, không có 'Z').
  const isoToLocalInput = (iso?: string | null): string => {
    if (!iso) {
      return '';
    }
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      return '';
    }
    const pad = (n: number) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  // input datetime-local (giờ địa phương) -> ISO UTC để gửi backend.
  const localInputToIso = (value: string): string | null => {
    const v = (value || '').trim();
    if (!v) {
      return null;
    }
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) {
      return null;
    }
    return d.toISOString();
  };

  const openEditModal = (det: DetectionRead) => {
    setEditError(null);
    setEditDet(det);
    setEditForm({
      vessel_id: det.vessel_id != null ? String(det.vessel_id) : '',
      start_time: isoToLocalInput(det.start_time),
      end_time: isoToLocalInput(det.end_time),
      berth_in_time: isoToLocalInput(det.berth_in_time),
      berth_out_time: isoToLocalInput(det.berth_out_time),
      confidence:
        det.confidence != null ? String((Number(det.confidence) * 100).toFixed(1)) : '',
    });
  };

  const closeEditModal = () => {
    setEditDet(null);
    setEditError(null);
    setEditSaving(false);
  };

  const submitEdit = async () => {
    if (!editDet) {
      return;
    }
    setEditError(null);

    const payload: DetectionUpdate = {
      vessel_id: editForm.vessel_id ? Number(editForm.vessel_id) : null,
      start_time: localInputToIso(editForm.start_time),
      end_time: localInputToIso(editForm.end_time),
      berth_in_time: localInputToIso(editForm.berth_in_time),
      berth_out_time: localInputToIso(editForm.berth_out_time),
    };

    const confTrim = editForm.confidence.trim();
    if (confTrim) {
      const pct = Number(confTrim);
      if (!Number.isFinite(pct) || pct < 0 || pct > 100) {
        setEditError('Độ tin cậy phải trong khoảng 0–100.');
        return;
      }
      payload.confidence = pct / 100;
    }

    if (
      payload.start_time &&
      payload.end_time &&
      new Date(payload.end_time).getTime() < new Date(payload.start_time).getTime()
    ) {
      setEditError('Thời gian kết thúc phải sau thời gian bắt đầu.');
      return;
    }

    setEditSaving(true);
    try {
      await onUpdateDetection(editDet.id, payload);
      closeEditModal();
    } catch (err: unknown) {
      setEditError(err instanceof Error ? err.message : 'Cập nhật thất bại.');
      setEditSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <TableFilterPanel onReset={resetDetFilters} activeCount={detFilterCount}>
        <FilterField label="Từ khóa (mã tàu / ID nhận diện / vessel id)">
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
        <FilterField label="Mã tàu">
          <select
            value={detShipIdFilter}
            onChange={(e) => setDetShipIdFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vessels.map((vessel) => (
              <option key={vessel.id} value={String(vessel.id)}>
                {vessel.ship_id}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Loại tàu">
          <select
            value={detVesselTypeFilter}
            onChange={(e) => setDetVesselTypeFilter(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {vesselTypes.map((type) => (
              <option key={type.id} value={String(type.id)}>
                {type.type_name}
              </option>
            ))}
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

      <div className="flex flex-wrap items-center justify-end gap-3">
        {error && <p className="mr-auto text-[12px] normal-case text-red-500">{error}</p>}
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
                <SortableTh sortKey="time" sort={sort} onSort={handleSortChange}>
                  Thời Gian
                </SortableTh>
                <th className={dt.pad}>Thời Lượng Neo Đậu</th>
                <SortableTh sortKey="ship_id" sort={sort} onSort={handleSortChange}>
                  Mã Tàu
                </SortableTh>
                <SortableTh sortKey="confidence" sort={sort} onSort={handleSortChange}>
                  Độ Tin Cậy
                </SortableTh>
                <SortableTh sortKey="camera" sort={sort} onSort={handleSortChange}>
                  Camera IN / OUT
                </SortableTh>
                <SortableTh sortKey="status" sort={sort} onSort={handleSortChange}>
                  Trạng Thái
                </SortableTh>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && detections.length === 0 ? (
                <tr>
                  <td colSpan={7} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : detections.length > 0 ? (
                detections.map((det) => (
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
                    <td
                      className={cn(dt.pad, dt.mono, 'text-gray-600 dark:text-gray-300')}
                      title={det.track_id ?? undefined}
                    >
                      <span className="block font-semibold">{formatBerthDuration(det)}</span>
                      {(() => {
                        const range = getBerthDurationRange(det);
                        if (!range) {
                          return null;
                        }
                        return (
                          <span className="block text-[10px] text-gray-400 dark:text-gray-500 normal-case">
                            ({range.source}: {range.from} → {range.to})
                          </span>
                        );
                      })()}
                    </td>
                    <td className={cn(dt.pad, dt.body, 'font-bold uppercase')}>
                      <div className="flex flex-wrap items-center gap-2">
                        <span>{getDetectionShipLabel(det)}</span>
                        {det.is_over_berth_limit ? <OverBerthLimitBadge /> : null}
                      </div>
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'text-blue-600 dark:text-blue-400')}>
                      {(((det.confidence ?? 0) as number) * 100).toFixed(1)}%
                    </td>
                    <td className={cn(dt.pad, 'normal-case')}>
                      <div className="flex flex-col gap-0.5 text-[11px]">
                        <span className="text-gray-600 dark:text-gray-300">
                          <span className="text-emerald-600 dark:text-emerald-400 font-semibold">IN:</span>{' '}
                          {det.berth_in_camera_name ?? '—'}
                        </span>
                        <span className="text-gray-600 dark:text-gray-300">
                          <span className="text-red-500 dark:text-red-400 font-semibold">OUT:</span>{' '}
                          {det.berth_out_camera_name ?? '—'}
                        </span>
                      </div>
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
                      <button
                        type="button"
                        onClick={() => openEditModal(det)}
                        title="Chỉnh sửa"
                        className="p-1.5 text-indigo-500 hover:bg-indigo-500/10 rounded-lg transition-all"
                      >
                        <Pencil className="w-4 h-4" />
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
                    colSpan={7}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {total === 0
                      ? detFilterCount > 0
                        ? 'Không có bản ghi khớp bộ lọc'
                        : 'Không có dữ liệu nhận diện'
                      : 'Trang này không có bản ghi'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <DataPagination
          page={page}
          pageSize={pageSize}
          total={total}
          onPageChange={onPageChange}
          onPageSizeChange={onPageSizeChange}
        />
      </div>

      {previewImageUrl && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 lg:pl-[calc(256px+1rem)]">
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

      {editDet && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 lg:pl-[calc(256px+1rem)]">
          <button
            type="button"
            className="absolute inset-0"
            aria-label="Đóng chỉnh sửa"
            onClick={closeEditModal}
          />
          <div className="relative z-10 w-full max-w-lg rounded-2xl border border-gray-200 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#121214]">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-sm font-semibold uppercase tracking-wider text-gray-800 dark:text-white">
                  Chỉnh sửa nhận diện
                </p>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Tàu: {getDetectionShipLabel(editDet)} · Track: {editDet.track_id ?? '—'}
                </p>
              </div>
              <button
                type="button"
                className="rounded-full bg-gray-100 p-2 text-gray-600 hover:bg-gray-200 dark:bg-white/10 dark:text-white dark:hover:bg-white/20"
                onClick={closeEditModal}
                aria-label="Đóng"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-3">
              <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                Mã tàu (vessel)
                <select
                  value={editForm.vessel_id}
                  onChange={(e) => setEditForm((f) => ({ ...f, vessel_id: e.target.value }))}
                  className={cn(filterControlClass, 'mt-1 normal-case')}
                >
                  <option value="">— Không gán —</option>
                  {vessels.map((vessel) => (
                    <option key={vessel.id} value={String(vessel.id)}>
                      {vessel.ship_id}
                    </option>
                  ))}
                </select>
              </label>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                  Bắt đầu
                  <input
                    type="datetime-local"
                    value={editForm.start_time}
                    onChange={(e) => setEditForm((f) => ({ ...f, start_time: e.target.value }))}
                    className={cn(filterControlClass, 'mt-1 normal-case')}
                  />
                </label>
                <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                  Kết thúc
                  <input
                    type="datetime-local"
                    value={editForm.end_time}
                    onChange={(e) => setEditForm((f) => ({ ...f, end_time: e.target.value }))}
                    className={cn(filterControlClass, 'mt-1 normal-case')}
                  />
                </label>
                <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                  Vào vùng (berth in)
                  <input
                    type="datetime-local"
                    value={editForm.berth_in_time}
                    onChange={(e) => setEditForm((f) => ({ ...f, berth_in_time: e.target.value }))}
                    className={cn(filterControlClass, 'mt-1 normal-case')}
                  />
                </label>
                <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                  Rời vùng (berth out)
                  <input
                    type="datetime-local"
                    value={editForm.berth_out_time}
                    onChange={(e) => setEditForm((f) => ({ ...f, berth_out_time: e.target.value }))}
                    className={cn(filterControlClass, 'mt-1 normal-case')}
                  />
                </label>
              </div>

              <label className="block text-[11px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                Độ tin cậy (%)
                <input
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={editForm.confidence}
                  onChange={(e) => setEditForm((f) => ({ ...f, confidence: e.target.value }))}
                  placeholder="VD: 87.5"
                  className={cn(filterControlClass, 'mt-1 normal-case')}
                />
              </label>

              <p className="rounded-lg bg-amber-500/10 px-3 py-2 text-[11px] normal-case text-amber-600 dark:text-amber-400">
                Lưu thay đổi sẽ tự động tính lại hóa đơn AI của nhận diện này (trừ khi hóa đơn đã thanh toán).
              </p>

              {editError && (
                <p className="text-[12px] normal-case text-red-500">{editError}</p>
              )}
            </div>

            <div className="mt-5 flex gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={closeEditModal}
                className="flex-1"
                disabled={editSaving}
              >
                Hủy
              </Button>
              <Button
                type="button"
                onClick={() => void submitEdit()}
                disabled={editSaving}
                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
              >
                {editSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Lưu & Tính Lại Hóa Đơn'}
              </Button>
            </div>
          </div>
        </div>
      )}

      {compareOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-3 sm:p-6 lg:pl-[calc(256px+1.5rem)]">
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
