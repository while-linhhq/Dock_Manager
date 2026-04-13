import React, { useMemo } from 'react';
import { Loader2, ScanSearch } from 'lucide-react';
import type { DetectionRead } from '../../../types/api.types';
import { cn } from '../../../utils/cn';
import { formatDateTimeVN } from '../../../utils/date-time';
import { getDetectionDisplayTimeIso, getDetectionShipLabel } from '../../../utils/detection-display';

const SIDEBAR_LIMIT = 18;

function formatShortDateTime(iso: string | null): string {
  return formatDateTimeVN(iso, {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

export type DashboardRecentDetectionsSidebarProps = {
  detections: DetectionRead[];
  isLoading: boolean;
};

export const DashboardRecentDetectionsSidebar: React.FC<DashboardRecentDetectionsSidebarProps> = ({
  detections,
  isLoading,
}) => {
  const rows = useMemo(
    () => detections.slice(0, SIDEBAR_LIMIT),
    [detections],
  );

  return (
    <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl p-5 shadow-xl space-y-3">
      <div className="flex items-start gap-2">
        <ScanSearch className="h-4 w-4 text-blue-500 shrink-0 mt-0.5" />
        <div className="min-w-0 flex-1">
          <h4 className="text-gray-900 dark:text-white font-bold uppercase tracking-widest text-xs">
            Nhận diện gần đây
          </h4>
          <p className="text-[10px] text-gray-500 dark:text-gray-400 mt-1 leading-relaxed">
            {rows.length}/{detections.length} mục hiển thị (mới nhất).
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-6 w-6 animate-spin text-blue-500" />
        </div>
      ) : rows.length === 0 ? (
        <p className="py-8 text-center text-[10px] font-mono uppercase tracking-wide text-gray-500">
          Không có dữ liệu nhận diện
        </p>
      ) : (
        <ul
          className="max-h-[min(22rem,55vh)] overflow-y-auto divide-y divide-gray-100 dark:divide-white/5 rounded-xl border border-gray-200 dark:border-white/10 bg-gray-50/50 dark:bg-white/2"
          aria-label="Danh sách nhận diện gần đây"
        >
          {rows.map((row) => {
            const iso = getDetectionDisplayTimeIso(row);
            const ship = getDetectionShipLabel(row);
            const accepted = row.is_accepted === true;
            return (
              <li key={row.id} className="px-3 py-2.5 text-[11px] leading-tight space-y-1">
                <p className="font-mono text-[10px] text-gray-500 dark:text-gray-400 tabular-nums">
                  {formatShortDateTime(iso)}
                </p>
                <p className="font-bold text-gray-900 dark:text-white truncate" title={ship}>
                  {ship}
                </p>
                <span
                  className={cn(
                    'inline-block rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-tight',
                    accepted
                      ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                      : 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
                  )}
                >
                  {accepted ? 'Đã xác nhận' : 'Chờ duyệt'}
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};
