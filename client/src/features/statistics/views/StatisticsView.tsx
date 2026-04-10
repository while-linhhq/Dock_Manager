import React, { useEffect, useState } from 'react';
import { 
  BarChart3, 
  Download, 
  Search, 
  Calendar, 
  Ship, 
  Loader2, 
  RefreshCw,
  FileSpreadsheet,
  Info
} from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { useStatisticsStore } from '../store/statisticsStore';

export const StatisticsView: React.FC = () => {
  const { logs, isLoading, fetchLogs, exportLogs } = useStatisticsStore();
  const [shipId, setShipId] = useState('');
  const [logDate, setLogDate] = useState('');

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  const handleSearch = () => {
    fetchLogs(0, 100, shipId || undefined, logDate || undefined);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Filters */}
      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Mã Tàu</label>
            <div className="relative">
              <Ship className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="text" 
                value={shipId}
                onChange={(e) => setShipId(e.target.value)}
                placeholder="Nhập mã tàu..." 
                className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
          </div>
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Ngày Ghi Nhật Ký</label>
            <div className="relative">
              <Calendar className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="date" 
                value={logDate}
                onChange={(e) => setLogDate(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
          </div>
          <div className="flex space-x-2">
            <Button onClick={handleSearch} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              <Search className="w-4 h-4 mr-2" />
              Tìm Kiếm
            </Button>
            <Button 
              variant="outline" 
              onClick={() => exportLogs(logDate || undefined, shipId || undefined)}
              className="border-emerald-500/50 text-emerald-500 hover:bg-emerald-500/10"
            >
              <FileSpreadsheet className="w-4 h-4 mr-2" />
              Xuất Excel
            </Button>
          </div>
        </div>
      </div>

      {/* Logs Table */}
      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-white/5 flex justify-between items-center">
          <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Nhật Ký Cảng Tàu</h3>
          <span className="text-[10px] font-mono text-gray-500 uppercase">Tổng số: {logs.length} bản ghi</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                <th className="px-6 py-4">Thời Gian</th>
                <th className="px-6 py-4">Mã Tàu</th>
                <th className="px-6 py-4">Loại Sự Kiện</th>
                <th className="px-6 py-4">Chi Tiết</th>
                <th className="px-6 py-4 text-right">Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && logs.length === 0 ? (
                <tr><td colSpan={5} className="px-6 py-12 text-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" /></td></tr>
              ) : logs.length > 0 ? (
                logs.map((log) => (
                  <tr key={log.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors">
                    <td className="px-6 py-4 text-[10px] font-mono text-gray-400">
                      {new Date(log.log_date).toLocaleString('vi-VN')}
                    </td>
                    <td className="px-6 py-4 font-mono text-xs font-bold text-blue-500">{log.ship_id}</td>
                    <td className="px-6 py-4">
                      <span className="px-2 py-1 bg-gray-100 dark:bg-white/5 rounded text-[9px] font-bold uppercase tracking-tighter text-gray-600 dark:text-gray-400 border border-gray-200 dark:border-white/10">
                        {log.event_type}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-xs text-gray-600 dark:text-gray-300 max-w-xs truncate">
                      {log.details || '---'}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button className="p-1.5 text-gray-400 hover:text-blue-500 transition-colors">
                        <Info className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr><td colSpan={5} className="px-6 py-12 text-center text-gray-500 text-xs uppercase font-mono">Không tìm thấy nhật ký</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
