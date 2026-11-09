import React from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { PortLogRead } from '../../../types/api.types';
import {
  PORT_LOG_TABLE_COL_COUNT,
  fmtConf,
  fmtDateTime,
  fmtInt,
  fmtNullableStr,
  formatVoteSummary,
  portLogTimeIso,
} from '../utils/port-log-display';
import { StatisticsLogTd, StatisticsLogTh } from './statistics-log-table-cells';
import { DataPagination } from '../../../components/DataPagination';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import {
  isPortLogSortKey,
  type PortLogSort,
} from '../services/statisticsApi';
import {
  useTableSort,
  type SortAccessors,
  type SortDirection,
  type SortState,
} from '../../../hooks/useTableSort';

export type StatisticsLogsTableProps = {
  isLoading: boolean;
  error: string | null;
  /** Đúng MỘT trang nhật ký lấy từ server (không phải toàn bộ tập kết quả). */
  logs: PortLogRead[];
  /** Phân trang phía server — state do `usePagedQuery` ở `StatisticsView` giữ. */
  total: number;
  page: number;
  pageSize: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (size: number) => void;
  /** Đổi cột sắp xếp → server nạp lại trang 1 với `sort`/`order` mới. */
  onSortChange: (sort: PortLogSort) => void;
  /** Map 'SHIP_ID|YYYY-MM-DD' (ngày VN) → số lượt neo ngoài giờ trong ngày đó. */
  outsideCountByShipDate: Map<string, number>;
};

/**
 * Mặc định của bảng: không cột nào được chọn nên không gửi `sort`/`order` —
 * server trả về đúng thứ tự `time desc` như trước.
 */
const INITIAL_LOG_SORT: SortState = { key: null, direction: 'asc' };

// Ngày VN 'YYYY-MM-DD' của một thời điểm ISO (dùng để khớp với summary theo ngày).
function vnDateKey(iso: string | null | undefined): string | null {
  if (!iso) {
    return null;
  }
  const d = new Date(/(?:Z|[+-]\d{2}:\d{2})$/i.test(iso.trim()) ? iso.trim() : `${iso.trim()}Z`);
  if (Number.isNaN(d.getTime())) {
    return null;
  }
  // en-CA cho định dạng YYYY-MM-DD; timeZone ép về giờ VN.
  return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' });
}

// Header sort dùng SortableTh nhưng vẫn giữ dáng của StatisticsLogTh (nền/viền/uppercase).
const logThSort =
  'px-4 py-3.5 sm:px-4 sm:py-3.5 align-bottom text-xs sm:text-sm font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.02] whitespace-nowrap';

