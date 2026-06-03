import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Upload } from 'lucide-react';
import { useVesselStore } from '../store/vesselStore';
import type { VesselCreate, VesselTypeCreate } from '../services/vesselsApi';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import { resolveApiAssetUrl } from '../../../utils/resolve-api-asset-url';
import { vesselSchema, vesselTypeSchema } from '../vessels-schemas';
import { VesselsMainTabs, type VesselsMainTab } from '../components/VesselsMainTabs';
import { VesselsListSection } from '../components/VesselsListSection';
import { VesselTypesSection } from '../components/VesselTypesSection';
import { VesselsModals } from '../components/VesselsModals';
import { vesselsApi } from '../services/vesselsApi';
import { ApiError } from '../../../services/httpClient';
import { Modal } from '../../../components/Modal/Modal';
import { Button } from '../../../components/Button/Button';
import type { VesselVisualReference } from '../services/vesselsApi';

export const VesselsView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<VesselsMainTab>('vessels');
  const [isVesselModalOpen, setIsVesselModalOpen] = useState(false);
  const [isTypeModalOpen, setIsTypeModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [vesselQ, setVesselQ] = useState('');
  const [vesselTypeFilter, setVesselTypeFilter] = useState('');
  const [vesselActive, setVesselActive] = useState<'all' | 'active' | 'inactive'>('all');
  const [vesselDateFrom, setVesselDateFrom] = useState('');
  const [vesselDateTo, setVesselDateTo] = useState('');
  const [typeQ, setTypeQ] = useState('');
  const [uploadTarget, setUploadTarget] = useState<VesselRead | null>(null);
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadPreviewUrls, setUploadPreviewUrls] = useState<string[]>([]);
  const [isUploadingImage, setIsUploadingImage] = useState(false);
  const [references, setReferences] = useState<VesselVisualReference[]>([]);
  const [isLoadingReferences, setIsLoadingReferences] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const {
    vessels,
    vesselTypes,
    isLoading,
    fetchVessels,
    fetchVesselTypes,
    upsertVessel,
    upsertVesselType,
    deleteVessel,
    deleteVesselType,
  } = useVesselStore();

  const vesselForm = useForm<VesselCreate>({
    resolver: zodResolver(vesselSchema),
    defaultValues: { is_active: true },
  });

  const typeForm = useForm<VesselTypeCreate>({
    resolver: zodResolver(vesselTypeSchema),
  });

  useEffect(() => {
    if (activeTab === 'vessels') {
      fetchVessels();
      fetchVesselTypes();
    } else {
      fetchVesselTypes();
    }
  }, [activeTab, fetchVessels, fetchVesselTypes]);

  const filteredVessels = useMemo(() => {
    return vessels.filter((v) => {
      if (
        !matchesAnyField(
          vesselQ,
          v.ship_id,
          v.name,
          v.owner,
          v.owner_info,
          v.registration_number,
        )
      ) {
        return false;
      }
      if (vesselTypeFilter && String(v.vessel_type_id ?? '') !== vesselTypeFilter) {
        return false;
      }
      if (vesselActive === 'active' && !v.is_active) {
        return false;
      }
      if (vesselActive === 'inactive' && v.is_active) {
        return false;
      }
      const t = v.created_at ?? v.last_seen ?? v.updated_at;
      if (!isoInLocalDateRange(t, vesselDateFrom, vesselDateTo)) {
        return false;
      }
      return true;
    });
  }, [vessels, vesselQ, vesselTypeFilter, vesselActive, vesselDateFrom, vesselDateTo]);

  const filteredTypes = useMemo(() => {
    return vesselTypes.filter((t) => matchesAnyField(typeQ, t.type_name, t.description));
  }, [vesselTypes, typeQ]);

  const vesselFilterCount =
    (vesselQ.trim() ? 1 : 0) +
    (vesselTypeFilter ? 1 : 0) +
    (vesselActive !== 'all' ? 1 : 0) +
    (vesselDateFrom ? 1 : 0) +
    (vesselDateTo ? 1 : 0);

  const resetVesselFilters = () => {
    setVesselQ('');
    setVesselTypeFilter('');
    setVesselActive('all');
    setVesselDateFrom('');
    setVesselDateTo('');
  };

  const onVesselSubmit = async (data: VesselCreate) => {
    try {
      await upsertVessel(editingId, data);
      setIsVesselModalOpen(false);
      vesselForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onTypeSubmit = async (data: VesselTypeCreate) => {
    try {
      await upsertVesselType(editingId, data);
      setIsTypeModalOpen(false);
      typeForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditVessel = (vessel: VesselRead) => {
    setEditingId(String(vessel.id));
    vesselForm.reset({
      ship_id: vessel.ship_id,
      name: vessel.name ?? '',
      vessel_type_id: vessel.vessel_type_id != null ? String(vessel.vessel_type_id) : '',
      owner_info: vessel.owner ?? vessel.owner_info ?? '',
      is_active: vessel.is_active,
    });
    setIsVesselModalOpen(true);
  };

  const handleEditType = (type: VesselTypeRead) => {
    setEditingId(String(type.id));
    typeForm.reset({
      type_name: type.type_name,
      description: type.description ?? '',
    });
    setIsTypeModalOpen(true);
  };

  const handleDeleteVessel = async (id: string) => {
    if (!window.confirm('Xác nhận xóa tàu này?')) {
      return;
    }
    await deleteVessel(id);
  };

  const handleDeleteType = async (id: string | number) => {
    if (!window.confirm('Xác nhận xóa loại tàu này?')) {
      return;
    }
    await deleteVesselType(String(id));
  };

  const clearUploadPreviews = () => {
    uploadPreviewUrls.forEach((url) => URL.revokeObjectURL(url));
    setUploadPreviewUrls([]);
  };

  const handleUploadVesselImages = async (vesselId: string, files: File[]) => {
    try {
      setIsUploadingImage(true);
      const result = await vesselsApi.uploadVesselReferenceImages(vesselId, files);
      const enrolledCount = result.count ?? (result.point_id ? 1 : 0);
      const failedCount = result.failed?.length ?? 0;
      if (failedCount > 0) {
        setStatusMessage(
          `Đã trích đặc trưng ${enrolledCount} ảnh, thất bại ${failedCount} ảnh.`,
        );
      } else {
        setStatusMessage(`Upload và trích đặc trưng thành công ${enrolledCount} ảnh.`);
      }
      const latest = await vesselsApi.getVesselReferenceImages(vesselId);
      setReferences(latest.items || []);
      await fetchVessels();
      setUploadFiles([]);
      clearUploadPreviews();
    } catch (error) {
      console.error(error);
      const detail =
        error instanceof ApiError ? error.message : 'Upload ảnh mẫu thất bại. Vui lòng thử lại.';
      setStatusMessage(detail);
    } finally {
      setIsUploadingImage(false);
    }
  };

  const handleOpenUploadModal = (v: VesselRead) => {
    clearUploadPreviews();
    setUploadTarget(v);
    setUploadFiles([]);
    setStatusMessage(null);
    setIsLoadingReferences(true);
    void vesselsApi
      .getVesselReferenceImages(String(v.id))
      .then((resp) => setReferences(resp.items || []))
      .catch((err) => {
        console.error(err);
        setReferences([]);
      })
      .finally(() => setIsLoadingReferences(false));
  };

  const handleCloseUploadModal = () => {
    setUploadTarget(null);
    setUploadFiles([]);
    setReferences([]);
    setStatusMessage(null);
    clearUploadPreviews();
  };

  const handleDeleteReference = async (vesselId: string, pointId: string) => {
    try {
      await vesselsApi.deleteVesselReferenceImage(vesselId, pointId);
      setReferences((prev) => prev.filter((ref) => ref.id !== pointId));
      setStatusMessage('Đã xóa ảnh mẫu thành công.');
      await fetchVessels();
    } catch (err) {
      console.error(err);
      setStatusMessage('Xóa ảnh mẫu thất bại.');
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <VesselsMainTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'vessels' ? (
        <VesselsListSection
          vesselQ={vesselQ}
          setVesselQ={setVesselQ}
          vesselTypeFilter={vesselTypeFilter}
          setVesselTypeFilter={setVesselTypeFilter}
          vesselActive={vesselActive}
          setVesselActive={setVesselActive}
          vesselDateFrom={vesselDateFrom}
          setVesselDateFrom={setVesselDateFrom}
          vesselDateTo={vesselDateTo}
          setVesselDateTo={setVesselDateTo}
          resetVesselFilters={resetVesselFilters}
          vesselFilterCount={vesselFilterCount}
          onOpenAddVessel={() => {
            setEditingId(null);
            vesselForm.reset({ is_active: true });
            setIsVesselModalOpen(true);
          }}
          vesselTypes={vesselTypes}
          vessels={vessels}
          filteredVessels={filteredVessels}
          isLoading={isLoading}
          onEditVessel={handleEditVessel}
          onDeleteVessel={handleDeleteVessel}
          onOpenUploadModal={handleOpenUploadModal}
        />
      ) : (
        <VesselTypesSection
          typeQ={typeQ}
          setTypeQ={setTypeQ}
          resetTypeFilters={() => setTypeQ('')}
          typeFilterCount={typeQ.trim() ? 1 : 0}
          onOpenAddType={() => {
            setEditingId(null);
            typeForm.reset();
            setIsTypeModalOpen(true);
          }}
          vesselTypes={vesselTypes}
          filteredTypes={filteredTypes}
          isLoading={isLoading}
          onEditType={handleEditType}
          onDeleteType={(id) => void handleDeleteType(id)}
        />
      )}

      <VesselsModals
        isVesselModalOpen={isVesselModalOpen}
        onCloseVessel={() => setIsVesselModalOpen(false)}
        vesselForm={vesselForm}
        onVesselSubmit={onVesselSubmit}
        editingId={editingId}
        vesselTypes={vesselTypes}
        isLoading={isLoading}
        isTypeModalOpen={isTypeModalOpen}
        onCloseType={() => setIsTypeModalOpen(false)}
        typeForm={typeForm}
        onTypeSubmit={onTypeSubmit}
      />

      <Modal
        isOpen={Boolean(uploadTarget)}
        onClose={handleCloseUploadModal}
        title={`Upload ảnh mẫu - ${uploadTarget?.ship_id ?? ''}`}
        className="max-w-2xl"
      >
        <div className="space-y-4">
          <p className="text-xs text-gray-600 dark:text-gray-300">
            Ảnh này sẽ dùng để trích đặc trưng visual cho tàu <strong>{uploadTarget?.ship_id}</strong>.
          </p>
          <label
            className="block border-2 border-dashed border-gray-300 dark:border-white/15 rounded-xl p-6 cursor-pointer
            hover:border-blue-500 transition-colors bg-gray-50/50 dark:bg-white/[0.02]"
          >
            <input
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={(e) => {
                const selected = Array.from(e.target.files ?? []);
                clearUploadPreviews();
                setUploadFiles(selected);
                setUploadPreviewUrls(selected.map((file) => URL.createObjectURL(file)));
                e.target.value = '';
              }}
            />
            <div className="flex items-center gap-3 text-sm text-gray-700 dark:text-gray-200">
              <Upload className="w-5 h-5 text-blue-500" />
              <span>
                {uploadFiles.length > 0
                  ? `Đã chọn ${uploadFiles.length} ảnh`
                  : 'Chọn một hoặc nhiều ảnh tàu (jpg/png/webp) để trích đặc trưng'}
              </span>
            </div>
          </label>

          {uploadPreviewUrls.length > 0 ? (
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 max-h-[320px] overflow-auto">
              {uploadPreviewUrls.map((url, index) => (
                <div
                  key={`${url}-${index}`}
                  className="rounded-xl overflow-hidden border border-gray-200 dark:border-white/10"
                >
                  <img
                    src={url}
                    alt={`Preview upload ${index + 1}`}
                    className="w-full h-28 object-cover bg-black/5 dark:bg-black/20"
                  />
                </div>
              ))}
            </div>
          ) : null}

          <div className="rounded-xl border border-gray-200 dark:border-white/10">
            <div className="px-4 py-3 border-b border-gray-100 dark:border-white/10">
              <p className="text-xs font-semibold text-gray-700 dark:text-gray-200">
                Ảnh mẫu đã upload ({references.length})
              </p>
            </div>
            <div className="max-h-72 overflow-auto p-3">
              {isLoadingReferences ? (
                <div className="text-sm text-gray-500">Đang tải danh sách ảnh mẫu...</div>
              ) : references.length === 0 ? (
                <div className="text-sm text-gray-500">Chưa có ảnh mẫu nào.</div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {references.map((item) => {
                    const previewSrc = resolveApiAssetUrl(item.preview_url);
                    return (
                    <div
                      key={item.id}
                      className="rounded-xl border border-gray-200 dark:border-white/10 overflow-hidden bg-gray-50/50 dark:bg-white/[0.02]"
                    >
                      <div className="aspect-[4/3] bg-black/5 dark:bg-black/20 flex items-center justify-center">
                        {previewSrc ? (
                          <img
                            src={previewSrc}
                            alt={item.payload?.filename || item.id}
                            className="w-full h-full object-cover"
                            loading="lazy"
                          />
                        ) : (
                          <span className="text-[11px] text-gray-400 px-2 text-center">
                            Không có preview
                          </span>
                        )}
                      </div>
                      <div className="p-2 space-y-1">
                        <p
                          className="text-[11px] font-medium text-gray-800 dark:text-gray-100 truncate"
                          title={item.payload?.filename || item.id}
                        >
                          {item.payload?.filename || item.id}
                        </p>
                        <p className="text-[10px] text-gray-500 truncate">
                          {item.payload?.enrolled_at
                            ? new Date(item.payload.enrolled_at).toLocaleString('vi-VN')
                            : 'N/A'}
                        </p>
                        <button
                          type="button"
                          className="text-[11px] text-red-600 hover:text-red-500"
                          onClick={() => void handleDeleteReference(String(uploadTarget?.id), item.id)}
                        >
                          Xóa
                        </button>
                      </div>
                    </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {statusMessage ? (
            <div className="text-xs px-3 py-2 rounded-lg bg-gray-100 text-gray-700 dark:bg-white/10 dark:text-gray-200">
              {statusMessage}
            </div>
          ) : null}

          <div className="flex gap-3 pt-2">
            <Button type="button" variant="outline" className="flex-1" onClick={handleCloseUploadModal}>
              Hủy
            </Button>
            <Button
              type="button"
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white"
              disabled={!uploadTarget || uploadFiles.length === 0 || isUploadingImage}
              onClick={() => {
                if (!uploadTarget || uploadFiles.length === 0) {
                  return;
                }
                void handleUploadVesselImages(String(uploadTarget.id), uploadFiles);
              }}
            >
              {isUploadingImage ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                `Upload & Trích đặc trưng (${uploadFiles.length || 0})`
              )}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
