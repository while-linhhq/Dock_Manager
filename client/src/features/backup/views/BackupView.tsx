import React, { useEffect, useState } from 'react';
import { 
  History, 
  Database, 
  Search, 
  User, 
  Clock, 
  FileCode, 
  Eye,
  Loader2,
  AlertCircle,
  Image as ImageIcon,
  Video
} from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { useBackupStore } from '../store/backupStore';

export const BackupView: React.FC = () => {
  const { auditLogs, isLoading, fetchAuditLogs } = useBackupStore();

  useEffect(() => {
    fetchAuditLogs();
  }, [fetchAuditLogs]);

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
        <div className="p-6 border-b border-gray-200 dark:border-white/5 flex justify-between items-center">
          <div className="flex items-center space-x-2">
            <History className="w-5 h-5 text-blue-500" />
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Lịch Sử Hệ Thống (Audit Logs)</h3>
          </div>
          <Button variant="outline" size="sm" onClick={() => fetchAuditLogs()} className="border-gray-200 dark:border-white/10 text-gray-500">
            Làm Mới
          </Button>
        </div>

        <div className="divide-y divide-gray-100 dark:divide-white/5">
          {isLoading && auditLogs.length === 0 ? (
            <div className="p-12 text-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" /></div>
          ) : auditLogs.length > 0 ? (
            auditLogs.map((log) => (
              <div key={log.id} className="p-6 hover:bg-gray-50 dark:hover:bg-white/[0.01] transition-colors group">
                <div className="flex items-start justify-between">
                  <div className="flex items-start space-x-4">
                    <div className="p-2 bg-blue-500/10 rounded-lg">
                      <FileCode className="w-4 h-4 text-blue-500" />
                    </div>
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-gray-900 dark:text-white uppercase tracking-tighter">
                          {log.action}
                        </span>
                        <span className="text-[10px] px-1.5 py-0.5 bg-gray-100 dark:bg-white/5 rounded text-gray-500 font-mono">
                          {log.table_name}
                        </span>
                      </div>
                      <p className="text-xs text-gray-500">
                        ID Bản ghi: <span className="font-mono text-blue-500">{log.record_id}</span>
                      </p>
                      <div className="flex items-center space-x-3 pt-1">
                        <div className="flex items-center text-[10px] text-gray-400 font-mono">
                          <User className="w-3 h-3 mr-1" />
                          {log.user?.full_name || 'Hệ Thống'}
                        </div>
                        <div className="flex items-center text-[10px] text-gray-400 font-mono">
                          <Clock className="w-3 h-3 mr-1" />
                          {new Date(log.created_at).toLocaleString('vi-VN')}
                        </div>
                      </div>
                    </div>
                  </div>
                  <button className="p-2 text-gray-400 hover:text-blue-500 opacity-0 group-hover:opacity-100 transition-all">
                    <Eye className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))
          ) : (
            <div className="p-12 text-center text-gray-500 text-xs uppercase font-mono tracking-widest">Không có dữ liệu lịch sử</div>
          )}
        </div>
      </div>
    </div>
  );
};
