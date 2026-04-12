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

export type StatisticsLogsTableProps = {
  isLoading: boolean;
  logs: PortLogRead[];
  displayLogs: PortLogRead[];
};

export const StatisticsLogsTable: React.FC<StatisticsLogsTableProps> = ({
  isLoading,
  logs,
  displayLogs,
}) => {
  return (
    <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
      <div className="p-4 md:p-6 border-b border-gray-200 dark:border-white/5 flex justify-between items-center flex-wrap gap-2">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Nhật ký cảng (OCR / port log)
        </h3>
        <span className="text-xs sm:text-sm font-mono text-gray-500 dark:text-gray-400 uppercase">
          {displayLogs.length}/{logs.length} · scroll ngang để xem đủ cột
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-max min-w-full text-left border-collapse">
          <thead>
            <tr>
              <StatisticsLogTh title="Khóa DB">id</StatisticsLogTh>
              <StatisticsLogTh title="ships_completed_today — tàu hoàn thành trong ngày (OCR audit)">
                ships_today
              </StatisticsLogTh>
              <StatisticsLogTh title="logged_at">logged_at</StatisticsLogTh>
              <StatisticsLogTh title="track_id">track_id</StatisticsLogTh>
              <StatisticsLogTh title="first_seen_at">first_seen</StatisticsLogTh>
              <StatisticsLogTh title="last_seen_at">last_seen</StatisticsLogTh>
              <StatisticsLogTh title="confidence (YOLO / track)">confidence</StatisticsLogTh>
              <StatisticsLogTh title="voted_ship_id (kết quả bỏ phiếu OCR)">voted_ship_id</StatisticsLogTh>
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
            ) : displayLogs.length > 0 ? (
              displayLogs.map((log) => {
                const shipsToday = log.ships_completed_today ?? log.seq;
                const voteText = formatVoteSummary(log);
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
                  {logs.length === 0 ? 'Không tìm thấy nhật ký' : 'Không có bản ghi khớp bộ lọc'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
