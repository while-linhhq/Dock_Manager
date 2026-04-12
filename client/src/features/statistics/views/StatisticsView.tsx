import React, { useEffect, useMemo, useState } from 'react';
import { useStatisticsStore } from '../store/statisticsStore';
import { isoInLocalDateRange } from '../../../utils/table-filters';
import { portLogShip, portLogTimeIso } from '../utils/port-log-display';
import { StatisticsFiltersBar } from '../components/StatisticsFiltersBar';
import { StatisticsLogsTable } from '../components/StatisticsLogsTable';

export const StatisticsView: React.FC = () => {
  const { logs, isLoading, fetchLogs, exportLogs } = useStatisticsStore();
  const [shipId, setShipId] = useState('');
  const [trackQ, setTrackQ] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [minConf, setMinConf] = useState('');

  useEffect(() => {
    fetchLogs(0, 500);
  }, [fetchLogs]);

  const displayLogs = useMemo(() => {
    return logs.filter((log) => {
      const sid = portLogShip(log);
      if (shipId.trim() && !sid.toLowerCase().includes(shipId.trim().toLowerCase())) {
        return false;
      }
      if (trackQ.trim() && !(log.track_id ?? '').toLowerCase().includes(trackQ.trim().toLowerCase())) {
        return false;
      }
      const iso = portLogTimeIso(log);
      if (!isoInLocalDateRange(iso ?? undefined, dateFrom, dateTo)) {
        return false;
      }
      if (minConf.trim()) {
        const c = Number(log.confidence ?? 0);
        if (c < Number(minConf)) {
          return false;
        }
      }
      return true;
    });
  }, [logs, shipId, trackQ, dateFrom, dateTo, minConf]);

  const filterCount =
    (shipId.trim() ? 1 : 0) +
    (trackQ.trim() ? 1 : 0) +
    (dateFrom ? 1 : 0) +
    (dateTo ? 1 : 0) +
    (minConf.trim() ? 1 : 0);

  const resetFilters = () => {
    setShipId('');
    setTrackQ('');
    setDateFrom('');
    setDateTo('');
    setMinConf('');
  };

  const handleApplyServerShip = () => {
    const s = shipId.trim();
    fetchLogs(0, 500, s || undefined, undefined);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <StatisticsFiltersBar
        shipId={shipId}
        setShipId={setShipId}
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
        onReloadFromServer={handleApplyServerShip}
        onExport={() => exportLogs(dateTo || dateFrom || undefined, shipId.trim() || undefined)}
      />

      <StatisticsLogsTable isLoading={isLoading} logs={logs} displayLogs={displayLogs} />
    </div>
  );
};
