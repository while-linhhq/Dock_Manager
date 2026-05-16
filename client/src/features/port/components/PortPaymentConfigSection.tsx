import React, { useEffect, useMemo, useState } from 'react';
import { portApi } from '../services/portApi';
import { AlertTriangle, CreditCard, Loader2, RotateCcw, Save } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import type { PortConfigRead } from '../services/portApi';

export const SEPAY_PORT_CONFIG_KEYS = [
  'sepay_webhook_secret',
  'sepay_public_api_base_url',
  'sepay_bank_account',
  'sepay_bank_name',
  'sepay_account_name',
] as const;

type FieldDef = {
  key: (typeof SEPAY_PORT_CONFIG_KEYS)[number];
  label: string;
  description: string;
  default: string;
  inputType: 'text' | 'password';
  group: 'bank' | 'webhook';
  placeholder?: string;
};

const FIELDS: FieldDef[] = [
  {
    key: 'sepay_bank_account',
    label: 'Số tài khoản',
    description: 'Số TK nhận tiền — dùng tạo mã QR tại qr.sepay.vn.',
    default: '',
    inputType: 'text',
    group: 'bank',
    placeholder: 'VD: 0010000000355',
  },
  {
    key: 'sepay_bank_name',
    label: 'Ngân hàng',
    description: 'Tên ngân hàng đúng theo danh sách SEPay (VD: Vietcombank, BIDV, TPBank).',
    default: '',
    inputType: 'text',
    group: 'bank',
    placeholder: 'VD: Vietcombank',
  },
  {
    key: 'sepay_account_name',
    label: 'Chủ tài khoản',
    description: 'Tên hiển thị khi khách chuyển khoản thủ công.',
    default: '',
    inputType: 'text',
    group: 'bank',
    placeholder: 'CÔNG TY ...',
  },
  {
    key: 'sepay_public_api_base_url',
    label: 'URL API công khai (backend)',
    description:
      'Gốc URL server FastAPI mà SEPay gọi webhook (VD: https://api.example.com hoặc https://xxx.ngrok.io). Để trống = backend tự lấy từ request.',
    default: '',
    inputType: 'text',
    group: 'webhook',
    placeholder: 'VD: http://127.0.0.1:8000',
  },
  {
    key: 'sepay_webhook_secret',
    label: 'Webhook secret (HMAC-SHA256)',
    description:
      'Secret khi tạo webhook trên my.sepay.vn. Phương thức xác thực: HMAC-SHA256.',
    default: '',
    inputType: 'password',
    group: 'webhook',
    placeholder: 'Dán secret từ SEPay',
  },
];

const GROUPS = [
  {
    id: 'bank' as const,
    label: 'Tài khoản nhận tiền',
    description: 'Thông tin hiển thị trên modal thanh toán và mã QR.',
  },
  {
    id: 'webhook' as const,
    label: 'Webhook SEPay',
    description: 'Xác thực giao dịch tự động — đổi trạng thái hóa đơn sang Đã thanh toán.',
  },
];

export type PortPaymentConfigSectionProps = {
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

function StatusPill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cn(
        'rounded-full px-2 py-0.5 text-[9px] font-bold uppercase tracking-widest',
        ok
          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
          : 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
      )}
    >
      {ok ? '✓' : '!'} {label}
    </span>
  );
}

function StatusPills({ bankReady, webhookReady }: { bankReady: boolean; webhookReady: boolean }) {
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      <StatusPill ok={bankReady} label="TK ngân hàng" />
      <StatusPill ok={webhookReady} label="Webhook secret" />
    </div>
  );
}

