import React, { useState } from 'react';
import { FlaskConical, Grid2X2, ScanSearch, ScanText, Video } from 'lucide-react';
import { cn } from '../../../utils/cn';
import { DetectionLabPanel } from '../components/DetectionLabPanel';
import { EmbeddingComparePanel } from '../components/EmbeddingComparePanel';
import { GroupCamTestPanel } from '../components/GroupCamTestPanel';
import { OcrLabPanel } from '../components/OcrLabPanel';

type LabTab = 'detection' | 'group-cam' | 'ocr' | 'embedding';

export const AiLabView: React.FC = () => {
  const [tab, setTab] = useState<LabTab>('detection');

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-blue-600/10 p-3 text-blue-500">
            <FlaskConical className="h-5 w-5" />
          </div>
          <div>
            <h1 className="text-xl font-extrabold tracking-tight text-gray-900 dark:text-white">
              AI Lab — Kiểm tra &amp; so sánh
            </h1>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Test nhận diện, OCR pipeline và tra cứu embedding Qdrant
            </p>
          </div>
        </div>

        <div className="flex rounded-lg bg-gray-200/80 dark:bg-white/10 p-0.5">
          <button
            type="button"
            onClick={() => setTab('detection')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-all',
              tab === 'detection'
                ? 'bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400',
            )}
          >
            <Video className="h-3.5 w-3.5" />
            Nhận diện
          </button>
          <button
            type="button"
            onClick={() => setTab('ocr')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-all',
              tab === 'ocr'
                ? 'bg-white dark:bg-emerald-600 text-emerald-600 dark:text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400',
            )}
          >
            <ScanText className="h-3.5 w-3.5" />
            OCR
          </button>
          <button
            type="button"
            onClick={() => setTab('group-cam')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-all',
              tab === 'group-cam'
                ? 'bg-white dark:bg-cyan-600 text-cyan-600 dark:text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400',
            )}
          >
            <Grid2X2 className="h-3.5 w-3.5" />
            Group Cam Test
          </button>
          <button
            type="button"
            onClick={() => setTab('embedding')}
            className={cn(
              'inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-[10px] font-bold uppercase tracking-widest transition-all',
              tab === 'embedding'
                ? 'bg-white dark:bg-violet-600 text-violet-600 dark:text-white shadow-sm'
                : 'text-gray-600 dark:text-gray-400',
            )}
          >
            <ScanSearch className="h-3.5 w-3.5" />
            Embedding
          </button>
        </div>
      </div>

      {tab === 'detection' ? (
        <DetectionLabPanel />
      ) : tab === 'group-cam' ? (
        <GroupCamTestPanel />
      ) : tab === 'ocr' ? (
        <OcrLabPanel />
      ) : (
        <EmbeddingComparePanel />
      )}
    </div>
  );
};
