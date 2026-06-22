import React, { useState } from 'react';
import { Plus, Pencil, Trash2, AlertCircle } from 'lucide-react';
import { useShipIdRulesStore } from '../store/shipIdRulesStore';
import type { PatternCreate, PatternRead, PatternUpdate } from '../types/ship-id-rules.types';
import { Button } from '../../../components/Button/Button';
import { Modal } from '../../../components/Modal/Modal';

function validateRegex(pattern: string): string | null {
  try {
    new RegExp(pattern);
    return null;
  } catch (e: unknown) {
    return e instanceof Error ? e.message : 'Invalid regex';
  }
}

type FormValues = {
  name: string;
  pattern: string;
  priority: string;
  description: string;
  is_active: boolean;
};

const DEFAULT_FORM: FormValues = {
  name: '',
  pattern: '',
  priority: '0',
  description: '',
  is_active: true,
};

export const PatternTable: React.FC = () => {
  const { patterns, createPattern, updatePattern, deletePattern } = useShipIdRulesStore();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<FormValues>(DEFAULT_FORM);
  const [regexError, setRegexError] = useState<string | null>(null);
  const [testInput, setTestInput] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  const testMatches = testInput.trim()
    ? patterns
        .filter((p) => p.is_active)
        .flatMap((p) => {
          try {
            const m = new RegExp(p.pattern, 'i').exec(testInput.toUpperCase().replace(/\s/g, ''));
            return m ? [{ pattern: p.name, match: m[0] }] : [];
          } catch {
            return [];
          }
        })
    : [];

  const openAdd = () => {
    setEditingId(null);
    setForm(DEFAULT_FORM);
    setRegexError(null);
    setIsModalOpen(true);
  };

  const openEdit = (p: PatternRead) => {
    setEditingId(p.id);
    setForm({
      name: p.name,
      pattern: p.pattern,
      priority: String(p.priority),
      description: p.description ?? '',
      is_active: p.is_active,
    });
    setRegexError(null);
    setIsModalOpen(true);
  };

  const handlePatternChange = (v: string) => {
    setForm((f) => ({ ...f, pattern: v }));
    setRegexError(validateRegex(v));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validateRegex(form.pattern);
    if (err) {
      setRegexError(err);
      return;
    }
    const payload = {
      name: form.name.trim(),
      pattern: form.pattern.trim(),
      priority: Number(form.priority) || 0,
      description: form.description.trim() || undefined,
      is_active: form.is_active,
    };
    setIsSaving(true);
    try {
      if (editingId !== null) {
        await updatePattern(editingId, payload as PatternUpdate);
      } else {
        await createPattern(payload as PatternCreate);
      }
      setIsModalOpen(false);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Lưu thất bại';
      alert(message);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm('Xóa pattern này?')) {
      return;
    }
    await deletePattern(id);
  };

  const sorted = [...patterns].sort((a, b) => b.priority - a.priority);

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Patterns được thử theo thứ tự priority giảm dần. OCR result khớp pattern đầu tiên sẽ được dùng.
        </p>
        <Button type="button" onClick={openAdd} className="flex items-center gap-1 text-xs px-3 py-1.5">
          <Plus className="w-3.5 h-3.5" /> Thêm pattern
        </Button>
      </div>

      <div className="space-y-2">
        <div className="text-xs font-medium text-gray-500 flex items-center gap-2">
          <span>Test live:</span>
          <input
            className="flex-1 px-2 py-1 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-xs"
            placeholder="Nhập text OCR để test..."
            value={testInput}
            onChange={(e) => setTestInput(e.target.value)}
          />
        </div>
        {testInput.trim() ? (
          <div className="text-xs px-3 py-2 rounded-lg bg-gray-50 dark:bg-white/5 border border-gray-100 dark:border-white/10">
            {testMatches.length > 0 ? (
              testMatches.map((m, i) => (
                <span key={i} className="mr-3 font-mono text-emerald-600 dark:text-emerald-400">
                  [{m.pattern}] → <strong>{m.match}</strong>
                </span>
              ))
            ) : (
              <span className="text-gray-400">Không có pattern nào khớp</span>
            )}
          </div>
        ) : null}
      </div>

      <div className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 dark:bg-white/5 text-gray-500 uppercase tracking-wider">
            <tr>
              <th className="px-3 py-2 text-left">Priority</th>
              <th className="px-3 py-2 text-left">Tên</th>
              <th className="px-3 py-2 text-left">Pattern</th>
              <th className="px-3 py-2 text-left">Trạng thái</th>
              <th className="px-3 py-2 text-right">Hành động</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-white/5">
            {sorted.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-3 py-4 text-center text-gray-400">
                  Chưa có pattern nào.
                </td>
              </tr>
            ) : null}
            {sorted.map((p) => (
              <tr key={p.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02]">
                <td className="px-3 py-2 font-mono font-bold text-blue-600">{p.priority}</td>
                <td className="px-3 py-2 font-medium">{p.name}</td>
                <td
                  className="px-3 py-2 font-mono text-gray-600 dark:text-gray-300 max-w-[200px] truncate"
                  title={p.pattern}
                >
                  {p.pattern}
                </td>
                <td className="px-3 py-2">
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                      p.is_active
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                        : 'bg-gray-100 text-gray-500 dark:bg-white/5'
                    }`}
                  >
                    {p.is_active ? 'Hoạt động' : 'Tắt'}
                  </span>
                </td>
                <td className="px-3 py-2 text-right flex justify-end gap-2">
                  <button type="button" onClick={() => openEdit(p)} className="text-blue-500 hover:text-blue-400">
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleDelete(p.id)}
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
        title={editingId ? 'Sửa pattern' : 'Thêm pattern mới'}
        className="max-w-lg"
      >
        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          <div>
            <label className="block text-xs font-medium mb-1">Tên pattern *</label>
            <input
              required
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="vd: Standard 4 số"
            />
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Regex pattern *</label>
            <input
              required
              className={`w-full px-3 py-2 rounded-lg border font-mono text-sm ${
                regexError
                  ? 'border-red-400 dark:border-red-500'
                  : 'border-gray-200 dark:border-white/10'
              } bg-white dark:bg-white/5`}
              value={form.pattern}
              onChange={(e) => handlePatternChange(e.target.value)}
              placeholder="([A-Z50]{2})[-\s]?(\d{4})"
            />
            {regexError ? (
              <p className="mt-1 text-xs text-red-500 flex items-center gap-1">
                <AlertCircle className="w-3 h-3" /> {regexError}
              </p>
            ) : null}
          </div>
          <div className="flex gap-3">
            <div className="flex-1">
              <label className="block text-xs font-medium mb-1">Priority (cao hơn = ưu tiên)</label>
              <input
                type="number"
                className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
                value={form.priority}
                onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
              />
            </div>
            <div className="flex items-end pb-2">
              <label className="flex items-center gap-2 text-xs cursor-pointer">
                <input
                  type="checkbox"
                  checked={form.is_active}
                  onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                  className="w-4 h-4"
                />
                Hoạt động
              </label>
            </div>
          </div>
          <div>
            <label className="block text-xs font-medium mb-1">Mô tả (tùy chọn)</label>
            <input
              className="w-full px-3 py-2 rounded-lg border border-gray-200 dark:border-white/10 bg-white dark:bg-white/5 text-sm"
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={() => setIsModalOpen(false)}>
              Hủy
            </Button>
            <Button type="submit" className="flex-1" disabled={!!regexError || isSaving}>
              {isSaving ? 'Đang lưu...' : editingId ? 'Cập nhật' : 'Tạo mới'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
