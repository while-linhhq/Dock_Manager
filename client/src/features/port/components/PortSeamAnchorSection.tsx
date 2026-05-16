import React, { useMemo, useState } from 'react';
import { Anchor, Loader2, RotateCcw, Save, AlertTriangle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { PortConfigRead } from '../services/portApi';

type FieldKind = 'bool' | 'int' | 'float';

type FieldDef = {
  key: string;
  label: string;
  description: string;
  kind: FieldKind;
  default: string;
  min?: number;
  max?: number;
  step?: number;
  group: 'lifecycle' | 'bgs' | 'revalidation';
};

const FIELDS: FieldDef[] = [
  // Anchor lifecycle
  {
    key: 'seam_anchor_enabled',
    label: 'Bật seam anchor',
    description: 'Tổng công tắc. Tắt để fallback về ReID thông thường.',
    kind: 'bool',
    default: 'true',
    group: 'lifecycle',
  },
  {
    key: 'seam_roi_width_ratio',
    label: 'Tỉ lệ vùng seam (ROI)',
    description: 'Bề rộng dải seam (so với width camera kề). Lớn hơn → bắt được tàu chia rộng hơn nhưng nhiễu hơn.',
    kind: 'float',
    default: '0.15',
    min: 0.05,
    max: 0.5,
    step: 0.01,
    group: 'lifecycle',
  },
  {
    key: 'seam_proximity_px',
    label: 'Khoảng cách kích hoạt (px)',
    description: 'Bbox cách cạnh ≤ giá trị này thì mới đủ điều kiện anchor khi YOLO mất track.',
    kind: 'int',
    default: '40',
    min: 0,
    max: 500,
    step: 1,
    group: 'lifecycle',
  },
  {
    key: 'anchor_iou_resurrect_threshold',
    label: 'IoU resurrect',
    description: 'IoU tối thiểu giữa detection mới và bbox anchor để dùng lại ID cũ thay vì cấp ID mới.',
    kind: 'float',
    default: '0.3',
    min: 0.05,
    max: 0.95,
    step: 0.05,
    group: 'lifecycle',
  },
  {
    key: 'anchor_departed_grace_sec',
    label: 'Grace period rời bến (s)',
    description: 'Thời gian seam phải trống liên tục trước khi chốt DEPARTED và xuất hoá đơn.',
    kind: 'float',
    default: '30.0',
    min: 1,
    max: 600,
    step: 1,
    group: 'lifecycle',
  },
  {
    key: 'anchor_min_stationary_sec',
    label: 'Thời gian neo tĩnh tối thiểu (s)',
    description: 'Tàu phải ở trạng thái STATIC ít nhất bấy nhiêu giây trước khi được anchor khi YOLO mất track.',
    kind: 'float',
    default: '8.0',
    min: 0,
    max: 300,
    step: 0.5,
    group: 'lifecycle',
  },

  // Background subtraction
  {
    key: 'bg_subtract_threshold',
    label: 'Ngưỡng foreground',
    description: 'Tỉ lệ pixel foreground tối thiểu để coi seam là OCCUPIED. Cao hơn → ít false-positive, nhưng dễ miss.',
    kind: 'float',
    default: '0.18',
    min: 0.01,
    max: 0.9,
    step: 0.01,
    group: 'bgs',
  },
  {
    key: 'bg_model_history',
    label: 'MOG2 history',
    description: 'Số frame quá khứ giữ trong background model. Lớn hơn → ổn định nhưng adapt chậm.',
    kind: 'int',
    default: '500',
    min: 50,
    max: 5000,
    step: 50,
    group: 'bgs',
  },
  {
    key: 'bg_var_threshold',
    label: 'MOG2 varThreshold',
    description: 'Ngưỡng phương sai để xếp pixel vào background. Thấp hơn → nhạy hơn.',
    kind: 'float',
    default: '25',
    min: 1,
    max: 200,
    step: 1,
    group: 'bgs',
  },
  {
    key: 'bg_min_seed_frames',
    label: 'Số frame seed tối thiểu',
    description: 'Số frame phải học trước khi background model được coi là sẵn sàng.',
    kind: 'int',
    default: '100',
    min: 10,
    max: 1000,
    step: 10,
    group: 'bgs',
  },

  // Re-validation & retention
  {
    key: 'anchor_embedding_match_enabled',
    label: 'Embedding match',
    description: 'Bật so khớp embedding khi re-validate & resurrect anchor.',
    kind: 'bool',
    default: 'true',
    group: 'revalidation',
  },
  {
    key: 'anchor_embedding_sim_threshold',
    label: 'Ngưỡng cosine similarity',
    description: 'Cosine similarity tối thiểu của embedding để xác nhận cùng tàu.',
    kind: 'float',
    default: '0.65',
    min: 0.3,
    max: 0.99,
    step: 0.01,
    group: 'revalidation',
  },
  {
    key: 'anchor_revalidation_sec',
    label: 'Chu kỳ re-validate (s)',
    description: 'Bao lâu kiểm tra lại appearance (color/embedding) cho anchor đang giữ.',
    kind: 'float',
    default: '5.0',
    min: 0.5,
    max: 60,
    step: 0.5,
    group: 'revalidation',
  },
  {
    key: 'anchor_color_hsv_tolerance_h',
    label: 'Dung sai màu Hue (độ)',
    description: 'Ngưỡng lệch Hue khi so sánh màu chủ đạo tàu lúc re-validate (chống false positive).',
    kind: 'int',
    default: '15',
    min: 1,
    max: 90,
    step: 1,
    group: 'revalidation',
  },
  {
    key: 'anchor_max_duration_sec',
    label: 'Thời gian giữ tối đa (s)',
    description: 'Trần thời gian giữ anchor để tránh kẹt vô hạn (mặc định 48h = 172800s).',
    kind: 'int',
    default: '172800',
    min: 60,
    max: 1_000_000,
    step: 60,
    group: 'revalidation',
  },
  {
    key: 'anchor_db_update_debounce_sec',
    label: 'Debounce ghi DB (s)',
    description: 'Tần suất cập nhật last_seen vào bảng anchored_identities (ghi ít hơn ⇒ giảm IO).',
    kind: 'float',
    default: '30.0',
    min: 1,
    max: 600,
    step: 1,
    group: 'revalidation',
  },
];

const GROUPS: { id: FieldDef['group']; label: string; description: string }[] = [
  {
    id: 'lifecycle',
    label: 'Vòng đời Anchor',
    description: 'Kích hoạt, vùng seam, ngưỡng IoU resurrect và grace period.',
  },
  {
    id: 'bgs',
    label: 'Background Subtraction (MOG2)',
    description: 'Tham số bộ trừ nền dùng để xác nhận vùng seam đang bị chiếm.',
  },
  {
    id: 'revalidation',
    label: 'Re-validation & Retention',
    description: 'Embedding match, chu kỳ kiểm tra và thời gian giữ tối đa.',
  },
];

export type PortSeamAnchorSectionProps = {
  configs: PortConfigRead[];
  isLoading: boolean;
  onUpdateConfig: (key: string, value: string, description?: string) => Promise<void>;
  onCreateConfig: (key: string, value: string, description?: string) => Promise<void>;
  onRefresh: () => Promise<void>;
};

type Draft = Record<string, string>;
type Overrides = Partial<Record<string, string>>;

function buildCurrentValues(configs: PortConfigRead[]): Draft {
  const map: Draft = {};
  for (const field of FIELDS) {
    const existing = configs.find((cfg) => cfg.key === field.key);
    map[field.key] = existing ? existing.value : field.default;
  }
  return map;
}

function normalizeValue(field: FieldDef, raw: string): string {
  if (field.kind === 'bool') {
    return raw === 'true' ? 'true' : 'false';
  }
  if (field.kind === 'int') {
    const n = Number(raw);
    if (!Number.isFinite(n)) return field.default;
    return String(Math.trunc(n));
  }
  const n = Number(raw);
  if (!Number.isFinite(n)) return field.default;
  return String(n);
}

function isOutOfRange(field: FieldDef, raw: string): boolean {
  if (field.kind === 'bool') return false;
  const n = Number(raw);
  if (!Number.isFinite(n)) return true;
  if (field.min != null && n < field.min) return true;
  if (field.max != null && n > field.max) return true;
  return false;
}

export const PortSeamAnchorSection: React.FC<PortSeamAnchorSectionProps> = ({
  configs,
  isLoading,
  onUpdateConfig,
  onCreateConfig,
  onRefresh,
}) => {
  const [overrides, setOverrides] = useState<Overrides>({});
  const [saving, setSaving] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const currentValues = useMemo<Draft>(() => buildCurrentValues(configs), [configs]);

  const draft = useMemo<Draft>(() => {
    const merged: Draft = { ...currentValues };
    for (const key of Object.keys(overrides)) {
      const val = overrides[key];
      if (val != null) merged[key] = val;
    }
    return merged;
  }, [currentValues, overrides]);

  const dirtyKeys = useMemo(() => {
    return FIELDS.filter((field) => {
      const overriden = overrides[field.key];
      if (overriden == null) return false;
      return normalizeValue(field, overriden) !== currentValues[field.key];
    }).map((f) => f.key);
  }, [overrides, currentValues]);

  const hasInvalid = useMemo(
    () => FIELDS.some((field) => isOutOfRange(field, draft[field.key])),
    [draft],
  );

  const handleChange = (field: FieldDef, value: string) => {
    setOverrides((prev) => ({ ...prev, [field.key]: value }));
  };

  const handleToggle = (field: FieldDef, checked: boolean) => {
    setOverrides((prev) => ({ ...prev, [field.key]: checked ? 'true' : 'false' }));
  };

  const handleReset = () => {
    setOverrides({});
    setError(null);
  };

  const handleResetDefaults = () => {
    const next: Overrides = {};
    for (const field of FIELDS) {
      if (currentValues[field.key] !== field.default) {
        next[field.key] = field.default;
      }
    }
    setOverrides(next);
    setError(null);
  };

  const handleSave = async () => {
    if (hasInvalid) {
      setError('Có giá trị vượt khoảng cho phép. Vui lòng kiểm tra lại.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      for (const key of dirtyKeys) {
        const field = FIELDS.find((f) => f.key === key);
        if (!field) continue;
        const value = normalizeValue(field, draft[key]);
        const existing = configs.find((cfg) => cfg.key === key);
        if (existing) {
          await onUpdateConfig(key, value, field.description);
        } else {
          await onCreateConfig(key, value, field.description);
        }
      }
      await onRefresh();
      setOverrides({});
      setLastSavedAt(new Date());
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      setError(message || 'Lưu cấu hình thất bại.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-white/5 dark:bg-[#121214]">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-blue-600/10 p-2.5">
              <Anchor className="h-5 w-5 text-blue-600" />
            </div>
            <div>
              <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
                Seam Anchor — Tham số neo tàu
              </h3>
              <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                Áp dụng cho group hybrid (≥ 2 camera). Thay đổi có hiệu lực ở lần khởi động pipeline kế tiếp.
              </p>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              onClick={handleResetDefaults}
              disabled={saving}
              className="bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10"
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Mặc định
            </Button>
            <Button
              type="button"
              onClick={handleReset}
              disabled={saving || dirtyKeys.length === 0}
              className="bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10"
            >
              Huỷ thay đổi
            </Button>
            <Button
              type="button"
              onClick={handleSave}
              disabled={saving || dirtyKeys.length === 0 || hasInvalid}
              className="bg-blue-600 text-white hover:bg-blue-700"
            >
              {saving ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Save className="mr-2 h-4 w-4" />
              )}
              Lưu ({dirtyKeys.length})
            </Button>
          </div>
        </div>

        {error ? (
          <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
            <span>{error}</span>
          </div>
        ) : lastSavedAt ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-600 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
            Đã lưu lúc {lastSavedAt.toLocaleTimeString()}.
          </div>
        ) : null}
      </div>

      {GROUPS.map((group) => (
        <div
          key={group.id}
          className="rounded-2xl border border-gray-200 bg-white shadow-2xl dark:border-white/5 dark:bg-[#121214]"
        >
          <div className="border-b border-gray-200 px-6 py-4 dark:border-white/5">
            <h4 className="text-xs font-bold uppercase tracking-widest text-gray-900 dark:text-white">
              {group.label}
            </h4>
            <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">{group.description}</p>
          </div>
          <div className="divide-y divide-gray-100 dark:divide-white/5">
            {FIELDS.filter((f) => f.group === group.id).map((field) => {
              const value = draft[field.key] ?? field.default;
              const dirty = dirtyKeys.includes(field.key);
              const invalid = isOutOfRange(field, value);
              return (
                <div
                  key={field.key}
                  className="flex flex-col gap-3 px-6 py-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <p className="text-[11px] font-bold uppercase tracking-widest text-gray-900 dark:text-white">
                        {field.label}
                      </p>
                      {dirty ? (
                        <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest text-amber-500">
                          chưa lưu
                        </span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-[10px] text-gray-500 dark:text-gray-400">{field.description}</p>
                    <p className="mt-1 font-mono text-[9px] uppercase tracking-widest text-gray-400">
                      {field.key}
                    </p>
                  </div>
                  <div className="flex items-center gap-3 md:w-72 md:justify-end">
                    {field.kind === 'bool' ? (
                      <label className="inline-flex cursor-pointer items-center gap-2">
                        <input
                          type="checkbox"
                          checked={value === 'true'}
                          onChange={(e) => handleToggle(field, e.target.checked)}
                          disabled={isLoading || saving}
                          className="peer sr-only"
                        />
                        <span
                          className={cn(
                            'relative h-6 w-11 rounded-full transition-colors',
                            value === 'true'
                              ? 'bg-blue-600'
                              : 'bg-gray-300 dark:bg-white/10',
                          )}
                        >
                          <span
                            className={cn(
                              'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform',
                              value === 'true' ? 'translate-x-5' : 'translate-x-0',
                            )}
                          />
                        </span>
                        <span className="font-mono text-[11px] text-gray-600 dark:text-gray-300">
                          {value === 'true' ? 'ON' : 'OFF'}
                        </span>
                      </label>
                    ) : (
                      <div className="flex items-center gap-2">
                        <input
                          type="number"
                          value={value}
                          min={field.min}
                          max={field.max}
                          step={field.step ?? (field.kind === 'int' ? 1 : 0.01)}
                          onChange={(e) => handleChange(field, e.target.value)}
                          disabled={isLoading || saving}
                          className={cn(
                            'w-40 rounded-xl border bg-white px-3 py-2 font-mono text-xs text-gray-900 transition-colors dark:bg-[#1a1a1d] dark:text-white',
                            invalid
                              ? 'border-red-400 focus:border-red-500 focus:ring-1 focus:ring-red-500/50'
                              : 'border-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50 dark:border-white/10',
                          )}
                        />
                        {field.min != null || field.max != null ? (
                          <span className="text-[9px] font-mono uppercase tracking-widest text-gray-400">
                            {field.min ?? '−∞'}–{field.max ?? '+∞'}
                          </span>
                        ) : null}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};
