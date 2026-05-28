import React, { useEffect, useMemo, useState } from 'react';
import { Cpu, Loader2, Play, Square } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import type { PipelineStartRequest } from '../services/portApi';
import { cameraGroupsApi, type CameraGroup } from '../../camera-fusion';

export type PortPipelineSectionProps = {
  isLoading: boolean;
  startPipeline: (req: PipelineStartRequest) => Promise<void>;
  stopPipeline: () => Promise<void>;
  pipelineTabEnableOcr: boolean;
  setPipelineTabEnableOcr: (v: boolean) => void;
};

export const PortPipelineSection: React.FC<PortPipelineSectionProps> = ({
  isLoading,
  startPipeline,
  stopPipeline,
  pipelineTabEnableOcr,
  setPipelineTabEnableOcr,
}) => {
  const [cameraGroups, setCameraGroups] = useState<CameraGroup[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState('');
  const selectedGroup = useMemo(
    () => cameraGroups.find((group) => String(group.id) === selectedGroupId),
    [cameraGroups, selectedGroupId],
  );

  useEffect(() => {
    cameraGroupsApi.list(true).then(setCameraGroups).catch(console.error);
  }, []);

  const canStart = selectedGroupId.length > 0;

  return (
    <div className="max-w-2xl mx-auto bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl p-8 space-y-8">
      <div className="text-center space-y-2">
        <div className="p-4 bg-blue-600/10 rounded-full w-fit mx-auto">
          <Cpu className="w-12 h-12 text-blue-600" />
        </div>
        <h3 className="text-lg font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Điều Khiển AI Core
        </h3>
        <p className="text-xs text-gray-500 uppercase tracking-widest">
          Khởi chạy hoặc dừng luồng xử lý nhận diện tàu
        </p>
      </div>

      <div className="rounded-2xl border border-gray-200 dark:border-white/10 bg-gray-50 dark:bg-white/[0.03] p-6 space-y-5">
        <div>
          <h4 className="text-[10px] font-bold text-gray-500 uppercase tracking-widest mb-1">
            Khởi chạy pipeline
          </h4>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">
            Chỉ hỗ trợ chạy theo Camera Group để đồng bộ multi-camera và Seam Anchor.
          </p>
        </div>
        <div>
          <label className="mb-2 block text-[10px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
            Camera Group
          </label>
          <>
            <select
              value={selectedGroupId}
              className="w-full rounded-xl border border-gray-200 bg-white px-3 py-2.5 text-sm dark:border-white/10 dark:bg-[#121214] dark:text-white"
              onChange={(e) => setSelectedGroupId(e.target.value)}
            >
              <option value="">-- Chọn camera group --</option>
              {cameraGroups.map((group) => (
                <option key={group.id} value={String(group.id)}>
                  {group.name} ({group.members.length} cameras)
                </option>
              ))}
            </select>
            {selectedGroup ? (
              <p className="mt-2 rounded-xl bg-blue-50 px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-blue-600 dark:bg-blue-950/30 dark:text-blue-300">
                Mode:{' '}
                {selectedGroup.pipeline_mode === 'fused'
                  ? 'Frame ghép thủ công từ layout canvas'
                  : 'Camera rời rạc đa luồng + Re-ID'}
              </p>
            ) : (
              <p className="mt-2 text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wide">
                Chưa chọn Camera Group.
              </p>
            )}
            {!cameraGroups.length ? (
              <p className="mt-2 text-[10px] font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wide">
                Chưa có group khả dụng — tạo group trong Camera Fusion trước khi chạy pipeline.
              </p>
            ) : null}
          </>
        </div>
        <div className="flex items-center space-x-2">
          <input
            type="checkbox"
            id="pipeline_tab_ocr"
            checked={pipelineTabEnableOcr}
            onChange={(e) => setPipelineTabEnableOcr(e.target.checked)}
            className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
          />
          <label
            htmlFor="pipeline_tab_ocr"
            className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
          >
            Bật OCR mã tàu
          </label>
        </div>
        <Button
          type="button"
          disabled={!canStart || isLoading}
          onClick={async () => {
            if (!canStart) {
              return;
            }
            try {
              await startPipeline({
                camera_group_id: Number(selectedGroupId),
                enable_ocr: pipelineTabEnableOcr,
              });
            } catch (err) {
              console.error(err);
            }
          }}
          className="w-full py-3.5 bg-emerald-600 hover:bg-emerald-700 text-white flex items-center justify-center gap-2"
        >
          {isLoading ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <>
              <Play className="w-5 h-5 shrink-0" />
              <span className="text-xs font-bold uppercase tracking-widest">Bắt đầu pipeline</span>
            </>
          )}
        </Button>
      </div>

      <Button
        type="button"
        variant="outline"
        onClick={() => stopPipeline()}
        className="w-full py-4 border-red-200 dark:border-red-900/40 text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 flex items-center justify-center gap-2"
      >
        <Square className="w-5 h-5 shrink-0" />
        <span className="text-xs font-bold uppercase tracking-widest">Dừng pipeline</span>
      </Button>

      <div className="p-6 bg-gray-50 dark:bg-white/5 rounded-2xl border border-gray-100 dark:border-white/5 space-y-4">
        <h4 className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Trạng Thái Hiện Tại</h4>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-600 dark:text-gray-300 font-bold uppercase">Engine Status</span>
          <span className="flex items-center text-xs font-mono text-green-500 font-bold">
            <span className="w-2 h-2 bg-green-500 rounded-full mr-2 animate-pulse" />
            OPERATIONAL
          </span>
        </div>
      </div>
    </div>
  );
};
