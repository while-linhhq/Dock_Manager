from typing import Any, Optional


def _permission_object(user) -> dict[str, Any]:
    role = getattr(user, 'role', None)
    raw = getattr(role, 'permissions', None) if role is not None else None
    if not raw or not isinstance(raw, dict):
        return {}
    return raw


def is_admin_user(user) -> bool:
    username = str(getattr(user, 'username', '') or '').strip().lower()
    if username == 'admin':
        return True
    role = getattr(user, 'role', None)
    role_name = str(getattr(role, 'role_name', '') or getattr(role, 'name', '') or '').strip().lower()
    if role_name == 'admin':
        return True
    perms = _permission_object(user)
    return perms.get('all') is True


def _normalized_menu_set(perms: dict[str, Any]) -> set[str]:
    menus = perms.get('menus') or perms.get('allowed_menus') or []
    if not isinstance(menus, list):
        return set()
    return {str(item).strip().lower() for item in menus if str(item).strip()}


def has_menu_access(user, menu_key: str) -> bool:
    if user is None:
        return False
    if is_admin_user(user):
        return True
    perms = _permission_object(user)
    aliases = {
        'discount_approval': ['discount_approval', 'discount-approval', 'discount'],
        'revenue': ['revenue', 'billing', 'invoices'],
    }.get(menu_key, [menu_key])
    allowed = _normalized_menu_set(perms)
    if allowed:
        return any(alias in allowed for alias in aliases)
    menu_access = perms.get('menu_access')
    if isinstance(menu_access, dict):
        return any(menu_access.get(alias) is True for alias in aliases)
    return any(perms.get(alias) is True for alias in aliases)


def can_approve_discount(user) -> bool:
    return has_menu_access(user, 'discount_approval')
