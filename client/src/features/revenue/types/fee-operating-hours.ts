export type WeekdayKey = 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat' | 'sun';

export type DayScheduleMode = 'unlimited' | 'open' | 'closed';

export type DayScheduleOpen = {
  open: string;
  close: string;
};

export type DayScheduleClosed = {
  closed: true;
};

export type DaySchedule = DayScheduleOpen | DayScheduleClosed | null;

export type OperatingHours = Partial<Record<WeekdayKey, DaySchedule>>;

export const WEEKDAY_ROWS: { key: WeekdayKey; label: string }[] = [
  { key: 'mon', label: 'Thứ 2' },
  { key: 'tue', label: 'Thứ 3' },
  { key: 'wed', label: 'Thứ 4' },
  { key: 'thu', label: 'Thứ 5' },
  { key: 'fri', label: 'Thứ 6' },
  { key: 'sat', label: 'Thứ 7' },
  { key: 'sun', label: 'Chủ nhật' },
];

export function getDayScheduleMode(schedule: DaySchedule | undefined): DayScheduleMode {
  if (schedule == null) {
    return 'unlimited';
  }
  if ('closed' in schedule && schedule.closed) {
    return 'closed';
  }
  return 'open';
}

export function emptyOperatingHours(): OperatingHours {
  return {};
}

export function operatingHoursFromApi(raw: OperatingHours | null | undefined): OperatingHours {
  if (!raw || typeof raw !== 'object') {
    return emptyOperatingHours();
  }
  return { ...raw };
}

export function operatingHoursToApi(hours: OperatingHours): OperatingHours | null {
  const out: OperatingHours = {};
  for (const { key } of WEEKDAY_ROWS) {
    const schedule = hours[key];
    if (schedule == null) {
      continue;
    }
    if ('closed' in schedule && schedule.closed) {
      out[key] = { closed: true };
      continue;
    }
    if ('open' in schedule && schedule.open && schedule.close) {
      out[key] = { open: schedule.open, close: schedule.close };
    }
  }
  return Object.keys(out).length > 0 ? out : null;
}

export function hasEnforcedOperatingDay(hours: OperatingHours): boolean {
  return WEEKDAY_ROWS.some(({ key }) => {
    const schedule = hours[key];
    if (!schedule) {
      return false;
    }
    if ('closed' in schedule && schedule.closed) {
      return true;
    }
    return Boolean('open' in schedule && schedule.open && schedule.close);
  });
}

export function summarizeOperatingHours(hours: OperatingHours): string {
  const parts = WEEKDAY_ROWS.filter(({ key }) => {
    const schedule = hours[key];
    return schedule != null;
  }).map(({ key, label }) => {
    const schedule = hours[key];
    if (!schedule) {
      return '';
    }
    if ('closed' in schedule && schedule.closed) {
      return `${label}: đóng`;
    }
    if ('open' in schedule) {
      return `${label} ${schedule.open}–${schedule.close}`;
    }
    return '';
  }).filter(Boolean);
  return parts.length > 0 ? parts.join(' · ') : 'Chưa cấu hình giờ';
}
