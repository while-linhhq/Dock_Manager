import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useVesselStore } from '../store/vesselStore';
import type { VesselCreate, VesselTypeCreate } from '../services/vesselsApi';
import type { VesselRead, VesselTypeRead } from '../../../types/api.types';
import { isoInLocalDateRange, matchesAnyField } from '../../../utils/table-filters';
import { vesselSchema, vesselTypeSchema } from '../vessels-schemas';
import { VesselsMainTabs, type VesselsMainTab } from '../components/VesselsMainTabs';
import { VesselsListSection } from '../components/VesselsListSection';
import { VesselTypesSection } from '../components/VesselTypesSection';
import { VesselsModals } from '../components/VesselsModals';

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
    </div>
  );
};
