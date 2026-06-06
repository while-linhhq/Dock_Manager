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

const operatingHoursSchema = z.custom<OperatingHours>(
  (value) => value == null || typeof value === 'object',
  'Giờ neo đậu không hợp lệ',
).optional();

export const feeSchema = z
  .object({
    fee_name: z.string().min(1, 'Tên phí là bắt buộc'),
    vessel_type_id: z.string().optional(),
    unit: feeUnitEnum,
    base_fee: z.number().min(0, 'Mức phí không được âm'),
    is_active: z.boolean(),
    berth_limit_count: optionalBerthLimitCount,
    berth_limit_unit: optionalBerthLimitUnit,
    over_limit_penalty_amount: optionalPenaltyAmount,
    outside_hours_penalty_amount: optionalPenaltyAmount,
    operating_hours: operatingHoursSchema,
  })
  .superRefine((data, ctx) => {
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
  });

export type FeeFormValues = z.infer<typeof feeSchema>;
