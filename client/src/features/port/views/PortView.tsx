import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { usePortStore } from '../store/portStore';
import {
  portApi,
  type CameraCreate,
  type DetectionFilters,
  type DetectionSort,
  type DetectionUpdate,
  type PortConfigCreate,
  type PortConfigRead,
} from '../services/portApi';
import type { DetectionRead } from '../../../types/api.types';
import { matchesAnyField } from '../../../utils/table-filters';
import { useFilterOptions } from '../../../hooks/useFilterOptions';
import { usePagedQuery } from '../../../hooks/usePagedQuery';
import { cameraSchema, configSchema } from '../port-schemas';
import { PortMainTabs, type PortMainTab } from '../components/PortMainTabs';
import { PortDetectionsSection } from '../components/PortDetectionsSection';
import { PortConfigsSection } from '../components/PortConfigsSection';
import { PortPipelineSection } from '../components/PortPipelineSection';
import { PortSeamAnchorSection } from '../components/PortSeamAnchorSection';
import {
  PortPaymentConfigSection,
  SEPAY_PORT_CONFIG_KEYS,
} from '../components/PortPaymentConfigSection';
import { PortModals } from '../components/PortModals';

const PORT_TAB_IDS: PortMainTab[] = ['detections', 'configs', 'payment', 'pipeline', 'seam-anchor'];

const SEPAY_CONFIG_KEY_SET = new Set<string>(SEPAY_PORT_CONFIG_KEYS);

function parsePortTab(value: string | null): PortMainTab {
  if (value && PORT_TAB_IDS.includes(value as PortMainTab)) {
    return value as PortMainTab;
  }
  return 'detections';
}

