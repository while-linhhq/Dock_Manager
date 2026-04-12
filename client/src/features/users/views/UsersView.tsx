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

export const UsersView: React.FC = () => {
  const [activeTab, setActiveTab] = useState<UsersMainTab>('users');
  const [isUserModalOpen, setIsUserModalOpen] = useState(false);
  const [isRoleModalOpen, setIsRoleModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [userQ, setUserQ] = useState('');
  const [userRoleId, setUserRoleId] = useState('');
  const [userActive, setUserActive] = useState<'all' | 'active' | 'inactive'>('all');
  const [roleQ, setRoleQ] = useState('');

  const { users, roles, isLoading, fetchUsers, fetchRoles, upsertUser, upsertRole, deleteRole } =
    useUserStore();

  const userForm = useForm<UserFormValues>({
    resolver: zodResolver(userSchema),
    defaultValues: { is_active: true },
  });

  const roleForm = useForm<RoleCreate>({
    resolver: zodResolver(roleSchema),
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
        !matchesAnyField(userQ, u.full_name, u.email, u.role?.name, u.role_id)
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
    setUserActive('all');
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
      await upsertRole(editingId, data);
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
      <UsersMainTabs activeTab={activeTab} onTabChange={setActiveTab} />

      {activeTab === 'users' ? (
        <UsersListSection
          userQ={userQ}
          setUserQ={setUserQ}
          userRoleId={userRoleId}
          setUserRoleId={setUserRoleId}
          userActive={userActive}
          setUserActive={setUserActive}
          resetUserFilters={resetUserFilters}
          userFilterCount={userFilterCount}
          onOpenAddUser={() => {
            setEditingId(null);
            userForm.reset({ is_active: true });
            setIsUserModalOpen(true);
          }}
          roles={roles}
          users={users}
          filteredUsers={filteredUsers}
          isLoading={isLoading}
          onEditUser={handleEditUser}
        />
      ) : (
        <RolesSection
          roleQ={roleQ}
          setRoleQ={setRoleQ}
          resetRoleFilters={() => setRoleQ('')}
          roleFilterCount={roleQ.trim() ? 1 : 0}
          onOpenAddRole={() => {
            setEditingId(null);
            roleForm.reset({ role_name: '', description: '' });
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
