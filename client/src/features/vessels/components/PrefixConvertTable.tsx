import React, { useState } from 'react';
import { Plus, Pencil, Trash2, ArrowRight } from 'lucide-react';
import { useShipIdRulesStore } from '../store/shipIdRulesStore';
import type { PrefixConvertCreate, PrefixConvertRead } from '../types/ship-id-rules.types';
import { Button } from '../../../components/Button/Button';
import { Modal } from '../../../components/Modal/Modal';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import { useTableSort, type SortAccessors } from '../../../hooks/useTableSort';

type FormValues = { from_prefix: string; to_prefix: string; reason: string };
const DEFAULT_FORM: FormValues = { from_prefix: '', to_prefix: '', reason: '' };

const PREFIX_RE = /^[A-Z]{1,10}$/;

export const PrefixConvertTable: React.FC = () => {
  const { prefixConvert, createPrefixConvert, updatePrefixConvert, deletePrefixConvert } =
    useShipIdRulesStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormValues>(DEFAULT_FORM);
  const [isSaving, setIsSaving] = useState(false);

  const sortAccessors: SortAccessors<PrefixConvertRead> = {
    from_prefix: (p) => p.from_prefix,
    to_prefix: (p) => p.to_prefix,
    reason: (p) => p.reason ?? '',
  };
  const { sorted, sort, toggle } = useTableSort(prefixConvert, sortAccessors);

  const from = form.from_prefix.trim().toUpperCase();
  const to = form.to_prefix.trim().toUpperCase();
  const sameError = !!from && !!to && from === to;
  const formatError =
    (!!from && !PREFIX_RE.test(from)) || (!!to && !PREFIX_RE.test(to));

  const openAdd = () => {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setIsModalOpen(true);
  };

  const openEdit = (p: PrefixConvertRead) => {
    setEditingId(p.id);
    setForm({ from_prefix: p.from_prefix, to_prefix: p.to_prefix, reason: p.reason ?? '' });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (sameError || formatError) {
      return;
    }
    setIsSaving(true);
    try {
      if (editingId !== null) {
        await updatePrefixConvert(editingId, {
          to_prefix: to,
          reason: form.reason.trim() || undefined,
        });
      } else {
        await createPrefixConvert({
          from_prefix: from,
          to_prefix: to,
          reason: form.reason.trim() || undefined,
        } as PrefixConvertCreate);
      }
      setIsModalOpen(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Lưu thất bại';
      alert(message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Đổi tiền tố (2 chữ đầu) khi OCR đọc nhầm, giữ nguyên phần số. Ví dụ SC-8168 → SG-8168.
          Áp dụng cho mọi biển bắt đầu bằng tiền tố nguồn. Convert Map (khớp cả biển) được ưu
          tiên hơn nếu trùng.
        </p>
        <Button type="button" onClick={openAdd} className="flex items-center gap-1 text-xs px-3 py-1.5 shrink-0">
          <Plus className="w-3.5 h-3.5" /> Thêm quy tắc
        </Button>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 uppercase tracking-wider">
            <tr>
              <SortableTh sortKey="from_prefix" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Tiền tố sai
              </SortableTh>
              <th className="px-3 py-2 text-center"></th>
              <SortableTh sortKey="to_prefix" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Tiền tố đúng
              </SortableTh>
              <SortableTh sortKey="reason" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Lý do
              </SortableTh>
              <th className="px-3 py-2 text-right">Hành động</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-white/5">
            {prefixConvert.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-gray-400">
                  Chưa có quy tắc nào.
                </td>
              </tr>
            ) : null}
            {sorted.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono font-semibold text-amber-600 dark:text-amber-400">
                  {p.from_prefix}-
                </td>
                <td className="px-3 py-2 text-center text-gray-400">
                  <ArrowRight className="w-3.5 h-3.5 inline" />
                </td>
                <td className="px-3 py-2 font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                  {p.to_prefix}-
                </td>
                <td className="px-3 py-2 text-gray-500">{p.reason ?? '—'}</td>
                <td className="px-3 py-2 text-right flex justify-end gap-2">
                  <button type="button" onClick={() => openEdit(p)} className="text-blue-500 hover:text-blue-400">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void deletePrefixConvert(p.id)}
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

      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingId ? 'Sửa quy tắc tiền tố' : 'Thêm quy tắc tiền tố'}
        className="max-w-md"
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {editingId === null ? (
            <div>
              <label className="block text-xs font-medium mb-1">Tiền tố sai *</label>
              <input
                required
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-mono uppercase"
                placeholder="vd: SC"
                value={form.from_prefix}
                onChange={(e) => setForm((f) => ({ ...f, from_prefix: e.target.value.toUpperCase() }))}
              />
            </div>
          ) : null}
          <div>
            <label className="block text-xs font-medium mb-1">Tiền tố đúng *</label>
            <input
              required
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-mono uppercase"
              placeholder="vd: SG"
              value={form.to_prefix}
              onChange={(e) => setForm((f) => ({ ...f, to_prefix: e.target.value.toUpperCase() }))}
            />
            {sameError ? (
              <p className="mt-1 text-xs text-red-500">Tiền tố đúng phải khác tiền tố sai.</p>
            ) : null}
            {formatError ? (
              <p className="mt-1 text-xs text-red-500">Tiền tố chỉ gồm 1-10 chữ cái (A-Z).</p>
            ) : null}
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Lý do (tùy chọn)</label>
            <input
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
              placeholder="vd: OCR nhầm G/C ở tiền tố"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setIsModalOpen(false)}>
              Hủy
            </Button>
            <Button type="submit" className="flex-1" disabled={sameError || formatError || isSaving}>
              {isSaving ? 'Đang lưu...' : editingId ? 'Cập nhật' : 'Tạo mới'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
