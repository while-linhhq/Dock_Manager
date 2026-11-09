export type LicenseEnforcementMode = 'off' | 'warn' | 'enforce';

/**
 * Ảnh chụp trạng thái license do backend trả về (`GET /license/status`).
 * Không chứa license key thật — chỉ có `license_key_hint` (4 ký tự cuối).
 */
export interface LicenseStatusRead {
  status: string;
  plan_name: string | null;
  valid_until: string | null;
  days_left: number | null;
  grace_days: number;
  features: Record<string, unknown>;
  enforcement_mode: LicenseEnforcementMode;
  instance_id: string;
  machine_code: string;
  license_key_hint: string | null;
  last_verified_at: string | null;
  last_error: string | null;
}

/** Body của `POST /license/activate`; `label` mặc định rỗng ở backend. */
export interface LicenseActivateRequest {
  license_key: string;
  label?: string;
}
