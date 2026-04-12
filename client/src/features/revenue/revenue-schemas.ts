import { z } from 'zod';
import { FEE_BILLING_UNITS } from '../../utils/fee-billing-unit';

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

export const feeSchema = z.object({
  fee_name: z.string().min(1, 'Tên phí là bắt buộc'),
  vessel_type_id: z.string().optional(),
  unit: feeUnitEnum,
  base_fee: z.number().min(0, 'Mức phí không được âm'),
  is_active: z.boolean(),
});

export type FeeFormValues = z.infer<typeof feeSchema>;
