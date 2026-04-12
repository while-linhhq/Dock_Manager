import React from 'react';
import { CheckCircle2, Loader2, MoreVertical, UserPlus, XCircle } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import { cn } from '../../../utils/cn';
import { dt } from '../../../utils/data-table-classes';
import type { RoleRead, UserRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type UsersListSectionProps = {
  userQ: string;
  setUserQ: (v: string) => void;
  userRoleId: string;
  setUserRoleId: (v: string) => void;
  userActive: 'all' | 'active' | 'inactive';
  setUserActive: (v: 'all' | 'active' | 'inactive') => void;
  resetUserFilters: () => void;
  userFilterCount: number;
  onOpenAddUser: () => void;
  roles: RoleRead[];
  users: UserRead[];
  filteredUsers: UserRead[];
  isLoading: boolean;
  onEditUser: (u: UserRead) => void;
};

export const UsersListSection: React.FC<UsersListSectionProps> = ({
  userQ,
  setUserQ,
  userRoleId,
  setUserRoleId,
  userActive,
  setUserActive,
  resetUserFilters,
  userFilterCount,
  onOpenAddUser,
  roles,
  users,
  filteredUsers,
  isLoading,
  onEditUser,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel onReset={resetUserFilters} activeCount={userFilterCount}>
        <FilterField label="Từ khóa (họ tên / email / vai trò)">
          <input
            type="text"
            value={userQ}
            onChange={(e) => setUserQ(e.target.value)}
            placeholder="Lọc nhanh..."
            className={filterControlClass}
          />
        </FilterField>
        <FilterField label="Vai trò">
          <select
            value={userRoleId}
            onChange={(e) => setUserRoleId(e.target.value)}
            className={filterControlClass}
          >
            <option value="">Tất cả</option>
            {roles.map((r) => (
              <option key={r.id} value={String(r.id)}>
                {r.role_name || r.name}
              </option>
            ))}
          </select>
        </FilterField>
        <FilterField label="Trạng thái">
          <select
            value={userActive}
            onChange={(e) => setUserActive(e.target.value as 'all' | 'active' | 'inactive')}
            className={filterControlClass}
          >
            <option value="all">Tất cả</option>
            <option value="active">Đang hoạt động</option>
            <option value="inactive">Đã vô hiệu</option>
          </select>
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-end">
        <Button
          type="button"
          onClick={onOpenAddUser}
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
              <tr className={dt.headRow}>
                <th className={dt.pad}>Họ Tên</th>
                <th className={dt.pad}>Email</th>
                <th className={dt.pad}>Vai Trò</th>
                <th className={dt.pad}>Trạng Thái</th>
                <th className={cn(dt.pad, 'text-right')}>Thao Tác</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100 dark:divide-white/5">
              {isLoading && users.length === 0 ? (
                <tr>
                  <td colSpan={5} className={cn(dt.pad, 'py-12 text-center')}>
                    <Loader2 className="w-8 h-8 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : filteredUsers.length > 0 ? (
                filteredUsers.map((u) => (
                  <tr
                    key={u.id}
                    className="hover:bg-gray-50 dark:hover:bg-white/[0.02] transition-colors group"
                  >
                    <td className={dt.pad}>
                      <div className="flex items-center space-x-3">
                        <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-blue-500/20 to-cyan-500/20 flex items-center justify-center text-blue-500 font-bold text-sm">
                          {(u.full_name || '?').charAt(0)}
                        </div>
                        <span className={cn(dt.body, 'font-bold uppercase')}>{u.full_name}</span>
                      </div>
                    </td>
                    <td className={cn(dt.pad, dt.mono, 'text-gray-500 dark:text-gray-400')}>
                      {u.email}
                    </td>
                    <td className={dt.pad}>
                      <span
                        className={cn(
                          'px-2.5 py-1 bg-blue-500/10 text-blue-600 dark:text-blue-400 rounded border border-blue-500/20',
                          dt.badge,
                        )}
                      >
                        {u.role?.name || 'N/A'}
                      </span>
                    </td>
                    <td className={dt.pad}>
                      <span
                        className={cn(
                          'inline-flex items-center px-2.5 py-1 rounded-full border',
                          dt.badge,
                          u.is_active
                            ? 'text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
                            : 'text-red-600 dark:text-red-400 bg-red-500/10 border-red-500/20',
                        )}
                      >
                        {u.is_active ? (
                          <CheckCircle2 className="w-3.5 h-3.5 mr-1 shrink-0" />
                        ) : (
                          <XCircle className="w-3.5 h-3.5 mr-1 shrink-0" />
                        )}
                        {u.is_active ? 'Hoạt Động' : 'Tạm Khóa'}
                      </span>
                    </td>
                    <td className={cn(dt.pad, 'text-right')}>
                      <button
                        type="button"
                        onClick={() => onEditUser(u)}
                        className="p-2 text-gray-400 hover:text-blue-500 transition-all"
                      >
                        <MoreVertical className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td
                    colSpan={5}
                    className={cn(
                      dt.pad,
                      'py-12 text-center font-mono uppercase tracking-wide',
                      dt.empty,
                    )}
                  >
                    {users.length === 0
                      ? 'Không có dữ liệu người dùng'
                      : 'Không có người dùng khớp bộ lọc'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
