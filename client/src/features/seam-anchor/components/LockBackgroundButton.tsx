import React, { useState } from 'react';
import { ImageDown, Loader2 } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { seamAnchorApi } from '../services/seam-anchor-api';
import type {
  SeamAnchorLockRequest,
  SeamAnchorLockResponse,
} from '../types/seam-anchor.types';

type LockBackgroundButtonProps = {
  groupId?: number;
  cameraIds?: number[];
  forceCapture?: boolean;
  disabled?: boolean;
  className?: string;
  size?: 'sm' | 'md';
  label?: string;
  onLocked?: (response: SeamAnchorLockResponse) => void;
  onError?: (error: unknown) => void;
};

function describeResult(response: SeamAnchorLockResponse): string {
  const lockedCount = response.locked.length;
  const failureCount = response.failures.length;
  const sourceMix = new Set(response.locked.map((item) => item.source));
  const sourceLabel = sourceMix.has('live')
    ? sourceMix.has('capture')
      ? 'live + chụp adhoc'
      : 'từ pipeline đang chạy'
    : 'chụp adhoc qua RTSP';
  let summary = `Đã lock ${lockedCount} camera (${sourceLabel})`;
  if (failureCount > 0) {
    summary += ` — bỏ qua ${failureCount} camera`;
  }
  return summary;
}

export const LockBackgroundButton: React.FC<LockBackgroundButtonProps> = ({
  groupId,
  cameraIds,
  forceCapture,
  disabled,
  className,
  size = 'md',
  label = 'Lock Background',
  onLocked,
  onError,
}) => {
  const [isLoading, setIsLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ kind: 'success' | 'error'; text: string } | null>(
    null,
  );

  const handleClick = async () => {
    if (isLoading) {
      return;
    }
    const payload: SeamAnchorLockRequest = {
      group_id: groupId,
      camera_ids: cameraIds,
      force_capture: forceCapture,
    };
    setIsLoading(true);
    setFeedback(null);
    try {
      const response = await seamAnchorApi.lockBackground(payload);
      setFeedback({ kind: 'success', text: describeResult(response) });
      onLocked?.(response);
    } catch (err) {
      const text = err instanceof Error ? err.message : 'Lock Background thất bại';
      setFeedback({ kind: 'error', text });
      onError?.(err);
    } finally {
      setIsLoading(false);
    }
  };

  const sizeClasses =
    size === 'sm'
      ? 'px-3 py-1.5 text-[10px]'
      : 'px-4 py-2 text-xs';

  return (
    <div className={cn('flex flex-col items-stretch gap-1', className)}>
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || isLoading}
        className={cn(
          'inline-flex items-center justify-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 font-bold uppercase tracking-widest text-blue-600 transition-colors hover:bg-blue-500/15 disabled:cursor-not-allowed disabled:opacity-50 dark:text-blue-300',
          sizeClasses,
        )}
      >
        {isLoading ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <ImageDown className="h-3.5 w-3.5" />
        )}
        <span>{label}</span>
      </button>
      {feedback ? (
        <span
          className={cn(
            'text-[10px] font-mono uppercase tracking-widest',
            feedback.kind === 'success' ? 'text-emerald-500' : 'text-red-500',
          )}
        >
          {feedback.text}
        </span>
      ) : null}
    </div>
  );
};
