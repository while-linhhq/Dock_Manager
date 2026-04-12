/**
 * Typography for dense data tables — slightly larger than legacy 10px for readability.
 */
export const dt = {
  /** thead > tr */
  headRow:
    'text-xs sm:text-sm font-bold text-gray-500 dark:text-gray-400 uppercase tracking-wide border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]',
  /** th / td padding */
  pad: 'px-5 sm:px-6 py-3.5 sm:py-4',
  /** Primary body text */
  body: 'text-sm text-gray-900 dark:text-white',
  bodyMuted: 'text-sm text-gray-600 dark:text-gray-300',
  /** IDs, codes */
  mono: 'font-mono text-sm text-gray-800 dark:text-gray-200',
  monoAccent: 'font-mono text-sm font-semibold text-blue-600 dark:text-blue-400',
  /** Secondary / meta column */
  meta: 'text-xs sm:text-sm font-semibold text-gray-600 dark:text-gray-400 uppercase tracking-wide',
  /** Status pill inside table */
  badge: 'text-xs font-bold uppercase tracking-wide',
  /** Row action links */
  action: 'text-xs sm:text-sm font-bold uppercase tracking-wide',
  /** Empty / loading row message */
  empty: 'text-sm text-gray-500 dark:text-gray-400',
} as const;