export const PortView: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = useMemo(
    () => parsePortTab(searchParams.get('tab')),
    [searchParams],
  );
  const [isCameraModalOpen, setIsCameraModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingConfigKey, setEditingConfigKey] = useState<string | null>(null);
  const [pipelineTabEnableOcr, setPipelineTabEnableOcr] = useState(true);
  const [detQ, setDetQ] = useState('');
  const [detAccepted, setDetAccepted] = useState<'all' | 'yes' | 'no'>('all');
  const [detShipIdFilter, setDetShipIdFilter] = useState('');
  const [detVesselTypeFilter, setDetVesselTypeFilter] = useState('');
  const [detDateFrom, setDetDateFrom] = useState('');
  const [detDateTo, setDetDateTo] = useState('');
  const [detMinConfPct, setDetMinConfPct] = useState('');
  const [cfgKeyQ, setCfgKeyQ] = useState('');
  const [cfgValQ, setCfgValQ] = useState('');

  const {
    configs,
    isLoading,
    fetchConfigs,
    verifyDetection,
    updateDetection,
    upsertCamera,
    upsertConfig,
    deleteConfig,
    deleteDetection,
    startPipeline,
    stopPipeline,
    shutdownServer,
  } = usePortStore();
  const { vessels: filterVessels, vesselTypes: filterVesselTypes } = useFilterOptions();

  // Bảy ô lọc của bảng nhận diện → tham số API; server lọc/sắp xếp, client không
  // còn lọc lại (trước đây `filteredDetections` lọc trên tối đa 200 bản ghi).
  const detFilters = useMemo<DetectionFilters>(
    () => ({
      q: detQ.trim() || undefined,
      isAccepted: detAccepted,
      vesselId: detShipIdFilter || undefined,
      vesselTypeId: detVesselTypeFilter || undefined,
      dateFrom: detDateFrom || undefined,
      dateTo: detDateTo || undefined,
      minConfidencePct: detMinConfPct.trim() || undefined,
    }),
    [
      detQ,
      detAccepted,
      detShipIdFilter,
      detVesselTypeFilter,
      detDateFrom,
      detDateTo,
      detMinConfPct,
    ],
  );

  // `usePagedQuery` là nguồn sự thật duy nhất cho trang/bộ lọc/sắp xếp của danh
  // sách nhận diện; `filters` truyền vào chỉ là giá trị KHỞI TẠO.
  const {
    items: detections,
    total: detectionsTotal,
    page: detectionsPage,
    pageSize: detectionsPageSize,
    isLoading: detectionsLoading,
    error: detectionsError,
    setPage: setDetectionsPage,
    setPageSize: setDetectionsPageSize,
    setFilters: setDetFilters,
    setSort: setDetSort,
    reload: reloadDetections,
  } = usePagedQuery<DetectionRead, DetectionFilters, DetectionSort>({
    fetcher: portApi.getDetectionsPage,
    filters: detFilters,
  });

  // Đẩy nội dung bộ lọc xuống hook. Object đã được memo hoá nên hiệu ứng chỉ chạy
  // khi bộ lọc THỰC SỰ đổi; hook tự đưa `page` về 1 rồi debounce trước khi gọi API.
  // Bỏ qua lần chạy đầu vì hook đã KHỞI TẠO bằng chính `detFilters` (đẩy lại đúng
  // object đó chỉ làm hook tăng token nạp lại → thêm một request thừa lúc mở trang).
  const pushedDetFiltersRef = useRef(detFilters);
  useEffect(() => {
    if (pushedDetFiltersRef.current === detFilters) {
      return;
    }
    pushedDetFiltersRef.current = detFilters;
    setDetFilters(detFilters);
  }, [detFilters, setDetFilters]);

  const cameraForm = useForm<CameraCreate>({
    resolver: zodResolver(cameraSchema),
    defaultValues: { is_active: true },
  });

  const configForm = useForm<PortConfigCreate>({
    resolver: zodResolver(configSchema),
  });

  const handleTabChange = (tab: PortMainTab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'detections') {
      next.delete('tab');
    } else {
      next.set('tab', tab);
    }
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    // Danh sách nhận diện do `usePagedQuery` tự nạp (kèm phân trang/bộ lọc).
    if (activeTab === 'configs' || activeTab === 'payment' || activeTab === 'seam-anchor') {
      fetchConfigs();
    }
  }, [activeTab, fetchConfigs]);

  const filteredConfigs = useMemo(() => {
    return configs.filter((cfg) => {
      if (SEPAY_CONFIG_KEY_SET.has(cfg.key)) {
        return false;
      }
      if (!matchesAnyField(cfgKeyQ, cfg.key)) {
        return false;
      }
      if (!matchesAnyField(cfgValQ, cfg.value, cfg.description)) {
        return false;
      }
      return true;
    });
  }, [configs, cfgKeyQ, cfgValQ]);

  const detFilterCount =
    (detQ.trim() ? 1 : 0) +
    (detAccepted !== 'all' ? 1 : 0) +
    (detShipIdFilter ? 1 : 0) +
    (detVesselTypeFilter ? 1 : 0) +
    (detDateFrom ? 1 : 0) +
    (detDateTo ? 1 : 0) +
    (detMinConfPct.trim() ? 1 : 0);

  const cfgFilterCount = (cfgKeyQ.trim() ? 1 : 0) + (cfgValQ.trim() ? 1 : 0);

  const resetDetFilters = () => {
    setDetQ('');
    setDetAccepted('all');
    setDetShipIdFilter('');
    setDetVesselTypeFilter('');
    setDetDateFrom('');
    setDetDateTo('');
    setDetMinConfPct('');
  };

  const resetCfgFilters = () => {
    setCfgKeyQ('');
    setCfgValQ('');
  };

  const onCameraSubmit = async (data: CameraCreate) => {
    try {
      await upsertCamera(editingId, data);
      setIsCameraModalOpen(false);
      cameraForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onConfigSubmit = async (data: PortConfigCreate) => {
    try {
      await upsertConfig(editingConfigKey, data);
      setIsConfigModalOpen(false);
      configForm.reset();
      setEditingConfigKey(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditConfig = (cfg: PortConfigRead) => {
    setEditingConfigKey(cfg.key);
    configForm.reset({
      key: cfg.key,
      value: cfg.value,
      description: cfg.description || '',
    });
    setIsConfigModalOpen(true);
  };

  const handleDeleteConfig = async (key: string) => {
    if (!window.confirm(`Xác nhận xóa config "${key}"?`)) {
      return;
    }
    await deleteConfig(key);
  };

  const handleShutdownServer = async () => {
    if (
      !window.confirm(
        'Ngắt server sẽ dừng pipeline, kill process OCR và tắt tiến trình backend. ' +
          'Phải khởi động lại server thủ công. Xác nhận?',
      )
    ) {
      return;
    }
    try {
      const killed = await shutdownServer();
      window.alert(
        `Server đang tắt. Đã kill ${killed.length} orphan OCR process` +
          (killed.length ? ` (PID: ${killed.join(', ')}).` : '.'),
      );
    } catch (err) {
      console.error(err);
      window.alert('Ngắt server thất bại. Xem console để biết chi tiết.');
    }
  };

  // Sau mỗi mutation, nạp lại ĐÚNG trang/bộ lọc đang xem (thay vì tải lại cả bảng).
  const handleDeleteDetection = async (id: string) => {
    if (!window.confirm('Xác nhận xóa bản ghi nhận diện này?')) {
      return;
    }
    await deleteDetection(id);
    reloadDetections();
  };

  const handleUpdateDetection = async (id: string, data: DetectionUpdate) => {
    await updateDetection(id, data);
    reloadDetections();
  };

  const handleVerifyDetection = async (id: string, data: { is_accepted: boolean }) => {
    await verifyDetection(id, data);
    reloadDetections();
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <PortMainTabs activeTab={activeTab} onTabChange={handleTabChange} />

      {activeTab === 'detections' && (
        <PortDetectionsSection
          detQ={detQ}
          setDetQ={setDetQ}
          detAccepted={detAccepted}
          setDetAccepted={setDetAccepted}
          detShipIdFilter={detShipIdFilter}
          setDetShipIdFilter={setDetShipIdFilter}
          detVesselTypeFilter={detVesselTypeFilter}
          setDetVesselTypeFilter={setDetVesselTypeFilter}
          detDateFrom={detDateFrom}
          setDetDateFrom={setDetDateFrom}
          detDateTo={detDateTo}
          setDetDateTo={setDetDateTo}
          detMinConfPct={detMinConfPct}
          setDetMinConfPct={setDetMinConfPct}
          resetDetFilters={resetDetFilters}
          detFilterCount={detFilterCount}
          onRefresh={reloadDetections}
          isLoading={detectionsLoading}
          error={detectionsError}
          detections={detections}
          page={detectionsPage}
          pageSize={detectionsPageSize}
          total={detectionsTotal}
          onPageChange={setDetectionsPage}
          onPageSizeChange={setDetectionsPageSize}
          onSortChange={setDetSort}
          vessels={filterVessels}
          vesselTypes={filterVesselTypes}
          onVerify={handleVerifyDetection}
          onDeleteDetection={handleDeleteDetection}
          onUpdateDetection={handleUpdateDetection}
        />
      )}

      {activeTab === 'payment' && (
        <PortPaymentConfigSection
          configs={configs}
          isLoading={isLoading}
          onUpdateConfig={(key, value, description) =>
            upsertConfig(key, { value, description })
          }
          onCreateConfig={(key, value, description) =>
            upsertConfig(null, { key, value, description })
          }
          onRefresh={fetchConfigs}
        />
      )}

      {activeTab === 'configs' && (
        <PortConfigsSection
          cfgKeyQ={cfgKeyQ}
          setCfgKeyQ={setCfgKeyQ}
          cfgValQ={cfgValQ}
          setCfgValQ={setCfgValQ}
          resetCfgFilters={resetCfgFilters}
          cfgFilterCount={cfgFilterCount}
          onOpenAddConfig={() => {
            setEditingConfigKey(null);
            configForm.reset({ key: '', value: '', description: '' });
            setIsConfigModalOpen(true);
          }}
          filteredConfigs={filteredConfigs}
          configs={configs}
          onEditConfig={handleEditConfig}
          onDeleteConfig={handleDeleteConfig}
          onToggleConfig={(key, value, description) =>
            upsertConfig(key, { value, description })
          }
          onShutdownServer={handleShutdownServer}
        />
      )}

      {activeTab === 'seam-anchor' && (
        <PortSeamAnchorSection
          configs={configs}
          isLoading={isLoading}
          onUpdateConfig={(key, value, description) =>
            upsertConfig(key, { value, description })
          }
          onCreateConfig={(key, value, description) =>
            upsertConfig(null, { key, value, description })
          }
          onRefresh={fetchConfigs}
        />
      )}

      {activeTab === 'pipeline' && (
        <PortPipelineSection
          isLoading={isLoading}
          startPipeline={startPipeline}
          stopPipeline={stopPipeline}
          pipelineTabEnableOcr={pipelineTabEnableOcr}
          setPipelineTabEnableOcr={setPipelineTabEnableOcr}
        />
      )}

      <PortModals
        isCameraModalOpen={isCameraModalOpen}
        onCloseCamera={() => setIsCameraModalOpen(false)}
        cameraForm={cameraForm}
        onCameraSubmit={onCameraSubmit}
        editingCameraId={editingId}
        isLoading={isLoading}
        isConfigModalOpen={isConfigModalOpen}
        onCloseConfig={() => setIsConfigModalOpen(false)}
        configForm={configForm}
        onConfigSubmit={onConfigSubmit}
        editingConfigKey={editingConfigKey}
      />
    </div>
  );
};
