import React from 'react';
import type { UseFormReturn } from 'react-hook-form';
import { Loader2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import type { RoleRead } from '../../../types/api.types';
import type { RoleCreate } from '../services/usersApi';
import type { UserFormValues } from '../users-schemas';

export type UsersModalsProps = {
  isUserModalOpen: boolean;
  onCloseUser: () => void;
  userForm: UseFormReturn<UserFormValues>;
  onUserSubmit: (data: UserFormValues) => void | Promise<void>;
  editingId: string | null;
  roles: RoleRead[];
  isLoading: boolean;
  isRoleModalOpen: boolean;
  onCloseRole: () => void;
  roleForm: UseFormReturn<RoleCreate>;
  onRoleSubmit: (data: RoleCreate) => void | Promise<void>;
};

export const UsersModals: React.FC<UsersModalsProps> = ({
  isUserModalOpen,
  onCloseUser,
  userForm,
  onUserSubmit,
  editingId,
  roles,
  isLoading,
  isRoleModalOpen,
  onCloseRole,
  roleForm,
  onRoleSubmit,
}) => {
  return (
    <>
      <Modal
        isOpen={isUserModalOpen}
        onClose={onCloseUser}
        title={editingId ? 'Chỉnh Sửa Người Dùng' : 'Thêm Người Dùng Mới'}
      >
        <form onSubmit={userForm.handleSubmit(onUserSubmit)} className="space-y-4">
          <Input
            label="Họ Tên"
            placeholder="VD: Nguyễn Văn A"
            {...userForm.register('full_name')}
            error={userForm.formState.errors.full_name?.message}
          />
          <Input
            label="Email"
            type="email"
            placeholder="VD: user@bason.port"
            {...userForm.register('email')}
            error={userForm.formState.errors.email?.message}
          />
          {!editingId && (
            <Input
              label="Mật Khẩu"
              type="password"
              placeholder="••••••••"
              {...userForm.register('password')}
              error={userForm.formState.errors.password?.message}
            />
          )}
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Vai Trò
            </label>
            <select
              {...userForm.register('role_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn vai trò...</option>
              {roles.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center space-x-2 ml-1">
            <input
              type="checkbox"
              id="user_is_active"
              {...userForm.register('is_active')}
              className="w-4 h-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            />
            <label
              htmlFor="user_is_active"
              className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest"
            >
              Kích Hoạt Tài Khoản
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseUser} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : editingId ? (
                'Cập Nhật'
              ) : (
                'Thêm Mới'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        isOpen={isRoleModalOpen}
        onClose={onCloseRole}
        title={editingId ? 'Chỉnh Sửa Vai Trò' : 'Thêm Vai Trò Mới'}
      >
        <form onSubmit={roleForm.handleSubmit(onRoleSubmit)} className="space-y-4">
          <Input
            label="Tên Vai Trò"
            placeholder="VD: Quản Lý"
            {...roleForm.register('role_name')}
            error={roleForm.formState.errors.role_name?.message}
          />
          <div className="space-y-1">
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">
              Mô Tả
            </label>
            <textarea
              {...roleForm.register('description')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all min-h-[100px]"
              placeholder="Nhập mô tả vai trò..."
            />
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={onCloseRole} className="flex-1">
              Hủy
            </Button>
            <Button
              type="submit"
              disabled={isLoading}
              className="flex-1 bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isLoading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : editingId ? (
                'Cập Nhật'
              ) : (
                'Thêm Mới'
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
};
