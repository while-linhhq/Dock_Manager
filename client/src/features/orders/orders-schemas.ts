import { z } from 'zod';

export const orderSchema = z.object({
  vessel_id: z.string().min(1, 'Mã tàu là bắt buộc'),
  cargo_details: z.string().optional(),
  total_amount: z.number().min(0, 'Số tiền không được âm'),
  status: z.string().default('pending'),
});
