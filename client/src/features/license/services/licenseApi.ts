import { httpClient } from '../../../services/httpClient';
import type { LicenseActivateRequest, LicenseStatusRead } from '../types';

export const licenseApi = {
  getStatus: (): Promise<LicenseStatusRead> =>
    httpClient.get<LicenseStatusRead>('/license/status'),
  activate: (data: LicenseActivateRequest): Promise<LicenseStatusRead> =>
    httpClient.post<LicenseStatusRead>('/license/activate', data),
  refresh: (): Promise<LicenseStatusRead> =>
    httpClient.post<LicenseStatusRead>('/license/refresh'),
};
