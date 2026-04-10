import React, { useEffect, useState } from 'react';
import { 
  Users, 
  UserPlus, 
  Shield, 
  Search, 
  MoreVertical, 
  CheckCircle2, 
  XCircle,
  Loader2,
  Plus,
  Trash2,
} from 'lucide-react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '../../../components/Button/Button';
import { Input } from '../../../components/Input/Input';
import { Modal } from '../../../components/Modal/Modal';
import { cn } from '../../../utils/cn';
import { useUserStore } from '../store/userStore';
import type { RoleCreate } from '../services/usersApi';

const userSchema = z.object({
  email: z.string().email('Email không hợp lệ'),
  password: z.string().min(6, 'Mật khẩu ít nhất 6 ký tự').optional(),
  full_name: z.string().min(1, 'Họ tên là bắt buộc'),
  role_id: z.string().min(1, 'Vai trò là bắt buộc'),
  is_active: z.boolean().default(true),
});

const roleSchema = z.object({
  role_name: z.string().min(1, 'Tên vai trò là bắt buộc'),
  description: z.string().optional(),
});

export const UsersView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'users' | 'roles'>('users');
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  const { 
    users, roles, isLoading, 
    fetchUsers, fetchRoles, 
    upsertUser, upsertRole, deleteRole 
  } = useUserStore();

  const userForm = useForm<z.infer<typeof userSchema>>({
    resolver: zodResolver(userSchema),
    defaultValues: { is_active: true }
  });

  const roleForm = useForm<RoleCreate>({
    resolver: zodResolver(roleSchema)
  });

  useEffect(() => {
    if (activeTab === 'users') {
      fetchUsers();
      fetchRoles();
    } else {
      fetchRoles();
    }
  }, [activeTab, fetchUsers, fetchRoles]);

  const onUserSubmit = async (data: any) => {
    try {
      await upsertUser(editingId, data);
      setIsUserModalOpen(false);
      userForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const onRoleSubmit = async (data: RoleCreate) => {
    try {
      await upsertRole(editingId, data);
      setIsRoleModalOpen(false);
      roleForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditUser = (user: any) => {
    setEditingId(user.id);
    userForm.reset({
      email: user.email,
      full_name: user.full_name,
      role_id: user.role_id,
      is_active: user.is_active,
    });
    setIsUserModalOpen(true);
  };

  const handleEditRole = (role: any) => {
    setEditingId(role.id);
    roleForm.reset({
      role_name: role.role_name || role.name,
      description: role.description,
    });
    setIsRoleModalOpen(true);
  };

  const handleDeleteRole = async (id: string) => {
    if (!window.confirm('Xác nhận xóa vai trò này?')) {
      return;
    }
    await deleteRole(id);
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      {/* Tabs */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-white/5 p-1 rounded-xl w-fit">
        <button
          onClick={() => setActiveTab('users')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'users' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Users className="w-4 h-4" />
          <span>Người Dùng</span>
        </button>
        <button
          onClick={() => setActiveTab('roles')}
          className={cn(
            "px-6 py-2 rounded-lg text-xs font-bold uppercase tracking-widest transition-all flex items-center space-x-2",
            activeTab === 'roles' 
              ? "bg-white dark:bg-blue-600 text-blue-600 dark:text-white shadow-sm" 
              : "text-gray-500 hover:text-gray-900 dark:hover:text-white"
          )}
        >
          <Shield className="w-4 h-4" />
          <span>Vai Trò</span>
        </button>
      </div>

      {activeTab === 'users' ? (
        <div className="space-y-6">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="relative flex-1 max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-500" />
              <input 
                type="text" 
                placeholder="Tìm tên, email..." 
                className="w-full pl-10 pr-4 py-2 bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white"
              />
            </div>
            <Button 
              onClick={() => {
                setEditingId(null);
                userForm.reset({ is_active: true });
                setIsUserModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <UserPlus className="w-4 h-4 mr-2" />
              Thêm Người Dùng
            </Button>
          </div>

          <div className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 rounded-2xl shadow-2xl overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="text-[10px] font-bold text-gray-500 uppercase tracking-[0.2em] border-b border-gray-200 dark:border-white/5 bg-gray-50 dark:bg-white/[0.01]">
                    <th className="px-6 py-4">Họ Tên</th>
                    <th className="px-6 py-4">Email</th>
                    <th className="px-6 py-4">Vai Trò</th>
                    <th className="px-6 py-4">Trạng Thái</th>
                    <th className="px-6 py-4 text-right">Thao Tác</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-white/5">
                  {isLoading && users.length === 0 ? (
                    <tr><td colSpan={5} className="px-6 py-12 text-center"><Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" /></td></tr>
                  ) : users.length > 0 ? (
                    users.map((u) => (
                      <tr key={u.id} className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors group">
                        <td className="px-6 py-4">
                          <div className="flex items-center space-x-3">
                            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-blue-500/20 to-cyan-500/20 flex items-center justify-center text-blue-500 font-bold text-xs">
                              {u.full_name.charAt(0)}
                            </div>
                            <span className="text-xs font-bold text-gray-900 dark:text-white uppercase">{u.full_name}</span>
                          </div>
                        </td>
                        <td className="px-6 py-4 text-xs font-mono text-gray-500">{u.email}</td>
                        <td className="px-6 py-4">
                          <span className="px-2 py-1 bg-blue-500/10 text-blue-500 rounded text-[9px] font-bold uppercase tracking-widest border border-blue-500/20">
                            {u.role?.name || 'N/A'}
                          </span>
                        </td>
                        <td className="px-6 py-4">
                          <span className={cn(
                            "inline-flex items-center px-2.5 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest border",
                            u.is_active ? "text-emerald-500 bg-emerald-500/10 border-emerald-500/20" : "text-red-500 bg-red-500/10 border-red-500/20"
                          )}>
                            {u.is_active ? <CheckCircle2 className="w-3 h-3 mr-1" /> : <XCircle className="w-3 h-3 mr-1" />}
                            {u.is_active ? 'Hoạt Động' : 'Tạm Khóa'}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button 
                            onClick={() => handleEditUser(u)}
                            className="p-2 text-gray-400 hover:text-blue-500 transition-all"
                          >
                            <MoreVertical className="w-4 h-4" />
                          </button>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr><td colSpan={5} className="px-6 py-12 text-center text-gray-500 text-xs uppercase font-mono">Không có dữ liệu người dùng</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : (
        <div className="space-y-6">
          <div className="flex justify-between items-center">
            <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">Danh Mục Vai Trò</h3>
            <Button 
              onClick={() => {
                setEditingId(null);
                roleForm.reset({ role_name: '', description: '' });
                setIsRoleModalOpen(true);
              }}
              className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
            >
              <Plus className="w-4 h-4 mr-2" />
              Thêm Vai Trò
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {roles.map((role) => (
              <div key={role.id} className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4">
                <div className="p-3 bg-blue-600/10 rounded-xl w-fit">
                  <Shield className="w-6 h-6 text-blue-600" />
                </div>
                <div>
                  <h4 className="text-sm font-bold text-gray-900 dark:text-white uppercase">
                    {role.role_name || role.name}
                  </h4>
                  <p className="text-[10px] text-gray-500 uppercase tracking-widest mt-1">
                    {role.description || 'Không có mô tả'}
                  </p>
                </div>
                <div className="pt-4 border-t border-gray-100 dark:border-white/5 flex justify-end gap-3">
                  <button
                    onClick={() => handleEditRole(role)}
                    className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest"
                  >
                    Chỉnh Sửa
                  </button>
                  <button
                    onClick={() => handleDeleteRole(role.id)}
                    className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest inline-flex items-center gap-1"
                  >
                    <Trash2 className="w-3 h-3" />
                    Xóa
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* User Modal */}
      <Modal
        isOpen={isUserModalOpen}
        onClose={() => setIsUserModalOpen(false)}
        title={editingId ? "Chỉnh Sửa Người Dùng" : "Thêm Người Dùng Mới"}
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
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Vai Trò</label>
            <select
              {...userForm.register('role_id')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all"
            >
              <option value="">Chọn vai trò...</option>
              {roles.map(r => (
                <option key={r.id} value={r.id}>{r.name}</option>
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
            <label htmlFor="user_is_active" className="text-[10px] font-bold text-gray-700 dark:text-gray-300 uppercase tracking-widest">
              Kích Hoạt Tài Khoản
            </label>
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsUserModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? "Cập Nhật" : "Thêm Mới")}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Role Modal */}
      <Modal
        isOpen={isRoleModalOpen}
        onClose={() => setIsRoleModalOpen(false)}
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
            <label className="text-[10px] font-bold text-gray-500 uppercase tracking-widest ml-1">Mô Tả</label>
            <textarea
              {...roleForm.register('description')}
              className="w-full px-4 py-2 bg-gray-50 dark:bg-white/5 border border-gray-200 dark:border-white/10 rounded-xl focus:border-blue-500 focus:ring-0 text-sm font-mono dark:text-white transition-all min-h-[100px]"
              placeholder="Nhập mô tả vai trò..."
            />
          </div>
          <div className="pt-4 flex space-x-3">
            <Button type="button" variant="outline" onClick={() => setIsRoleModalOpen(false)} className="flex-1">Hủy</Button>
            <Button type="submit" disabled={isLoading} className="flex-1 bg-blue-600 hover:bg-blue-700 text-white">
              {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : (editingId ? 'Cập Nhật' : 'Thêm Mới')}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
