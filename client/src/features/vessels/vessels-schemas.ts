import { z } from 'zod';

export const vesselSchema = z.object({
  ship_id: z.string().min(1, 'Mã tàu là bắt buộc'),
  name: z.string().min(1, 'Tên tàu là bắt buộc'),
  vessel_type_id: z.string().min(1, 'Loại tàu là bắt buộc'),
  owner_info: z.string().optional(),
  is_active: z.boolean(),
});

export const vesselTypeSchema = z.object({
  type_name: z.string().min(1, 'Tên loại tàu là bắt buộc'),
  description: z.string().optional(),
});
