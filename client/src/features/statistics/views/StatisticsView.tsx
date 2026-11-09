import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useStatisticsStore } from '../store/statisticsStore';
import {
  statisticsApi,
  type PortLogFilters,
  type PortLogSort,
} from '../services/statisticsApi';
import { StatisticsFiltersBar } from '../components/StatisticsFiltersBar';
import { StatisticsLogsTable } from '../components/StatisticsLogsTable';
import { useFilterOptions } from '../../../hooks/useFilterOptions';
import { usePagedQuery } from '../../../hooks/usePagedQuery';
import type { PortLogRead } from '../../../types/api.types';

export const StatisticsView: React.FC = () => {
  const { outsideSummary, fetchOutsideSummary, exportLogs } = useStatisticsStore();
  const [shipId, setShipId] = useState('');
  const [vesselTypeFilter, setVesselTypeFilter] = useState('');
  const [trackQ, setTrackQ] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [minConf, setMinConf] = useState('');
  const { vessels, vesselTypes } = useFilterOptions();

  useEffect(() => {
    void fetchOutsideSummary();
  }, [fetchOutsideSummary]);

  // Lookup 'SHIP_ID|YYYY-MM-DD' → số lượt neo ngoài giờ trong ngày (VN).
  const outsideCountByShipDate = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of outsideSummary) {
      map.set(`${row.ship_id.trim().toUpperCase()}|${row.date}`, row.count);
    }
    return map;
  }, [outsideSummary]);

  // Sáu bộ lọc của trang đều có tham số phía server ⇒ không còn bộ lọc client
  // (trước đây `displayLogs` lọc trên tối đa 500 dòng đã nạp).
  const portLogFilters = useMemo<PortLogFilters>(
    () => ({
      shipId: shipId || undefined,
      q: trackQ.trim() || undefined,
      vesselTypeId: vesselTypeFilter || undefined,
      minConfidence: minConf.trim() || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    }),
    [shipId, trackQ, vesselTypeFilter, minConf, dateFrom, dateTo],
  );

  const {
    items: logs,
    total: logsTotal,
    page: logsPage,
    pageSize: logsPageSize,
    isLoading: logsLoading,
    error: logsError,
    setPage: setLogsPage,
    setPageSize: setLogsPageSize,
    setFilters: setPortLogFilters,
    setSort: setLogsSort,
    reload: reloadLogs,
  } = usePagedQuery<PortLogRead, PortLogFilters, PortLogSort>({
    fetcher: statisticsApi.getPortLogsPage,
    filters: portLogFilters,
  });

  // Đẩy nội dung bộ lọc xuống hook; object đã memo hoá nên hiệu ứng chỉ chạy khi
  // bộ lọc THỰC SỰ đổi. Bỏ qua lần chạy đầu vì hook đã KHỞI TẠO bằng chính
  // `portLogFilters` (đẩy lại đúng object đó chỉ thêm một request thừa lúc mở trang).
  const pushedPortLogFiltersRef = useRef(portLogFilters);
  useEffect(() => {
    if (pushedPortLogFiltersRef.current === portLogFilters) {
      return;
    }
    pushedPortLogFiltersRef.current = portLogFilters;
    setPortLogFilters(portLogFilters);
  }, [portLogFilters, setPortLogFilters]);

  const filterCount =
    (shipId.trim() ? 1 : 0) +
    (vesselTypeFilter ? 1 : 0) +
    (trackQ.trim() ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0) +
    (minConf.trim() ? 1 : 0);

  const resetFilters = () => {
    setShipId('');
    setVesselTypeFilter('');
    setTrackQ('');
    setDateFrom('');
    setDateTo('');
    setMinConf('');
  };

  // Mọi bộ lọc đã chạy ở server nên nút này chỉ còn nghĩa "nạp lại trang hiện tại".
  const handleReload = () => {
    reloadLogs();
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <StatisticsFiltersBar
        shipId={shipId}
        setShipId={setShipId}
        vesselTypeFilter={vesselTypeFilter}
        setVesselTypeFilter={setVesselTypeFilter}
        vessels={vessels}
        vesselTypes={vesselTypes}
        trackQ={trackQ}
        setTrackQ={setTrackQ}
        dateFrom={dateFrom}
        setDateFrom={setDateFrom}
        dateTo={dateTo}
        setDateTo={setDateTo}
        minConf={minConf}
        setMinConf={setMinConf}
        resetFilters={resetFilters}
        filterCount={filterCount}
        onReloadFromServer={handleReload}
        onExport={() => exportLogs(dateTo || dateFrom || undefined, shipId.trim() || undefined)}
      />

      <StatisticsLogsTable
        isLoading={logsLoading}
        error={logsError}
        logs={logs}
        total={logsTotal}
        page={logsPage}
        pageSize={logsPageSize}
        onPageChange={setLogsPage}
        onPageSizeChange={setLogsPageSize}
        onSortChange={setLogsSort}
        outsideCountByShipDate={outsideCountByShipDate}
      />
    </div>
  );
};
