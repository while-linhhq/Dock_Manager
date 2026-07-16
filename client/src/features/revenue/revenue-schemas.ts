import { z } from 'zod';
import { FEE_BILLING_UNITS } from '../../utils/fee-billing-unit';
import { hasEnforcedOperatingDay, type OperatingHours } from './types/fee-operating-hours';

export const invoiceSchema = z.object({
  order_id: z.string().min(1, 'Mã đơn hàng là bắt buộc'),
  items: z
    .array(
      z.object({
        description: z.string().min(1, 'Mô tả là bắt buộc'),
        quantity: z.number().min(1, 'Số lượng ít nhất là 1'),
        unit_price: z.number().min(0, 'Đơn giá không được âm'),
      }),
    )
    .min(1, 'Cần ít nhất một hạng mục'),
});

export const paymentSchema = z.object({
  amount: z.number().min(1, 'Số tiền thanh toán phải lớn hơn 0'),
  payment_method: z.string().min(1, 'Phương thức thanh toán là bắt buộc'),
  reference_number: z.string().optional(),
  notes: z.string().optional(),
});

const feeUnitEnum = z.enum(FEE_BILLING_UNITS);

const berthLimitUnitEnum = z.enum(['day', 'month']);

const optionalBerthLimitCount = z.preprocess((value) => {
  if (value === '' || value == null) {
    return undefined;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}, z.number().int().min(1).optional());

const optionalBerthLimitUnit = z.preprocess((value) => {
  if (value === '' || value == null) {
    return undefined;
  }
  return value;
}, berthLimitUnitEnum.optional());

const optionalPenaltyAmount = z.preprocess((value) => {
  if (value === '' || value == null) {
    return undefined;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}, z.number().min(0).optional());

const optionalDurationMinutes = z.preprocess((value) => {
  if (value === '' || value == null) {
    return undefined;
  }
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}, z.number().int().min(1).optional());

const operatingHoursSchema = z.custom<OperatingHours>(
  (value) => value == null || typeof value === 'object',
  'Giờ neo đậu không hợp lệ',
).optional();

// Shape gốc — cả hai ngữ cảnh phí dùng chung. Cả vessel_id lẫn vessel_type_id
// đều optional ở đây; requiredness enforce riêng theo ngữ cảnh (xem 2 schema bên dưới).
const feeBaseShape = {
  fee_name: z.string().min(1, 'Tên phí là bắt buộc'),
  // Doanh Thu › Cấu Hình Phí gắn theo LOẠI TÀU (áp cho tàu tháng cùng loại).
  vessel_type_id: z.string().optional(),
  // Tab Tàu Lẻ gắn phí theo từng MÃ TÀU (vessel_id được panel inject sẵn).
  vessel_id: z.string().optional(),
  unit: feeUnitEnum,
  base_fee: z.number().min(0, 'Mức phí không được âm'),
  is_active: z.boolean(),
  berth_limit_count: optionalBerthLimitCount,
  berth_limit_unit: optionalBerthLimitUnit,
  over_limit_penalty_amount: optionalPenaltyAmount,
  outside_hours_penalty_amount: optionalPenaltyAmount,
  // Phạt neo ngoài giờ TÍNH THEO GIỜ (₫/giờ) — chỉ áp cho tàu tháng.
  outside_hours_penalty_per_hour: optionalPenaltyAmount,
  // Giới hạn thời gian cho MỘT lần neo đậu (phút) + phí phạt khi vượt.
  max_berth_duration_minutes: optionalDurationMinutes,
  over_duration_penalty_amount: optionalPenaltyAmount,
  operating_hours: operatingHoursSchema,
} as const;

const feeObject = z.object(feeBaseShape);
type FeeObjectValues = z.infer<typeof feeObject>;

// Ràng buộc chung về giới hạn neo đậu + phạt — áp cho cả 2 schema.
function applyFeeRefinements<T extends z.ZodObject<z.ZodRawShape>>(schema: T) {
  return schema.superRefine((rawData, ctx) => {
    const data = rawData as FeeObjectValues;
    const count = Number.isFinite(data.berth_limit_count) ? data.berth_limit_count : undefined;
    const unit = data.berth_limit_unit;
    if (count != null && !unit) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Chọn đơn vị giới hạn (ngày hoặc tháng)',
        path: ['berth_limit_unit'],
      });
    }
    if (unit && count == null) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Nhập số lượng giới hạn neo đậu',
        path: ['berth_limit_count'],
      });
    }
    const overPenalty = data.over_limit_penalty_amount ?? 0;
    if (overPenalty > 0 && !(count != null && count > 0 && unit)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Phí phạt vượt giới hạn cần cấu hình giới hạn neo đậu',
        path: ['over_limit_penalty_amount'],
      });
    }
    const outsidePenalty = data.outside_hours_penalty_amount ?? 0;
    const hours = (data.operating_hours ?? {}) as OperatingHours;
    if (outsidePenalty > 0 && !hasEnforcedOperatingDay(hours)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Phí phạt ngoài giờ cần cấu hình giờ neo ít nhất một ngày',
        path: ['outside_hours_penalty_amount'],
      });
    }
    const outsidePerHour = data.outside_hours_penalty_per_hour ?? 0;
    if (outsidePerHour > 0 && !hasEnforcedOperatingDay(hours)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Phí phạt ngoài giờ theo giờ cần cấu hình giờ neo ít nhất một ngày',
        path: ['outside_hours_penalty_per_hour'],
      });
    }
    const durationMinutes = Number.isFinite(data.max_berth_duration_minutes)
      ? data.max_berth_duration_minutes
      : undefined;
    const overDurationPenalty = data.over_duration_penalty_amount ?? 0;
    if (overDurationPenalty > 0 && !(durationMinutes != null && durationMinutes > 0)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: 'Phí phạt vượt thời gian cần cấu hình giới hạn thời gian neo (phút)',
        path: ['over_duration_penalty_amount'],
      });
    }
  });
}

// Schema mặc định (permissive scope) — dùng cho tab Tàu Lẻ (VesselFeeConfigsPanel),
// nơi vessel_id được inject tự động nên không cần validate scope.
export const feeSchema = applyFeeRefinements(feeObject);

// Schema cho Doanh Thu › Cấu Hình Phí (tàu tháng): bắt buộc chọn LOẠI TÀU.
export const feeSchemaByType = applyFeeRefinements(
  z.object({
    ...feeBaseShape,
    vessel_type_id: z.string().min(1, 'Chọn loại tàu áp dụng phí'),
  }),
);

export type FeeFormInput = z.input<typeof feeSchema>;
export type FeeFormValues = z.output<typeof feeSchema>;
export type MonthlyFeeFormInput = z.input<typeof feeSchemaByType>;
export type MonthlyFeeFormValues = z.output<typeof feeSchemaByType>;