export const StatisticsLogsTable: React.FC<StatisticsLogsTableProps> = ({
  isLoading,
  error,
  logs,
  total,
  page,
  pageSize,
  onPageChange,
  onPageSizeChange,
  onSortChange,
  outsideCountByShipDate,
}) => {
  // Sắp xếp do SERVER thực hiện: `useTableSort` chỉ giữ trạng thái mũi tên trên
  // tiêu đề (`sorted` không dùng — thứ tự trong trang là của server).
  const sortAccessors: SortAccessors<PortLogRead> = {
    time: (log) => portLogTimeIso(log),
    voted_ship_id: (log) => log.voted_ship_id ?? '',
  };
  const { sort, setSort } = useTableSort(logs, sortAccessors, INITIAL_LOG_SORT);

  /** Đổi cột/chiều: cập nhật mũi tên rồi báo server nạp lại trang 1. */
  const handleSortChange = (key: string) => {
    if (!isPortLogSortKey(key)) {
      return;
    }
    const direction: SortDirection =
      sort.key === key && sort.direction === 'asc' ? 'desc' : 'asc';
    setSort({ key, direction });
    onSortChange({ key, order: direction });
  };

  return (
    <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
      <div className="p-4 md:p-6 border-b border-gray-200 dark:border-white/5 flex justify-between items-center flex-wrap gap-2">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Nhật ký cảng (OCR / port log)
        </h3>
        <div className="flex items-center gap-3">
          {error && <span className="text-[12px] normal-case text-red-500">{error}</span>}
          <span className="text-xs sm:text-sm font-mono text-gray-500 dark:text-gray-400 uppercase">
            {logs.length}/{total} · scroll ngang để xem đủ cột
          </span>
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-max min-w-full text-left border-collapse">
          <thead>
            <tr>
              <StatisticsLogTh title="Khóa DB">id</StatisticsLogTh>
              <StatisticsLogTh title="ships_completed_today — tàu hoàn thành trong ngày (OCR audit)">
                ships_today
              </StatisticsLogTh>
              <SortableTh sortKey="time" sort={sort} onSort={handleSortChange} className={logThSort}>
                logged_at
              </SortableTh>
              <StatisticsLogTh title="track_id">track_id</StatisticsLogTh>
              <StatisticsLogTh title="first_seen_at">first_seen</StatisticsLogTh>
              <StatisticsLogTh title="last_seen_at">last_seen</StatisticsLogTh>
              <StatisticsLogTh title="confidence (YOLO / track)">confidence</StatisticsLogTh>
              <SortableTh sortKey="voted_ship_id" sort={sort} onSort={handleSortChange} className={logThSort}>
                voted_ship_id
              </SortableTh>
              <StatisticsLogTh title="Số lượt tàu này neo NGOÀI khung giờ cho phép trong ngày (theo mã tàu · ngày VN)">
                lượt neo ngoài giờ (ngày)
              </StatisticsLogTh>
              <StatisticsLogTh title="ocr_attempts">ocr_attempts</StatisticsLogTh>
              <StatisticsLogTh
                title="vote_summary — { ship_id: { count, total_conf } }"
                className="min-w-[14rem]"
              >
                vote_summary
              </StatisticsLogTh>
            </tr>
          </thead>
          <tbody>
            {isLoading && logs.length === 0 ? (
              <tr>
                <td
                  colSpan={PORT_LOG_TABLE_COL_COUNT}
                  className="px-6 py-12 text-center text-sm text-gray-500 dark:text-gray-400"
                >
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                </td>
              </tr>
            ) : logs.length > 0 ? (
              logs.map((log) => {
                const shipsToday = log.ships_completed_today ?? log.seq;
                const voteText = formatVoteSummary(log);
                const shipKey = (log.voted_ship_id ?? log.ship_id ?? '').trim().toUpperCase();
                const dayKey = vnDateKey(portLogTimeIso(log));
                const outsideCount =
                  shipKey && dayKey
                    ? outsideCountByShipDate.get(`${shipKey}|${dayKey}`) ?? 0
                    : 0;
                return (
                  <tr
                    key={log.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors"
                  >
                    <StatisticsLogTd mono>{String(log.id)}</StatisticsLogTd>
                    <StatisticsLogTd mono>{fmtInt(shipsToday ?? null)}</StatisticsLogTd>
                    <StatisticsLogTd mono className="whitespace-nowrap">
                      {fmtDateTime(portLogTimeIso(log))}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono className="max-w-[11rem] break-all">
                      {log.track_id ?? 'null'}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono className="whitespace-nowrap">
                      {fmtDateTime(log.first_seen_at)}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono className="whitespace-nowrap">
                      {fmtDateTime(log.last_seen_at)}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono>{fmtConf(log.confidence)}</StatisticsLogTd>
                    <StatisticsLogTd mono className="font-bold text-blue-600 dark:text-blue-400">
                      {fmtNullableStr(log.voted_ship_id ?? undefined)}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono>
                      {outsideCount > 0 ? (
                        <span className="inline-flex items-center rounded-full bg-fuchsia-100 dark:bg-fuchsia-500/15 px-2 py-0.5 font-bold text-fuchsia-700 dark:text-fuchsia-300">
                          {outsideCount}
                        </span>
                      ) : (
                        <span className="text-gray-400 dark:text-gray-600">0</span>
                      )}
                    </StatisticsLogTd>
                    <StatisticsLogTd mono>{fmtInt(log.ocr_attempts)}</StatisticsLogTd>
                    <StatisticsLogTd mono className="max-w-md">
                      <pre className="m-0 max-h-32 overflow-auto whitespace-pre-wrap break-words text-xs leading-snug text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-black/30 rounded-lg p-2 border border-gray-100 dark:border-white/10">
                        {voteText}
                      </pre>
                    </StatisticsLogTd>
                  </tr>
                );
              })
            ) : (
              <tr>
                <td
                  colSpan={PORT_LOG_TABLE_COL_COUNT}
                  className={cn(dt.pad, 'py-12 text-center font-mono uppercase tracking-wide', dt.empty)}
                >
                  {total === 0 ? 'Không tìm thấy nhật ký' : 'Trang này không có bản ghi'}
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
  );
};
