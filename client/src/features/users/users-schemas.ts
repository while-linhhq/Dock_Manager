import { z } from 'zod';

export const userSchema = z.object({
  username: z.string().min(3, 'Username ít nhất 3 ký tự').optional(),
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(6, 'Mật khẩu ít nhất 6 ký tự').optional(),
  full_name: z.string().min(1, 'Họ tên là bắt buộc'),
  role_id: z.string().min(1, 'Vai trò là bắt buộc'),
  is_active: z.boolean().default(true),
});

export const roleSchema = z.object({
  role_name: z.string().min(1, 'Tên vai trò là bắt buộc'),
  description: z.string().optional(),
  permissions: z
    .object({
      all: z.boolean().optional(),
      menus: z.array(z.string()).optional(),
    })
    .optional(),
});

export type UserFormValues = z.infer<typeof userSchema>;
