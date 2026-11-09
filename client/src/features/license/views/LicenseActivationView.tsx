import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, Copy, Loader2, Lock, ShieldAlert } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { isAdminUser } from '../../../utils/rbac';
import { useAuthStore } from '../../auth/store/authStore';
import { useLicenseStore } from '../store/licenseStore';

/**
 * Màn hình kích hoạt license duy nhất của app — hiện thay cho nội dung route
 * khi trạng thái license là `unlicensed` hoặc `invalid` (key đã lưu nhưng chưa
 * xác thực được, cho phép thử lại). Chỉ admin mới thấy form nhập key.
 */
export const LicenseActivationView: React.FC = () => {
  const status = useLicenseStore((state) => state.status);
  const isLoading = useLicenseStore((state) => state.isLoading);
  const error = useLicenseStore((state) => state.error);
  const activate = useLicenseStore((state) => state.activate);
  const user = useAuthStore((state) => state.user);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const authBootstrapped = useAuthStore((state) => state.authBootstrapped);

  const [licenseKey, setLicenseKey] = useState('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const isAdmin = isAdminUser(user);
  const machineCode = status?.machine_code ?? '';
  const errorMessage = validationError ?? error;

  useEffect(() => {
    if (!copied) {
      return;
    }
    const timer = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timer);
  }, [copied]);

  // Hard reload: đã có token nhưng `/auth/me` chưa xong (backend chậm/khởi động lại) nên chưa
  // biết quyền. Chờ phiên resolve thay vì đoán non-admin và hiện thông báo "liên hệ quản trị viên".
  const isSessionResolving = isAuthenticated && (!authBootstrapped || user == null);

  if (isSessionResolving) {
    return (
      <div className="flex min-h-[calc(100dvh-10rem)] w-full items-center justify-center py-4 sm:py-8">
        <div className="flex flex-col items-center justify-center gap-3 text-gray-500 dark:text-gray-400">
          <Loader2 className="h-8 w-8 animate-spin text-blue-500" aria-hidden />
          <p className="text-xs font-mono uppercase tracking-widest">Đang tải phiên đăng nhập…</p>
        </div>
      </div>
    );
  }

  const handleCopy = async () => {
    if (!machineCode) {
      return;
    }
    try {
      await navigator.clipboard.writeText(machineCode);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmedKey = licenseKey.trim();
    if (!trimmedKey) {
      setValidationError('Vui lòng nhập license key do DTG cấp.');
      return;
    }
    setValidationError(null);
    try {
      await activate(trimmedKey);
    } catch {
      // Store đã ghi `error`; thông báo hiển thị ngay dưới ô nhập.
    }
  };

  return (
    <div className="flex min-h-[calc(100dvh-10rem)] w-full items-center justify-center py-4 sm:py-8">
      <div className="w-full max-w-[560px] rounded-2xl border border-gray-200 bg-white p-6 shadow-xl transition-colors duration-300 dark:border-white/10 dark:bg-[#121214] sm:p-8">
        <div className="mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400">
          <Lock className="h-6 w-6" aria-hidden />
        </div>

        <h1 className="text-xl font-bold tracking-tight text-gray-900 dark:text-white sm:text-2xl">
          Kích hoạt DSight
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-gray-500 dark:text-gray-400">
          License chưa được kích hoạt hoặc chưa xác thực được. Nhập license key do DTG cấp để bắt
          đầu sử dụng.
        </p>

        <div className="mt-6">
          <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
            Mã máy
          </p>
          <div className="flex items-center justify-between gap-3 rounded-xl bg-[#0f172a] px-4 py-3">
            <code className="min-w-0 break-all font-mono text-sm font-bold tracking-[0.12em] text-sky-300 sm:text-base">
              {machineCode || '—'}
            </code>
            <button
              type="button"
              onClick={() => void handleCopy()}
              disabled={!machineCode}
              className={cn(
                'inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[10px] font-bold uppercase tracking-wider transition-colors disabled:cursor-not-allowed disabled:opacity-40',
                copied
                  ? 'bg-emerald-500/15 text-emerald-300'
                  : 'bg-white/10 text-gray-200 hover:bg-white/20',
              )}
              title="Sao chép mã máy"
            >
              {copied ? <Check className="h-3.5 w-3.5" aria-hidden /> : <Copy className="h-3.5 w-3.5" aria-hidden />}
              {copied ? 'Đã copy' : 'Copy'}
            </button>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-gray-400 dark:text-gray-500">
            Gửi mã máy cho DTG nếu cần hỗ trợ. Mã gắn với phần cứng của máy chủ và không đổi khi cài lại
            trên cùng máy.
          </p>
        </div>

        {isAdmin ? (
          <form className="mt-6" onSubmit={handleSubmit} noValidate>
            <label
              htmlFor="license-key"
              className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400"
            >
              License key
            </label>
            <input
              id="license-key"
              type="text"
              value={licenseKey}
              onChange={(event) => {
                setLicenseKey(event.target.value);
                setValidationError(null);
              }}
              placeholder="DSIGHT-XXXX-XXXX-XXXX-XXXX"
              autoComplete="off"
              spellCheck={false}
              disabled={isLoading}
              aria-invalid={errorMessage != null}
              aria-describedby={errorMessage != null ? 'license-key-error' : undefined}
              className={cn(
                'w-full rounded-xl border bg-gray-50 px-4 py-3 font-mono text-sm tracking-wider text-gray-900 outline-none transition-colors placeholder:text-gray-400 focus:ring-2 disabled:opacity-60 dark:bg-white/5 dark:text-white dark:placeholder:text-gray-500',
                errorMessage != null
                  ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20 dark:border-red-500'
                  : 'border-gray-300 focus:border-blue-500 focus:ring-blue-500/20 dark:border-white/10 dark:focus:border-blue-500',
              )}
            />

            {errorMessage != null && (
              <div
                id="license-key-error"
                role="alert"
                className="mt-3 flex items-start gap-2 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium leading-relaxed text-red-700 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300"
              >
                <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
                <span>{errorMessage}</span>
              </div>
            )}

            <Button
              type="submit"
              size="lg"
              disabled={isLoading}
              className="mt-4 w-full rounded-xl font-bold uppercase tracking-widest"
            >
              {isLoading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden />
                  Đang kích hoạt…
                </>
              ) : (
                'Kích hoạt'
              )}
            </Button>
          </form>
        ) : (
          <div
            role="status"
            className="mt-6 flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-relaxed text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200"
          >
            <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
            <span>Chưa kích hoạt license — liên hệ quản trị viên</span>
          </div>
        )}

        <p className="mt-6 border-t border-gray-100 pt-4 text-[11px] leading-relaxed text-gray-400 dark:border-white/5 dark:text-gray-500">
          Sau khi kích hoạt, app tự kiểm tra license server mỗi 6 giờ. Khi mất mạng tạm thời, app vẫn
          chạy bằng token license đã lưu trong thời hạn của token.
        </p>
      </div>
    </div>
  );
};
