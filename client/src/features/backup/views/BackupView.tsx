import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useBackupStore } from '../store/backupStore';
import type { AuditLogFilters } from '../services/backupApi';
import type { AuditLogRead } from '../../../types/api.types';
import { usePagedQuery } from '../../../hooks/usePagedQuery';
import { BackupFiltersBar } from '../components/BackupFiltersBar';
import { BackupAuditLogList } from '../components/BackupAuditLogList';

export const BackupView: React.FC = () => {
  const { fetchAuditLogsPage } = useBackupStore();
  const [q, setQ] = useState('');
  const [tableQ, setTableQ] = useState('');
  const [actionQ, setActionQ] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  // Bốn bộ lọc `/audit-logs/` có tham số ⇒ server lọc, client không lọc lại
  // (trước đây `filtered` lọc trên 50 dòng đã nạp).
  const auditLogFilters = useMemo<AuditLogFilters>(
    () => ({
      q: q.trim() || undefined,
      tableName: tableQ.trim() || undefined,
      action: actionQ.trim() || undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
    }),
    [q, tableQ, actionQ, dateFrom, dateTo],
  );

  const {
    items: auditLogs,
    total: auditLogsTotal,
    page: auditLogsPage,
    pageSize: auditLogsPageSize,
    isLoading: auditLogsLoading,
    error: auditLogsError,
    setPage: setAuditLogsPage,
    setPageSize: setAuditLogsPageSize,
    setFilters: setAuditLogFilters,
    reload: reloadAuditLogs,
  } = usePagedQuery<AuditLogRead, AuditLogFilters>({
    fetcher: fetchAuditLogsPage,
    filters: auditLogFilters,
  });

  // Đẩy nội dung bộ lọc xuống hook; object đã memo hoá nên hiệu ứng chỉ chạy khi
  // bộ lọc THỰC SỰ đổi. Bỏ qua lần chạy đầu vì hook đã KHỞI TẠO bằng chính
  // `auditLogFilters` (đẩy lại đúng object đó chỉ thêm một request thừa lúc mở trang).
  const pushedAuditLogFiltersRef = useRef(auditLogFilters);
  useEffect(() => {
    if (pushedAuditLogFiltersRef.current === auditLogFilters) {
      return;
    }
    pushedAuditLogFiltersRef.current = auditLogFilters;
    setAuditLogFilters(auditLogFilters);
  }, [auditLogFilters, setAuditLogFilters]);

  const filterCount =
    (q.trim() ? 1 : 0) +
    (tableQ.trim() ? 1 : 0) +
    (actionQ.trim() ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0);

  const reset = () => {
    setQ('');
    setTableQ('');
    setActionQ('');
    setDateFrom('');
    setDateTo('');
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <BackupFiltersBar
        q={q}
        setQ={setQ}
        tableQ={tableQ}
        setTableQ={setTableQ}
        actionQ={actionQ}
        setActionQ={setActionQ}
        dateFrom={dateFrom}
        setDateFrom={setDateFrom}
        dateTo={dateTo}
        setDateTo={setDateTo}
        onReset={reset}
        filterCount={filterCount}
      />

      <BackupAuditLogList
        isLoading={auditLogsLoading}
        error={auditLogsError}
        auditLogs={auditLogs}
        total={auditLogsTotal}
        filterCount={filterCount}
        page={auditLogsPage}
        pageSize={auditLogsPageSize}
        onPageChange={setAuditLogsPage}
        onPageSizeChange={setAuditLogsPageSize}
        onRefresh={reloadAuditLogs}
      />
    </div>
  );
};
