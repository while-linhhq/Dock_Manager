import React from 'react';
import { cn } from '../../../utils/cn';
import {
  WEEKDAY_ROWS,
  type DayScheduleMode,
  type OperatingHours,
  getDayScheduleMode,
} from '../types/fee-operating-hours';
import {
  feeControlClass,
  feeLabelClass,
  feeMonoControlClass,
} from './fee-config-form-ui';

export type FeeOperatingHoursEditorProps = {
  value: OperatingHours;
  onChange: (next: OperatingHours) => void;
  disabled?: boolean;
};

const modeOptions: { value: DayScheduleMode; label: string }[] = [
  { value: 'unlimited', label: '24/7' },
  { value: 'open', label: 'Mở cửa' },
  { value: 'closed', label: 'Đóng' },
];

const rowControlClass = cn(feeControlClass, 'h-7 text-xs');
const timeClass = cn(feeMonoControlClass, 'h-7 w-[3.75rem] shrink-0 px-1.5 text-center text-xs');

function normalizeTimeInput(raw: string, fallback: string): string {
  const trimmed = raw.trim();
  const match = /^(\d{1,2}):(\d{2})$/.exec(trimmed);
  if (!match) {
    return fallback;
  }
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59) {
    return fallback;
  }
  return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
}

const ROW_GRID = 'grid min-w-0 grid-cols-[3.5rem_4.75rem_1fr] items-center gap-x-1.5';

export const FeeOperatingHoursEditor: React.FC<FeeOperatingHoursEditorProps> = ({
  value,
  onChange,
  disabled = false,
}) => {
  const setDayMode = (key: (typeof WEEKDAY_ROWS)[number]['key'], mode: DayScheduleMode) => {
    const next = { ...value };
    if (mode === 'unlimited') {
      delete next[key];
    } else if (mode === 'closed') {
      next[key] = { closed: true };
    } else {
      const prev = value[key];
      const open = prev && 'open' in prev ? prev.open : '06:00';
      const close = prev && 'close' in prev ? prev.close : '22:00';
      next[key] = { open, close };
    }
    onChange(next);
  };

  const setDayTime = (
    key: (typeof WEEKDAY_ROWS)[number]['key'],
    field: 'open' | 'close',
    raw: string,
  ) => {
    const schedule = value[key];
    const open = schedule && 'open' in schedule ? schedule.open : '06:00';
    const close = schedule && 'close' in schedule ? schedule.close : '22:00';
    onChange({
      ...value,
      [key]: {
        open: field === 'open' ? raw : open,
        close: field === 'close' ? raw : close,
      },
    });
  };

  const commitDayTime = (
    key: (typeof WEEKDAY_ROWS)[number]['key'],
    field: 'open' | 'close',
    raw: string,
  ) => {
    const schedule = value[key];
    const open = schedule && 'open' in schedule ? schedule.open : '06:00';
    const close = schedule && 'close' in schedule ? schedule.close : '22:00';
    const fallback = field === 'open' ? open : close;
    const normalized = normalizeTimeInput(raw, fallback);
    onChange({
      ...value,
      [key]: {
        open: field === 'open' ? normalized : open,
        close: field === 'close' ? normalized : close,
      },
    });
  };

  return (
    <div className="overflow-hidden rounded-xl border border-gray-200 dark:border-white/10">
      <div
        className={cn(
          ROW_GRID,
          'border-b border-gray-200 bg-gray-100/90 px-2.5 py-1.5 dark:border-white/10 dark:bg-white/5',
          feeLabelClass,
        )}
      >
        <span>Ngày</span>
        <span>Trạng thái</span>
        <span>Khung giờ</span>
      </div>
      <div className="grid grid-cols-1 gap-y-0.5 p-1.5 sm:grid-cols-2 sm:gap-x-3 sm:gap-y-0.5">
        {WEEKDAY_ROWS.map(({ key, label }) => {
          const mode = getDayScheduleMode(value[key]);
          const schedule = value[key];
          const openTime = schedule && 'open' in schedule ? schedule.open : '06:00';
          const closeTime = schedule && 'close' in schedule ? schedule.close : '22:00';

          return (
            <div key={key} className={cn(ROW_GRID, 'rounded-md px-1.5 py-1 hover:bg-gray-50/80 dark:hover:bg-white/[0.03]')}>
              <span className="text-xs font-medium text-gray-700 dark:text-gray-200">{label}</span>
              <select
                value={mode}
                disabled={disabled}
                onChange={(e) => setDayMode(key, e.target.value as DayScheduleMode)}
                className={rowControlClass}
              >
                {modeOptions.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              <div className="flex h-7 min-w-0 items-center gap-0.5">
                {mode === 'open' ? (
                  <>
                    <input
                      type="text"
                      inputMode="numeric"
                      disabled={disabled}
                      value={openTime}
                      placeholder="06:00"
                      maxLength={5}
                      onChange={(e) => setDayTime(key, 'open', e.target.value)}
                      onBlur={(e) => commitDayTime(key, 'open', e.target.value)}
                      className={timeClass}
                      aria-label={`Giờ mở ${label}`}
                    />
                    <span className="shrink-0 text-sm text-gray-400">–</span>
                    <input
                      type="text"
                      inputMode="numeric"
                      disabled={disabled}
                      value={closeTime}
                      placeholder="22:00"
                      maxLength={5}
                      onChange={(e) => setDayTime(key, 'close', e.target.value)}
                      onBlur={(e) => commitDayTime(key, 'close', e.target.value)}
                      className={timeClass}
                      aria-label={`Giờ đóng ${label}`}
                    />
                  </>
                ) : (
                  <span className="truncate text-xs text-gray-400">
                    {mode === 'closed' ? 'Đóng' : '—'}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
