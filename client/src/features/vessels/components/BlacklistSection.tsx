import React, { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { useShipIdRulesStore } from '../store/shipIdRulesStore';
import { Button } from '../../../components/Button/Button';
import type { BlacklistRead } from '../types/ship-id-rules.types';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import { useTableSort, type SortAccessors } from '../../../hooks/useTableSort';

export const BlacklistSection: React.FC = () => {
  const { blacklist, createBlacklist, deleteBlacklist, convertMap } = useShipIdRulesStore();
  const [value, setValue] = useState('');
  const [reason, setReason] = useState('');
  const [isAdding, setIsAdding] = useState(false);

  const convertMapWrongs = new Set(convertMap.map((c) => c.wrong_value));
  const conflict = value.trim().toUpperCase() && convertMapWrongs.has(value.trim().toUpperCase());

  const sortAccessors: SortAccessors<BlacklistRead> = {
    value: (b) => b.value,
    reason: (b) => b.reason ?? '',
    created_at: (b) => (b.created_at ? new Date(b.created_at) : null),
  };
  const { sorted, sort, toggle } = useTableSort(blacklist, sortAccessors);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!value.trim()) {
      return;
    }
    setIsAdding(true);
    try {
      await createBlacklist({ value: value.trim(), reason: reason.trim() || undefined });
      setValue('');
      setReason('');
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Thêm vào blacklist thất bại';
      alert(message);
    } finally {
      setIsAdding(false);
    }
  };

  return (
    <div className="space-y-3">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Các giá trị OCR trong danh sách này sẽ bị loại bỏ hoàn toàn, không đưa vào bình chọn.
      </p>

      <form onSubmit={(e) => void handleAdd(e)} className="flex gap-2 items-start">
        <div className="flex-1 space-y-1.5">
          <input
            required
            className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-mono uppercase"
            placeholder="Giá trị OCR sai, vd: SC-9999"
            value={value}
            onChange={(e) => setValue(e.target.value.toUpperCase())}
          />
          {conflict ? (
            <p className="text-xs text-amber-500">
              Giá trị này đã có trong convert map — blacklist sẽ ưu tiên (từ chối thay vì chuyển đổi).
            </p>
          ) : null}
        </div>
        <input
          className="flex-1 px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
          placeholder="Lý do (tùy chọn)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
        <Button type="submit" disabled={isAdding || !value.trim()} className="flex items-center gap-1 text-xs px-3 py-2 shrink-0">
          <Plus className="w-3.5 h-3.5" /> Thêm
        </Button>
      </form>

      <div className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 uppercase tracking-wider">
            <tr>
              <SortableTh sortKey="value" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Giá trị bị chặn
              </SortableTh>
              <SortableTh sortKey="reason" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Lý do
              </SortableTh>
              <SortableTh sortKey="created_at" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Ngày thêm
              </SortableTh>
              <th className="px-3 py-2 text-right">Xóa</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-white/5">
            {blacklist.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-3 py-4 text-center text-gray-400">
                  Blacklist trống.
                </td>
              </tr>
            ) : null}
            {sorted.map((b) => (
              <tr key={b.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono font-semibold text-red-600 dark:text-red-400">
                  {b.value}
                </td>
                <td className="px-3 py-2 text-gray-500">{b.reason ?? '—'}</td>
                <td className="px-3 py-2 text-gray-400">
                  {b.created_at ? new Date(b.created_at).toLocaleString('vi-VN') : '—'}
                </td>
                <td className="px-3 py-2 text-right">
                  <button
                    type="button"
                    onClick={() => void deleteBlacklist(b.id)}
                    className="text-red-500 hover:text-red-400"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
