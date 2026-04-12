import React, { useEffect, useMemo, useState } from 'react';
import { useBackupStore } from '../store/backupStore';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import { BackupFiltersBar } from '../components/BackupFiltersBar';
import { BackupAuditLogList } from '../components/BackupAuditLogList';

export const BackupView: React.FC = () => {
  const { auditLogs, isLoading, fetchAuditLogs } = useBackupStore();
  const [q, setQ] = useState('');
  const [tableQ, setTableQ] = useState('');
  const [actionQ, setActionQ] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  const filtered = useMemo(() => {
    return auditLogs.filter((log) => {
      if (
        !matchesAnyField(q, log.action, log.record_id, log.user?.full_name, log.user?.email)
      ) {
        return false;
      }
      if (
        tableQ.trim() &&
        !(log.table_name ?? '').toLowerCase().includes(tableQ.trim().toLowerCase())
      ) {
        return false;
      }
      if (
        actionQ.trim() &&
        !(log.action ?? '').toLowerCase().includes(actionQ.trim().toLowerCase())
      ) {
        return false;
      }
      if (!isoInLocalDateRange(log.created_at, dateFrom, dateTo)) {
        return false;
      }
      return true;
    });
  }, [auditLogs, q, tableQ, actionQ, dateFrom, dateTo]);

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
        isLoading={isLoading}
        auditLogs={auditLogs}
        filtered={filtered}
        onRefresh={() => fetchAuditLogs()}
      />
    </div>
  );
};
