import React from 'react';
import { Ship, CalendarClock, HelpCircle, Tag, ScanLine } from 'lucide-react';
import { cn } from '../../../utils/cn';

export type VesselsMainTab = 'spot' | 'monthly' | 'unclassified' | 'types' | 'recognition';

export type VesselsMainTabsProps = {
  activeTab: VesselsMainTab;
  onTabChange: (tab: VesselsMainTab) => void;
  activePatternCount?: number;
  /** Số tàu mỗi phân loại — hiển thị badge trên tab. */
  spotCount?: number;
  monthlyCount?: number;
  unclassifiedCount?: number;
};

const baseBtn =
  'px-5 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2 whitespace-nowrap';
const activeCls = 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm';
const idleCls = 'text-gray-500 hover:text-gray-900 dark:hover:text-white';

function Badge({ value, tone }: { value?: number; tone: 'blue' | 'amber' | 'gray' }) {
  if (value === undefined) return null;
  const toneCls =
    tone === 'blue'
      ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300'
      : tone === 'amber'
        ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300'
        : 'bg-gray-200 text-gray-600 dark:bg-white/10 dark:text-gray-300';
  return (
    <span
      className={cn(
        'ml-1 px-1.5 py-0.5 rounded-full text-[10px] font-bold leading-none',
        toneCls,
      )}
    >
      {value}
    </span>
  );
}

export const VesselsMainTabs: React.FC<VesselsMainTabsProps> = ({
  activeTab,
  onTabChange,
  activePatternCount,
  spotCount,
  monthlyCount,
  unclassifiedCount,
}) => {
  return (
    <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit max-w-full overflow-x-auto">
      <button
        type="button"
        onClick={() => onTabChange('spot')}
        className={cn(baseBtn, activeTab === 'spot' ? activeCls : idleCls)}
      >
        <Ship className="w-4 h-4" />
        <span>Tàu Lẻ</span>
        <Badge value={spotCount} tone="blue" />
      </button>
      <button
        type="button"
        onClick={() => onTabChange('monthly')}
        className={cn(baseBtn, activeTab === 'monthly' ? activeCls : idleCls)}
      >
        <CalendarClock className="w-4 h-4" />
        <span>Tàu Tháng</span>
        <Badge value={monthlyCount} tone="blue" />
      </button>
      <button
        type="button"
        onClick={() => onTabChange('unclassified')}
        className={cn(baseBtn, activeTab === 'unclassified' ? activeCls : idleCls)}
      >
        <HelpCircle className="w-4 h-4" />
        <span>Chưa Phân Loại</span>
        <Badge value={unclassifiedCount} tone="amber" />
      </button>
      <button
        type="button"
        onClick={() => onTabChange('types')}
        className={cn(baseBtn, activeTab === 'types' ? activeCls : idleCls)}
      >
        <Tag className="w-4 h-4" />
        <span>Loại Tàu</span>
      </button>
      <button
        type="button"
        onClick={() => onTabChange('recognition')}
        className={cn(baseBtn, activeTab === 'recognition' ? activeCls : idleCls)}
      >
        <ScanLine className="w-4 h-4" />
        <span>Cấu Hình Nhận Diện</span>
        <Badge value={activePatternCount} tone="gray" />
      </button>
    </div>
  );
};
