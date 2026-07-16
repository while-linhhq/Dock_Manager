import React, { useState } from 'react';
import { Plus, Pencil, Trash2, ArrowRight } from 'lucide-react';
import { useShipIdRulesStore } from '../store/shipIdRulesStore';
import type { ConvertMapCreate, ConvertMapRead } from '../types/ship-id-rules.types';
import { Button } from '../../../components/Button/Button';
import { Modal } from '../../../components/Modal/Modal';
import { SortableTh } from '../../../components/SortableTh/SortableTh';
import { useTableSort, type SortAccessors } from '../../../hooks/useTableSort';

type FormValues = { wrong_value: string; correct_value: string; reason: string };
const DEFAULT_FORM: FormValues = { wrong_value: '', correct_value: '', reason: '' };

export const ConvertMapTable: React.FC = () => {
  const { convertMap, createConvertMap, updateConvertMap, deleteConvertMap } = useShipIdRulesStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormValues>(DEFAULT_FORM);
  const [isSaving, setIsSaving] = useState(false);

  const sortAccessors: SortAccessors<ConvertMapRead> = {
    wrong_value: (c) => c.wrong_value,
    correct_value: (c) => c.correct_value,
    reason: (c) => c.reason ?? '',
  };
  const { sorted, sort, toggle } = useTableSort(convertMap, sortAccessors);

  const sameError =
    form.wrong_value.trim() &&
    form.correct_value.trim() &&
    form.wrong_value.trim().toUpperCase() === form.correct_value.trim().toUpperCase();

  const openAdd = () => {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setIsModalOpen(true);
  };

  const openEdit = (c: ConvertMapRead) => {
    setEditingId(c.id);
    setForm({ wrong_value: c.wrong_value, correct_value: c.correct_value, reason: c.reason ?? '' });
    setIsModalOpen(true);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (sameError) {
      return;
    }
    setIsSaving(true);
    try {
      if (editingId !== null) {
        await updateConvertMap(editingId, {
          correct_value: form.correct_value.trim().toUpperCase(),
          reason: form.reason.trim() || undefined,
        });
      } else {
        await createConvertMap({
          wrong_value: form.wrong_value.trim().toUpperCase(),
          correct_value: form.correct_value.trim().toUpperCase(),
          reason: form.reason.trim() || undefined,
        } as ConvertMapCreate);
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
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Khi OCR nhận diện ra giá trị sai, hệ thống sẽ tự thay bằng giá trị đúng.
        </p>
        <Button type="button" onClick={openAdd} className="flex items-center gap-1 text-xs px-3 py-1.5">
          <Plus className="w-3.5 h-3.5" /> Thêm mapping
        </Button>
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 uppercase tracking-wider">
            <tr>
              <SortableTh sortKey="wrong_value" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                OCR nhận diện sai
              </SortableTh>
              <th className="px-3 py-2 text-center"></th>
              <SortableTh sortKey="correct_value" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Kết quả đúng
              </SortableTh>
              <SortableTh sortKey="reason" sort={sort} onSort={toggle} className="px-3 py-2 sm:px-3 sm:py-2">
                Lý do
              </SortableTh>
              <th className="px-3 py-2 text-right">Hành động</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-white/5">
            {convertMap.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-gray-400">
                  Chưa có mapping nào.
                </td>
              </tr>
            ) : null}
            {sorted.map((c) => (
              <tr key={c.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono font-semibold text-amber-600 dark:text-amber-400">
                  {c.wrong_value}
                </td>
                <td className="px-3 py-2 text-center text-gray-400">
                  <ArrowRight className="w-3.5 h-3.5 inline" />
                </td>
                <td className="px-3 py-2 font-mono font-semibold text-emerald-600 dark:text-emerald-400">
                  {c.correct_value}
                </td>
                <td className="px-3 py-2 text-gray-500">{c.reason ?? '—'}</td>
                <td className="px-3 py-2 text-right flex justify-end gap-2">
                  <button type="button" onClick={() => openEdit(c)} className="text-blue-500 hover:text-blue-400">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void deleteConvertMap(c.id)}
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
        title={editingId ? 'Sửa mapping' : 'Thêm mapping mới'}
        className="max-w-md"
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {editingId === null ? (
            <div>
              <label className="block text-xs font-medium mb-1">OCR nhận diện sai *</label>
              <input
                required
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-mono uppercase"
                placeholder="vd: SC-4567"
                value={form.wrong_value}
                onChange={(e) => setForm((f) => ({ ...f, wrong_value: e.target.value.toUpperCase() }))}
              />
            </div>
          ) : null}
          <div>
            <label className="block text-xs font-medium mb-1">Kết quả đúng *</label>
            <input
              required
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm font-mono uppercase"
              placeholder="vd: SG-4567"
              value={form.correct_value}
              onChange={(e) => setForm((f) => ({ ...f, correct_value: e.target.value.toUpperCase() }))}
            />
            {sameError ? (
              <p className="mt-1 text-xs text-red-500">Giá trị đúng phải khác giá trị sai.</p>
            ) : null}
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Lý do (tùy chọn)</label>
            <input
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
              value={form.reason}
              onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value }))}
              placeholder="vd: OCR nhầm G/C do hình dạng tương tự"
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setIsModalOpen(false)}>
              Hủy
            </Button>
            <Button type="submit" className="flex-1" disabled={!!sameError || isSaving}>
              {isSaving ? 'Đang lưu...' : editingId ? 'Cập nhật' : 'Tạo mới'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
