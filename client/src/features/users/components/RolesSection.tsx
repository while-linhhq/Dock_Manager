import React from 'react';
import { Plus, Shield, Trash2 } from 'lucide-react';
import { Button } from '../../../components/Button/Button';
import type { RoleRead } from '../../../types/api.types';
import {
  FilterField,
  TableFilterPanel,
  filterControlClass,
} from '../../../components/TableFilterPanel/TableFilterPanel';

export type RolesSectionProps = {
  roleQ: string;
  setRoleQ: (v: string) => void;
  resetRoleFilters: () => void;
  roleFilterCount: number;
  onOpenAddRole: () => void;
  roles: RoleRead[];
  filteredRoles: RoleRead[];
  onEditRole: (role: RoleRead) => void;
  onDeleteRole: (id: string) => void;
};

export const RolesSection: React.FC<RolesSectionProps> = ({
  roleQ,
  setRoleQ,
  resetRoleFilters,
  roleFilterCount,
  onOpenAddRole,
  roles,
  filteredRoles,
  onEditRole,
  onDeleteRole,
}) => {
  return (
    <div className="space-y-6">
      <TableFilterPanel
        title="Bộ lọc vai trò"
        onReset={resetRoleFilters}
        activeCount={roleFilterCount}
      >
        <FilterField label="Tên / mô tả" className="sm:col-span-2 lg:col-span-2">
          <input
            type="text"
            value={roleQ}
            onChange={(e) => setRoleQ(e.target.value)}
            placeholder="Lọc vai trò..."
            className={filterControlClass}
          />
        </FilterField>
      </TableFilterPanel>

      <div className="flex justify-between items-center">
        <h3 className="text-sm font-bold text-gray-900 dark:text-white uppercase tracking-widest">
          Danh Mục Vai Trò
        </h3>
        <Button
          type="button"
          onClick={onOpenAddRole}
          className="bg-blue-600 hover:bg-blue-700 text-white shadow-lg shadow-blue-600/20"
        >
          <Plus className="w-4 h-4 mr-2" />
          Thêm Vai Trò
        </Button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredRoles.length > 0 ? (
          filteredRoles.map((role) => (
            <div
              key={role.id}
              className="bg-white dark:bg-[#121214] border border-gray-200 dark:border-white/5 p-6 rounded-2xl shadow-xl space-y-4"
            >
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
                  type="button"
                  onClick={() => onEditRole(role)}
                  className="text-[10px] font-bold text-gray-500 hover:text-blue-600 uppercase tracking-widest"
                >
                  Chỉnh Sửa
                </button>
                <button
                  type="button"
                  onClick={() => onDeleteRole(role.id)}
                  className="text-[10px] font-bold text-red-600 hover:text-red-500 uppercase tracking-widest inline-flex items-center gap-1"
                >
                  <Trash2 className="w-3 h-3" />
                  Xóa
                </button>
              </div>
            </div>
          ))
        ) : (
          <div className="col-span-full py-12 text-center text-gray-500 text-xs uppercase font-mono">
            {roles.length === 0 ? 'Chưa có vai trò' : 'Không có vai trò khớp bộ lọc'}
          </div>
        )}
      </div>
    </div>
  );
};
