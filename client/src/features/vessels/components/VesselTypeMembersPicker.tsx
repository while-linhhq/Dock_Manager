import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { vesselsApi, type AssignableVessel } from '../services/vesselsApi';

export type VesselTypeMembersPickerProps = {
  /** id loại tàu đang sửa; null = đang tạo mới (chưa có thành viên sẵn). */
  editingTypeId: string | null;
  /** id tàu đang được chọn (controlled). */
  selectedIds: number[];
  onChange: (ids: number[]) => void;
  onLoadingChange?: (loading: boolean) => void;
};

/**
 * Picker gán tàu (tháng) vào một loại. Danh sách nguồn = tàu tháng + chưa phân loại
 * (loại trừ tàu lẻ). Khi sửa loại đã có, tự tick sẵn các tàu đang thuộc loại đó.
 */
export const VesselTypeMembersPicker: React.FC<VesselTypeMembersPickerProps> = ({
  editingTypeId,
  selectedIds,
  onChange,
  onLoadingChange,
}) => {
  const [all, setAll] = useState<AssignableVessel[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');

  // Tải danh sách tàu gán được + (nếu đang sửa) tàu hiện thuộc loại để tick sẵn.
  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setIsLoading(true);
      onLoadingChange?.(true);
      setError(null);
      try {
        const [assignable, members] = await Promise.all([
          vesselsApi.getAssignableVessels(),
          editingTypeId ? vesselsApi.getVesselTypeMembers(editingTypeId) : Promise.resolve([]),
        ]);
        if (cancelled) return;
        setAll(assignable);
        // Chỉ khởi tạo lựa chọn ban đầu từ member hiện có (khi sửa).
        onChange(members.map((m) => m.id));
      } catch (err) {
        if (cancelled) return;
        console.error(err);
        setError('Không tải được danh sách tàu để gán.');
      } finally {
        if (!cancelled) {
          setIsLoading(false);
          onLoadingChange?.(false);
        }
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editingTypeId, onLoadingChange]);

  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase();
    if (!kw) return all;
    return all.filter(
      (v) =>
        v.ship_id.toLowerCase().includes(kw) || (v.name ?? '').toLowerCase().includes(kw),
    );
  }, [all, q]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const toggle = (id: number) => {
    const next = new Set(selectedSet);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onChange([...next]);
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
          Gán Tàu Tháng Vào Loại
        </label>
        <span className="text-[10px] font-mono text-gray-400">
          Đã chọn {selectedIds.length}
        </span>
      </div>
      <p className="text-[10px] normal-case tracking-normal text-gray-400">
        Tick tàu để gán vào loại này (tàu sẽ thành «tàu tháng»). Bỏ tick để gỡ (về «chưa phân
        loại»). Danh sách gồm tàu tháng và tàu chưa phân loại; không có tàu lẻ.
      </p>

      <div className="relative">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-gray-400" />
        <input
          type="text"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Tìm theo mã / tên tàu..."
          className="w-full rounded-xl border border-gray-200 bg-gray-50 py-2 pl-9 pr-3 text-sm font-mono transition-all focus:border-blue-500 focus:ring-0 dark:border-white/10 dark:bg-white/5 dark:text-white"
        />
      </div>

      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[11px] font-medium text-red-600 dark:bg-red-500/10 dark:text-red-400">
          {error}
        </p>
      ) : null}

      <div className="max-h-64 overflow-y-auto rounded-xl border border-gray-200 dark:border-white/10">
        {isLoading ? (
          <div className="flex items-center gap-2 px-3 py-4 text-xs text-gray-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Đang tải danh sách tàu...
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-3 py-4 text-xs text-gray-500">
            {all.length === 0 ? 'Không có tàu nào để gán.' : 'Không có tàu khớp từ khóa.'}
          </p>
        ) : (
          <ul className="divide-y divide-gray-100 dark:divide-white/5">
            {filtered.map((v) => {
              const checked = selectedSet.has(v.id);
              // Tàu đang thuộc loại KHÁC (monthly + vessel_type_id != đang sửa) → cảnh báo di chuyển.
              const boundElsewhere =
                v.classification === 'monthly' &&
                v.vessel_type_id != null &&
                String(v.vessel_type_id) !== (editingTypeId ?? '') &&
                !checked;
              return (
                <li key={v.id}>
                  <label
                    className={cn(
                      'flex cursor-pointer items-center gap-3 px-3 py-2 transition-colors hover:bg-gray-50 dark:hover:bg-white/5',
                      checked && 'bg-blue-50/60 dark:bg-blue-500/10',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggle(v.id)}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-mono text-sm font-semibold text-blue-600 dark:text-blue-400">
                        {v.ship_id}
                      </span>
                      <span className="block truncate text-xs text-gray-500 dark:text-gray-400">
                        {v.name || '—'}
                      </span>
                    </span>
                    {boundElsewhere ? (
                      <span className="shrink-0 rounded bg-amber-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-amber-700 dark:bg-amber-500/15 dark:text-amber-400">
                        Đang thuộc loại khác
                      </span>
                    ) : v.classification === 'unclassified' ? (
                      <span className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-gray-500 dark:bg-white/10 dark:text-gray-400">
                        Chưa phân loại
                      </span>
                    ) : null}
                  </label>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
};