export const PortPaymentConfigSection: React.FC<PortPaymentConfigSectionProps> = ({
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
  const [webhookUrl, setWebhookUrl] = useState('');
  const [webhookUrlLoading, setWebhookUrlLoading] = useState(false);

  const refreshWebhookUrl = async () => {
    setWebhookUrlLoading(true);
    try {
      const data = await portApi.getSepayWebhookUrl();
      setWebhookUrl(data.webhook_url);
    } catch {
      setWebhookUrl('');
    } finally {
      setWebhookUrlLoading(false);
    }
  };

  useEffect(() => {
    void refreshWebhookUrl();
  }, [configs]);

  const currentValues = useMemo<Draft>(() => buildCurrentValues(configs), [configs]);

  const draft = useMemo<Draft>(() => {
    const merged: Draft = { ...currentValues };
    for (const key of Object.keys(overrides)) {
      const val = overrides[key];
      if (val != null) {
        merged[key] = val;
      }
    }
    return merged;
  }, [currentValues, overrides]);

  const dirtyKeys = useMemo(() => {
    return FIELDS.filter((field) => {
      const overriden = overrides[field.key];
      if (overriden == null) {
        return false;
      }
      return overriden !== currentValues[field.key];
    }).map((f) => f.key);
  }, [overrides, currentValues]);

  const bankReady =
    Boolean(draft.sepay_bank_account?.trim()) && Boolean(draft.sepay_bank_name?.trim());
  const webhookReady = Boolean(draft.sepay_webhook_secret?.trim());

  const handleChange = (key: string, value: string) => {
    setOverrides((prev) => ({ ...prev, [key]: value }));
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
    setSaving(true);
    setError(null);
    try {
      for (const key of dirtyKeys) {
        const field = FIELDS.find((f) => f.key === key);
        if (!field) {
          continue;
        }
        const value = draft[key] ?? '';
        const existing = configs.find((cfg) => cfg.key === key);
        if (existing) {
          await onUpdateConfig(key, value, field.description);
        } else {
          await onCreateConfig(key, value, field.description);
        }
      }
      await onRefresh();
      await refreshWebhookUrl();
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
      <PaymentHeaderCard
        bankReady={bankReady}
        webhookReady={webhookReady}
        saving={saving}
        dirtyCount={dirtyKeys.length}
        error={error}
        lastSavedAt={lastSavedAt}
        webhookUrl={webhookUrl}
        webhookUrlLoading={webhookUrlLoading}
        onResetDefaults={handleResetDefaults}
        onReset={handleReset}
        onSave={handleSave}
      />

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
              return (
                <div
                  key={field.key}
                  className="flex flex-col gap-3 px-6 py-4 md:flex-row md:items-center md:justify-between"
                >
                  <div className="flex-1">
                    <FieldMeta field={field} dirty={dirty} />
                  </div>
                  <input
                    type={field.inputType}
                    value={value}
                    placeholder={field.placeholder}
                    onChange={(e) => handleChange(field.key, e.target.value)}
                    disabled={isLoading || saving}
                    autoComplete={field.inputType === 'password' ? 'new-password' : 'off'}
                    className={cn(
                      'w-full rounded-xl border bg-white px-3 py-2 font-mono text-xs text-gray-900 transition-colors md:max-w-md',
                      'border-gray-200 focus:border-blue-500 focus:ring-1 focus:ring-blue-500/50',
                      'dark:border-white/10 dark:bg-[#1a1a1d] dark:text-white',
                    )}
                  />
                </div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
};

function PaymentHeaderCard({
  bankReady,
  webhookReady,
  saving,
  dirtyCount,
  error,
  lastSavedAt,
  webhookUrl,
  webhookUrlLoading,
  onResetDefaults,
  onReset,
  onSave,
}: {
  bankReady: boolean;
  webhookReady: boolean;
  saving: boolean;
  dirtyCount: number;
  error: string | null;
  lastSavedAt: Date | null;
  webhookUrl: string;
  webhookUrlLoading: boolean;
  onResetDefaults: () => void;
  onReset: () => void;
  onSave: () => void;
}) {
  return (
    <div className="rounded-2xl border border-gray-200 bg-white p-6 shadow-2xl dark:border-white/5 dark:bg-[#121214]">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-emerald-600/10 p-2.5">
            <CreditCard className="h-5 w-5 text-emerald-600" />
          </div>
          <div>
            <h3 className="text-sm font-bold uppercase tracking-widest text-gray-900 dark:text-white">
              Cấu hình thanh toán SEPay
            </h3>
            <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
              QR chuyển khoản và webhook tự động xác nhận hóa đơn trong Quản lý thu nhập.
            </p>
            <StatusPills bankReady={bankReady} webhookReady={webhookReady} />
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            onClick={onResetDefaults}
            disabled={saving}
            className="bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10"
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Mặc định
          </Button>
          <Button
            type="button"
            onClick={onReset}
            disabled={saving || dirtyCount === 0}
            className="bg-gray-100 text-gray-700 hover:bg-gray-200 dark:bg-white/5 dark:text-gray-200 dark:hover:bg-white/10"
          >
            Huỷ thay đổi
          </Button>
          <Button
            type="button"
            onClick={onSave}
            disabled={saving || dirtyCount === 0}
            className="bg-emerald-600 text-white hover:bg-emerald-700"
          >
            {saving ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Save className="mr-2 h-4 w-4" />
            )}
            Lưu ({dirtyCount})
          </Button>
        </div>
      </div>

      {error ? (
        <div className="mt-4 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-[11px] text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300">
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span>{error}</span>
        </div>
      ) : lastSavedAt ? (
        <SavedAtBanner lastSavedAt={lastSavedAt} />
      ) : null}

      <div className="mt-4 rounded-xl border border-gray-100 bg-gray-50 px-4 py-3 dark:border-white/5 dark:bg-white/[0.02]">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-500">
          URL webhook (dán vào my.sepay.vn)
        </p>
        <p className="mt-1 break-all font-mono text-xs text-blue-600 dark:text-blue-400">
          {webhookUrlLoading
            ? 'Đang lấy URL từ server…'
            : webhookUrl ||
              'Chưa xác định — lưu «URL API công khai» hoặc cấu hình SEPAY_PUBLIC_API_BASE_URL'}
        </p>
        <p className="mt-2 text-[10px] text-gray-500 dark:text-gray-400">
          Cấu trúc mã thanh toán trên SEPay phải trích xuất được{' '}
          <span className="font-mono">invoice_number</span> (nội dung CK = số hóa đơn).
        </p>
      </div>
    </div>
  );
}

function SavedAtBanner({ lastSavedAt }: { lastSavedAt: Date }) {
  return (
    <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] text-emerald-600 dark:border-emerald-500/30 dark:bg-emerald-500/10 dark:text-emerald-300">
      Đã lưu lúc {lastSavedAt.toLocaleTimeString()}.
    </div>
  );
}

function FieldMeta({ field, dirty }: { field: FieldDef; dirty: boolean }) {
  return (
    <>
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
      <p className="mt-1 font-mono text-[9px] uppercase tracking-widest text-gray-400">{field.key}</p>
    </>
  );
}
