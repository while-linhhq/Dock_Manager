import React, { useState } from 'react';
import { Camera, Grid3X3 } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { FusionGroupListView } from './FusionGroupListView';
import { SingleCameraListView } from './SingleCameraListView';

type CameraFusionTab = 'single' | 'groups';

const TABS: Array<{
  id: CameraFusionTab;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
}> = [
  { id: 'single', label: 'Camera đơn', icon: Camera },
  { id: 'groups', label: 'Group Camera', icon: Grid3X3 },
];

export const CameraFusionTabsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<CameraFusionTab>('single');

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-black tracking-tight text-gray-900 dark:text-white">
          Ghép Camera
        </h1>
        <p className="text-sm text-gray-500">
          Quản lý camera đơn và cấu hình group camera cho fused frame.
        </p>
      </div>

      <div className="flex w-fit space-x-1 overflow-x-auto rounded-xl bg-gray-100 p-1 dark:bg-white/5">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                'flex items-center space-x-2 whitespace-nowrap rounded-lg px-6 py-2 text-xs font-bold uppercase tracking-widest transition-all',
                activeTab === tab.id
                  ? 'bg-white text-blue-600 shadow-sm dark:bg-blue-600 dark:text-white'
                  : 'text-gray-500 hover:text-gray-900 dark:hover:text-white',
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {activeTab === 'single' ? <SingleCameraListView /> : <FusionGroupListView compact />}
    </div>
  );
};
