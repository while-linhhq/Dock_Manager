import React, { useEffect, useMemo, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useUserStore } from '../store/userStore';
import type { RoleCreate } from '../services/usersApi';
import type { RoleRead, UserRead } from '../../../types/api.types';
import { matchesAnyField } from '../../../utils/table-filters';
import { roleSchema, userSchema, type UserFormValues } from '../users-schemas';
import { UsersMainTabs, type UsersMainTab } from '../components/UsersMainTabs';
import { UsersListSection } from '../components/UsersListSection';
import { RolesSection } from '../components/RolesSection';
import { UsersModals } from '../components/UsersModals';
import { useAuthStore } from '../../auth/store/authStore';

export const UsersView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<UsersMainTab>('users');
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [userQ, setUserQ] = useState('');
  const [userRoleId, setUserRoleId] = useState('');
  const [userActive, setUserActiveFilter] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleQ, setRoleQ] = useState('');

  const { user: authUser } = useAuthStore();
  const {
    users,
    roles,
    isLoading,
    fetchUsers,
    fetchRoles,
    upsertUser,
    upsertRole,
    deleteRole,
    deleteUser,
    setUserActive,
  } = useUserStore();

  const userForm = useForm<UserFormValues>({
    resolver: zodResolver(userSchema),
    defaultValues: { is_active: true, username: '' },
  });

  const roleForm = useForm<RoleCreate>({
    resolver: zodResolver(roleSchema),
    defaultValues: {
      permissions: {
        menus: [],
      },
    },
  });

  useEffect(() => {
    if (activeTab === 'users') {
      fetchUsers();
      fetchRoles();
    } else {
      fetchRoles();
    }
  }, [activeTab, fetchUsers, fetchRoles]);

  const filteredUsers = useMemo(() => {
    return users.filter((u) => {
      if (
        !matchesAnyField(userQ, u.full_name, u.email, u.role?.name, u.role?.role_name, u.role_id)
      ) {
        return false;
      }
      if (userRoleId && String(u.role_id) !== userRoleId) {
        return false;
      }
      if (userActive === 'active' && !u.is_active) {
        return false;
      }
      if (userActive === 'inactive' && u.is_active) {
        return false;
      }
      return true;
    });
  }, [users, userQ, userRoleId, userActive]);

  const filteredRoles = useMemo(() => {
    return roles.filter((r) =>
      matchesAnyField(roleQ, r.role_name, r.name, r.description),
    );
  }, [roles, roleQ]);

  const userFilterCount =
    (userQ.trim() ? 1 : 0) + (userRoleId ? 1 : 0) + (userActive !== 'all' ? 1 : 0);

  const resetUserFilters = () => {
    setUserQ('');
    setUserRoleId('');
    setUserActiveFilter('all');
  };

  const onUserSubmit = async (data: UserFormValues) => {
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
      const normalized: RoleCreate = {
        role_name: data.role_name,
        description: data.description,
        permissions: {
          all: data.permissions?.all === true,
          menus: data.permissions?.all ? [] : data.permissions?.menus ?? [],
        },
      };
      await upsertRole(editingId, normalized);
      setIsRoleModalOpen(false);
      roleForm.reset();
      setEditingId(null);
    } catch (err) {
      console.error(err);
    }
  };

  const handleEditUser = (user: UserRead) => {
    setEditingId(user.id);
    userForm.reset({
      email: user.email,
      full_name: user.full_name,
      role_id: user.role_id,
      is_active: user.is_active,
    });
    setIsUserModalOpen(true);
  };

  const handleEditRole = (role: RoleRead) => {
    setEditingId(role.id);
    roleForm.reset({
      role_name: role.role_name || role.name || '',
      description: role.description,
      permissions: {
        all: Boolean((role.permissions as Record<string, unknown> | undefined)?.all === true),
        menus: Array.isArray((role.permissions as Record<string, unknown> | undefined)?.menus)
          ? ((role.permissions as Record<string, unknown>).menus as string[])
          : [],
      },
    });
    setIsRoleModalOpen(true);
  };

  const handleDeleteRole = async (id: string) => {
    if (!window.confirm('Xác nhận xóa vai trò này?')) {
      return;
    }
    await deleteRole(id);
  };

  const handleLockUser = async (u: UserRead) => {
    if (
      !window.confirm(
        `Tạm khóa "${u.full_name}"? Họ sẽ không đăng nhập được cho đến khi mở khóa.`,
      )
    ) {
      return;
    }
    try {
      await setUserActive(String(u.id), false);
    } catch {
      /* store error */
    }
  };

  const handleUnlockUser = async (u: UserRead) => {
    if (!window.confirm(`Mở khóa "${u.full_name}" và cho phép đăng nhập lại?`)) {
      return;
    }
    try {
      await setUserActive(String(u.id), true);
    } catch {
      /* store error */
    }
  };

  const handleDeleteUser = async (u: UserRead) => {
    if (
      !window.confirm(
        `XÓA VĨNH VIỄN "${u.full_name}" khỏi cơ sở dữ liệu? Hành động không hoàn tác. Dữ liệu tham chiếu (đơn, log…) sẽ giữ user_id = null nếu schema cho phép.`,
      )
    ) {
      return;
    }
    try {
      await deleteUser(String(u.id));
    } catch {
      /* store error */
    }
  };

  return (
    <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <UsersMainTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'users' ? (
        <UsersListSection
          userQ={userQ}
          setUserQ={setUserQ}
          userRoleId={userRoleId}
          setUserRoleId={setUserRoleId}
          userActive={userActive}
          setUserActive={setUserActiveFilter}
          resetUserFilters={resetUserFilters}
          userFilterCount={userFilterCount}
          onOpenAddUser={() => {
            setEditingId(null);
            userForm.reset({ is_active: true, username: '' });
            setIsUserModalOpen(true);
          }}
          roles={roles}
          users={users}
          filteredUsers={filteredUsers}
          isLoading={isLoading}
          onEditUser={handleEditUser}
          onLockUser={handleLockUser}
          onUnlockUser={handleUnlockUser}
          onDeleteUser={handleDeleteUser}
          currentUserId={authUser?.id ?? null}
        />
      ) : (
        <RolesSection
          roleQ={roleQ}
          setRoleQ={setRoleQ}
          resetRoleFilters={() => setRoleQ('')}
          roleFilterCount={roleQ.trim() ? 1 : 0}
          onOpenAddRole={() => {
            setEditingId(null);
            roleForm.reset({ role_name: '', description: '', permissions: { menus: [] } });
            setIsRoleModalOpen(true);
          }}
          roles={roles}
          filteredRoles={filteredRoles}
          onEditRole={handleEditRole}
          onDeleteRole={handleDeleteRole}
        />
      )}

      <UsersModals
        isUserModalOpen={isUserModalOpen}
        onCloseUser={() => setIsUserModalOpen(false)}
        userForm={userForm}
        onUserSubmit={onUserSubmit}
        editingId={editingId}
        roles={roles}
        isLoading={isLoading}
        isRoleModalOpen={isRoleModalOpen}
        onCloseRole={() => setIsRoleModalOpen(false)}
        roleForm={roleForm}
        onRoleSubmit={onRoleSubmit}
      />
    </div>
  );
};
