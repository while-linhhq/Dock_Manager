from fastapi import APIRouter
from app.api.v1.endpoints import (
    auth,
    users,
    roles,
    vessel_types,
    vessels,
    detections,
    orders,
    fee_configs,
    invoices,
    cameras,
    port_configs,
    port_logs,
    dashboard,
    exports,
    audit_logs,
    pipeline,
)


api_router = APIRouter()

api_router.include_router(auth.router,         prefix='/auth',          tags=['auth'])
api_router.include_router(users.router,        prefix='/users',         tags=['users'])
api_router.include_router(roles.router,        prefix='/roles',         tags=['roles'])
api_router.include_router(vessel_types.router, prefix='/vessel-types',  tags=['vessel-types'])
api_router.include_router(vessels.router,      prefix='/vessels',       tags=['vessels'])
api_router.include_router(detections.router,   prefix='/detections',    tags=['detections'])
api_router.include_router(orders.router,       prefix='/orders',        tags=['orders'])
api_router.include_router(fee_configs.router,  prefix='/fee-configs',   tags=['fee-configs'])
api_router.include_router(invoices.router,     prefix='/invoices',      tags=['invoices'])
api_router.include_router(cameras.router,      prefix='/cameras',       tags=['cameras'])
api_router.include_router(port_configs.router, prefix='/port-configs',  tags=['port-configs'])
api_router.include_router(port_logs.router,    prefix='/port-logs',     tags=['port-logs'])
api_router.include_router(dashboard.router,    prefix='/dashboard',     tags=['dashboard'])
api_router.include_router(exports.router,      prefix='/exports',       tags=['exports'])
api_router.include_router(audit_logs.router,   prefix='/audit-logs',    tags=['audit-logs'])
api_router.include_router(pipeline.router,     prefix='/pipeline',      tags=['pipeline'])
