import { httpClient } from '../../../services/httpClient';
import type {
  SeamAnchorLockRequest,
  SeamAnchorLockResponse,
  SeamAnchorStateResponse,
} from '../types/seam-anchor.types';

export const seamAnchorApi = {
  lockBackground: (payload: SeamAnchorLockRequest): Promise<SeamAnchorLockResponse> =>
    httpClient.post<SeamAnchorLockResponse>('/pipeline/seam-anchor/lock-background', payload),
  getState: (): Promise<SeamAnchorStateResponse> =>
    httpClient.get<SeamAnchorStateResponse>('/pipeline/seam-anchor/state'),
};
