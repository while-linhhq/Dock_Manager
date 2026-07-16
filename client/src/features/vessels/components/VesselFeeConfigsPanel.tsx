import React, { useCallback, useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Pencil, Plus, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import type { FeeConfigRead } from '../../../types/api.types';
import {
  revenueApi,
  type FeeConfigCreate,
  type FeeConfigUpdatePayload,
} from '../../revenue/services/revenueApi';
import {
  feeSchema,
  type FeeFormInput,
  type FeeFormValues,
} from '../../revenue/revenue-schemas';
import {
  FeeField,
  FeeSection,
  feeControlClass,
  feeErrorClass,
  feeMonoControlClass,
} from '../../revenue/components/fee-config-form-ui';
import { FeeOperatingHoursEditor } from '../../revenue/components/FeeOperatingHoursEditor';
import {
  emptyOperatingHours,
  operatingHoursFromApi,
  operatingHoursToApi,
  type OperatingHours,
} from '../../revenue/types/fee-operating-hours';
import {
  FEE_BILLING_UNIT_AMOUNT_LABELS,
  FEE_BILLING_UNIT_LABELS,
  FEE_BILLING_UNITS,
  formatFeeConfigDisplay,
  normalizeFeeBillingUnit,
} from '../../../utils/fee-billing-unit';

export type VesselFeeConfigsPanelProps = {
  /** Chỉ có khi đang chỉnh sửa tàu đã lưu — fee gắn theo vessel_id. */
  vesselId: number;
  vesselShipId?: string;
};

const blankFeeForm = (): FeeFormValues =>
  ({
    fee_name: '',
    vessel_id: String(0),
    unit: 'per_month',
    base_fee: 0,
    is_active: true,
    berth_limit_count: undefined,
    berth_limit_unit: undefined,
    over_limit_penalty_amount: undefined,
    outside_hours_penalty_amount: undefined,
    max_berth_duration_minutes: undefined,
    over_duration_penalty_amount: undefined,
    operating_hours: emptyOperatingHours(),
  }) as FeeFormValues;

export const VesselFeeConfigsPanel: React.FC<VesselFeeConfigsPanelProps> = ({
  vesselId,
  vesselShipId,
}) => {
  const [fees, setFees] = useState<FeeConfigRead[]>([]);
  const [isLoadingList, setIsLoadingList] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [formOpen, setFormOpen] = useState(false);
  const [editingFeeId, setEditingFeeId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const feeForm = useForm<FeeFormInput, unknown, FeeFormValues>({
    resolver: zodResolver(feeSchema),
    defaultValues: blankFeeForm(),
  });
  const feeUnit = feeForm.watch('unit');

  const loadFees = useCallback(async () => {
    setIsLoadingList(true);
    setError(null);
    try {
      const list = await revenueApi.getFeeConfigsByVessel(vesselId);
      setFees(list);
    } catch (err) {
      console.error(err);
      setError('Không tải được danh sách phí của tàu.');
    } finally {
      setIsLoadingList(false);
    }
  }, [vesselId]);

  useEffect(() => {
    void loadFees();
  }, [loadFees]);

  const openAdd = () => {
    setEditingFeeId(null);
    feeForm.reset({ ...blankFeeForm(), vessel_id: String(vesselId) });
    setFormOpen(true);
  };

  const openEdit = (fee: FeeConfigRead) => {
    setEditingFeeId(fee.id);
    feeForm.reset({
      fee_name: fee.fee_name,
      vessel_id: String(vesselId),
      unit: normalizeFeeBillingUnit(fee.unit),
      base_fee: Number(fee.base_fee),
      is_active: fee.is_active,
      berth_limit_count:
        fee.berth_limit_count != null && fee.berth_limit_count > 0
          ? fee.berth_limit_count
          : undefined,
      berth_limit_unit:
        fee.berth_limit_unit === 'day' || fee.berth_limit_unit === 'month'
          ? fee.berth_limit_unit
          : undefined,
      over_limit_penalty_amount:
        fee.over_limit_penalty_amount != null && Number(fee.over_limit_penalty_amount) > 0
          ? Number(fee.over_limit_penalty_amount)
          : undefined,
      outside_hours_penalty_amount:
        fee.outside_hours_penalty_amount != null &&
        Number(fee.outside_hours_penalty_amount) > 0
          ? Number(fee.outside_hours_penalty_amount)
          : undefined,
      max_berth_duration_minutes:
        fee.max_berth_duration_minutes != null && fee.max_berth_duration_minutes > 0
          ? fee.max_berth_duration_minutes
          : undefined,
      over_duration_penalty_amount:
        fee.over_duration_penalty_amount != null &&
        Number(fee.over_duration_penalty_amount) > 0
          ? Number(fee.over_duration_penalty_amount)
          : undefined,
      operating_hours: operatingHoursFromApi(fee.operating_hours),
    });
    setFormOpen(true);
  };

  const closeForm = () => {
    setFormOpen(false);
    setEditingFeeId(null);
    feeForm.reset(blankFeeForm());
  };

  const onSubmit = async (data: FeeFormValues) => {
    setIsSaving(true);
    setError(null);
    try {
      const hasBerthLimit =
        data.berth_limit_count != null &&
        Number.isFinite(data.berth_limit_count) &&
        data.berth_limit_count > 0 &&
        data.berth_limit_unit;

      const payload: FeeConfigCreate & FeeConfigUpdatePayload = {
        fee_name: data.fee_name,
        base_fee: data.unit === 'none' ? 0 : data.base_fee,
        unit: data.unit,
        is_active: data.is_active,
        vessel_id: vesselId,
        berth_limit_count: hasBerthLimit ? data.berth_limit_count : null,
        berth_limit_unit: hasBerthLimit ? data.berth_limit_unit : null,
        over_limit_penalty_amount:
          data.over_limit_penalty_amount != null && data.over_limit_penalty_amount > 0
            ? data.over_limit_penalty_amount
            : null,
        outside_hours_penalty_amount:
          data.outside_hours_penalty_amount != null &&
          data.outside_hours_penalty_amount > 0
            ? data.outside_hours_penalty_amount
            : null,
        // Tàu lẻ giữ nghiệp vụ phạt cố định theo lượt, không dùng đơn giá ngoài giờ theo giờ.
        outside_hours_penalty_per_hour: null,
        max_berth_duration_minutes:
          data.max_berth_duration_minutes != null &&
          Number.isFinite(data.max_berth_duration_minutes) &&
          data.max_berth_duration_minutes > 0
            ? data.max_berth_duration_minutes
            : null,
        over_duration_penalty_amount:
          data.over_duration_penalty_amount != null && data.over_duration_penalty_amount > 0
            ? data.over_duration_penalty_amount
            : null,
        operating_hours: operatingHoursToApi(data.operating_hours ?? emptyOperatingHours()),
      };

      if (editingFeeId != null) {
        await revenueApi.updateFeeConfig(editingFeeId, payload);
      } else {
        await revenueApi.createFeeConfig(payload);
      }
      await loadFees();
      closeForm();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : 'Lưu cấu hình phí thất bại. Thử lại sau.';
      setError(msg);
      console.error(err);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (fee: FeeConfigRead) => {
    if (
      !window.confirm(
        `Xóa vĩnh viễn phí «${fee.fee_name}» của tàu này? Không hoàn tác. (Muốn tạm ngừng, dùng checkbox «Đang áp dụng».)`,
      )
    ) {
      return;
    }
    setError(null);
    try {
      await revenueApi.deleteFeeConfig(fee.id);
      if (editingFeeId === fee.id) {
        closeForm();
      }
      await loadFees();
    } catch (err) {
      console.error(err);
      setError('Xóa phí thất bại.');
    }
  };

  return (
    <div className="space-y-3 rounded-xl border border-gray-200 bg-gray-50/60 p-3 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex items-center justify-between">
        <h4 className="text-[10px] font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">
          Cấu hình giá của tàu {vesselShipId ? `«${vesselShipId}»` : ''}
        </h4>
        {!formOpen && (
          <button
            type="button"
            onClick={openAdd}
            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-2.5 py-1 text-[11px] font-semibold text-white transition-colors hover:bg-blue-700"
          >
            <Plus className="h-3.5 w-3.5" />
            Thêm phí
          </button>
        )}
      </div>

      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-[11px] font-medium text-red-600 dark:bg-red-500/10 dark:text-red-400">
          {error}
        </p>
      ) : null}

      {/* Danh sách phí hiện có */}
      {isLoadingList ? (
        <div className="flex items-center gap-2 py-3 text-xs text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Đang tải danh sách phí...
        </div>
      ) : fees.length === 0 ? (
        <p className="py-2 text-xs text-gray-500">
          Tàu chưa có cấu hình giá nào. Nhấn «Thêm phí» để tạo.
        </p>
      ) : (
        <ul className="space-y-1.5">
          {fees.map((fee) => (
            <li
              key={fee.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-gray-200 bg-white px-3 py-2 dark:border-white/10 dark:bg-white/5"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-gray-900 dark:text-white">
                  {fee.fee_name}
                  {!fee.is_active && (
                    <span className="ml-2 rounded bg-gray-200 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider text-gray-500 dark:bg-white/10 dark:text-gray-400">
                      Tạm ngừng
                    </span>
                  )}
                </p>
                <p className="text-[11px] font-mono text-gray-500 dark:text-gray-400">
                  {formatFeeConfigDisplay(fee.base_fee, fee.unit)}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <button
                  type="button"
                  onClick={() => openEdit(fee)}
                  title="Sửa phí"
                  className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-blue-600 dark:hover:bg-white/10"
                >
                  <Pencil className="h-4 w-4" />
                </button>
                <button
                  type="button"
                  onClick={() => void handleDelete(fee)}
                  title="Xóa phí"
                  className="rounded-lg p-1.5 text-gray-400 transition-colors hover:bg-gray-100 hover:text-red-600 dark:hover:bg-white/10"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* Form thêm/sửa phí — KHÔNG dùng <form> để tránh lồng trong form tàu */}
      {formOpen && (
        <div className="space-y-3 rounded-xl border border-blue-200 bg-white p-3 dark:border-blue-500/30 dark:bg-white/[0.02]">
          <p className="text-[10px] font-bold uppercase tracking-widest text-blue-600 dark:text-blue-400">
            {editingFeeId != null ? 'Chỉnh sửa phí' : 'Thêm phí mới'}
          </p>

          <FeeSection title="Thông tin phí">
            <FeeField label="Tên phí" error={feeForm.formState.errors.fee_name?.message}>
              <input
                type="text"
                placeholder="VD: Phí cập cảng"
                className={feeControlClass}
                {...feeForm.register('fee_name')}
              />
            </FeeField>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <FeeField label="Đơn vị phí">
                <select {...feeForm.register('unit')} className={feeControlClass}>
                  {FEE_BILLING_UNITS.map((u) => (
                    <option key={u} value={u}>
                      {FEE_BILLING_UNIT_LABELS[u]}
                    </option>
                  ))}
                </select>
              </FeeField>
              <FeeField
                label={
                  FEE_BILLING_UNIT_AMOUNT_LABELS[
                    normalizeFeeBillingUnit(
                      feeUnit,
                    ) as keyof typeof FEE_BILLING_UNIT_AMOUNT_LABELS
                  ]
                }
                error={feeForm.formState.errors.base_fee?.message}
              >
                <input
                  type="number"
                  disabled={feeUnit === 'none'}
                  className={feeMonoControlClass}
                  {...feeForm.register('base_fee', { valueAsNumber: true })}
                />
              </FeeField>
            </div>
          </FeeSection>

          <FeeSection title="Giới hạn & phạt">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <FeeField label="Số lượng">
                <input
                  type="number"
                  min={1}
                  placeholder="∞"
                  title="Để trống = không giới hạn"
                  className={feeMonoControlClass}
                  {...feeForm.register('berth_limit_count', { valueAsNumber: true })}
                />
              </FeeField>
              <FeeField label="Đơn vị">
                <select {...feeForm.register('berth_limit_unit')} className={feeControlClass}>
                  <option value="">—</option>
                  <option value="day">Ngày</option>
                  <option value="month">Tháng</option>
                </select>
              </FeeField>
              <FeeField label="Phạt vượt (₫)">
                <input
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="0"
                  className={feeMonoControlClass}
                  {...feeForm.register('over_limit_penalty_amount', { valueAsNumber: true })}
                />
              </FeeField>
              <FeeField
                label="Phạt ngoài giờ (₫)"
                error={feeForm.formState.errors.outside_hours_penalty_amount?.message}
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="0"
                  className={feeMonoControlClass}
                  {...feeForm.register('outside_hours_penalty_amount', {
                    valueAsNumber: true,
                  })}
                />
              </FeeField>
            </div>
            {(feeForm.formState.errors.berth_limit_count ||
              feeForm.formState.errors.berth_limit_unit ||
              feeForm.formState.errors.over_limit_penalty_amount) && (
              <p className={feeErrorClass}>
                {feeForm.formState.errors.berth_limit_count?.message ||
                  feeForm.formState.errors.berth_limit_unit?.message ||
                  feeForm.formState.errors.over_limit_penalty_amount?.message}
              </p>
            )}
          </FeeSection>

          <FeeSection title="Giới hạn thời gian mỗi lần neo">
            <div className="grid grid-cols-2 gap-3">
              <FeeField label="Thời gian tối đa (phút)">
                <input
                  type="number"
                  min={1}
                  placeholder="∞"
                  title="Để trống = không giới hạn thời gian mỗi lần neo"
                  className={feeMonoControlClass}
                  {...feeForm.register('max_berth_duration_minutes', { valueAsNumber: true })}
                />
              </FeeField>
              <FeeField
                label="Phạt vượt thời gian (₫)"
                error={feeForm.formState.errors.over_duration_penalty_amount?.message}
              >
                <input
                  type="number"
                  min={0}
                  step={1000}
                  placeholder="0"
                  className={feeMonoControlClass}
                  {...feeForm.register('over_duration_penalty_amount', { valueAsNumber: true })}
                />
              </FeeField>
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-400 mt-1 leading-snug">
              Áp cho mỗi lượt neo: nếu thời gian một lần neo (berth-in → berth-out) vượt số phút
              cho phép, hóa đơn tự cộng khoản phạt này.
            </p>
          </FeeSection>

          <FeeSection title="Giờ neo đậu">
            <FeeOperatingHoursEditor
              value={(feeForm.watch('operating_hours') ?? {}) as OperatingHours}
              onChange={(next) =>
                feeForm.setValue('operating_hours', next, { shouldValidate: true })
              }
              disabled={isSaving}
            />
          </FeeSection>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-gray-200 pt-3 dark:border-white/10">
            <label className="flex cursor-pointer items-center gap-2">
              <input
                type="checkbox"
                {...feeForm.register('is_active')}
                className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
              />
              <span className="text-[10px] font-bold uppercase tracking-widest text-gray-600 dark:text-gray-300">
                Đang áp dụng
              </span>
            </label>
            <div className="flex gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={closeForm}
                className="min-w-[5rem]"
              >
                Hủy
              </Button>
              {/* type=button: gọi handleSubmit thủ công để KHÔNG submit form tàu bao ngoài */}
              <Button
                type="button"
                disabled={isSaving}
                onClick={() => void feeForm.handleSubmit(onSubmit)()}
                className="min-w-[5rem] bg-blue-600 text-white hover:bg-blue-700"
              >
                {isSaving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : editingFeeId != null ? (
                  'Cập Nhật'
                ) : (
                  'Thêm Mới'
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
