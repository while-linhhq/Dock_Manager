/**
 * API regression (không gọi pipeline): mỗi nhóm tạo 3 bản ghi, 1 DELETE, còn lại GET/PUT/PATCH...
 *
 * Chạy nhanh (Node 18+): node mcp_run_all.cjs
 * Chrome DevTools MCP: navigate tới http://127.0.0.1:8080/docs rồi evaluate_script
 *   async () => { ...copy toàn bộ thân file từ dòng sau (async () => { đến return...); }
 * Hoặc dán IIFE này vào Console trên tab /docs.
 *
 * Part 1: list batch + roles, vessel-types, vessels, orders, fee-configs
 */
/* eslint-disable */
(async () => {
  const base = 'http://127.0.0.1:8080/api/v1';
  const steps = [];
  const ts = () => Date.now();
  const tag = `T${ts()}`;

  const log = (name, ok, detail) => {
    steps.push({ name, ok, detail: detail == null ? null : String(detail).slice(0, 500) });
  };

  let token = '';
  try {
    const lr = await fetch(`${base}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: 'admin', password: 'admin123' }),
    });
    const lj = await lr.json();
    if (!lr.ok) throw new Error('login ' + lr.status + ' ' + JSON.stringify(lj));
    token = lj.access_token;
    log('auth_login', true, lr.status);
  } catch (e) {
    log('auth_login', false, e.message);
    return { part: 1, steps, error: 'login_failed' };
  }

  const h = (extra = {}) => ({
    Authorization: 'Bearer ' + token,
    ...extra,
  });

  const j = async (path, method, body) => {
    const r = await fetch(base + path, {
      method,
      headers: h({ 'Content-Type': 'application/json' }),
      body: body != null ? JSON.stringify(body) : undefined,
    });
    const t = await r.text();
    let b = null;
    try {
      b = t ? JSON.parse(t) : null;
    } catch {
      b = t;
    }
    return { status: r.status, body: b };
  };

  const del = async (path) => {
    const r = await fetch(base + path, { method: 'DELETE', headers: h() });
    return { status: r.status };
  };

  try {
    let r = await fetch(base + '/roles/', { headers: h() });
    log('roles_list', r.status === 200, r.status);
    r = await fetch(base + '/vessels/?limit=3', { headers: h() });
    log('vessels_list', r.status === 200, r.status);
    r = await fetch(base + '/orders/?limit=3', { headers: h() });
    log('orders_list', r.status === 200, r.status);
    r = await fetch(base + '/fee-configs/', { headers: h() });
    log('fee_configs_list', r.status === 200, r.status);
    r = await fetch(base + '/invoices/?limit=3', { headers: h() });
    log('invoices_list', r.status === 200, r.status);
    r = await fetch(base + '/cameras/', { headers: h() });
    log('cameras_list', r.status === 200, r.status);
    r = await fetch(base + '/port-configs/', { headers: h() });
    log('port_configs_list', r.status === 200, r.status);
  } catch (e) {
    log('list_batch', false, e.message);
  }

  const roleIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/roles/', 'POST', {
        role_name: `${tag}_role_${i}`,
        description: `auto ${i}`,
      });
      if (r.status !== 201) throw new Error('role create ' + r.status);
      roleIds.push(r.body.id);
    }
    log('roles_create_3', true, roleIds.join(','));
    let r = await j(`/roles/${roleIds[0]}`, 'GET');
    log('roles_get', r.status === 200, r.status);
    r = await j(`/roles/${roleIds[1]}`, 'PUT', { description: 'updated' });
    log('roles_put', r.status === 200, r.status);
    r = await del(`/roles/${roleIds[2]}`);
    log('roles_delete', r.status === 204, r.status);
  } catch (e) {
    log('roles_block', false, e.message);
  }

  const vtIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/vessel-types/', 'POST', {
        type_name: `${tag}_vtype_${i}`,
        description: `vt ${i}`,
      });
      if (r.status !== 201) throw new Error('vtype ' + r.status);
      vtIds.push(r.body.id);
    }
    log('vessel_types_create_3', true, vtIds.join(','));
    let r = await j(`/vessel-types/${vtIds[0]}`, 'GET');
    log('vessel_types_get', r.status === 200, r.status);
    r = await j(`/vessel-types/${vtIds[1]}`, 'PUT', {
      type_name: `${tag}_vtype_2b`,
      description: 'put',
    });
    log('vessel_types_put', r.status === 200, r.status);
    r = await del(`/vessel-types/${vtIds[2]}`);
    log('vessel_types_delete', r.status === 204, r.status);
  } catch (e) {
    log('vessel_types_block', false, e.message);
  }

  const vesselIds = [];
  const vtForShip = vtIds[0];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/vessels/', 'POST', {
        ship_id: `${tag}_SHIP_${i}`,
        name: `Name ${i}`,
        vessel_type_id: vtForShip,
        is_active: true,
      });
      if (r.status !== 201) throw new Error('vessel ' + r.status + JSON.stringify(r.body));
      vesselIds.push(r.body.id);
    }
    log('vessels_create_3', true, vesselIds.join(','));
    let r = await j(`/vessels/${vesselIds[0]}`, 'GET');
    log('vessels_get', r.status === 200, r.status);
    r = await j(`/vessels/${vesselIds[1]}`, 'PUT', { name: 'UpdatedVessel' });
    log('vessels_put', r.status === 200, r.status);
    r = await del(`/vessels/${vesselIds[2]}`);
    log('vessels_delete', r.status === 204, r.status);
  } catch (e) {
    log('vessels_block', false, e.message);
  }

  const orderIds = [];
  const vForOrder = vesselIds[0];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/orders/', 'POST', {
        order_number: `${tag}_ORD_${i}`,
        vessel_id: vForOrder,
        description: `order ${i}`,
        status: 'PENDING',
      });
      if (r.status !== 201) throw new Error('order ' + r.status);
      orderIds.push(r.body.id);
    }
    log('orders_create_3', true, orderIds.join(','));
    let r = await j(`/orders/${orderIds[0]}`, 'GET');
    log('orders_get', r.status === 200, r.status);
    r = await j(`/orders/${orderIds[1]}`, 'PUT', { description: 'upd' });
    log('orders_put', r.status === 200, r.status);
    r = await j(`/orders/${orderIds[1]}/status`, 'PATCH', { status: 'COMPLETED' });
    log('orders_patch_status', r.status === 200, r.status);
    r = await del(`/orders/${orderIds[2]}`);
    log('orders_delete', r.status === 204, r.status);
  } catch (e) {
    log('orders_block', false, e.message);
  }

  const feeIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/fee-configs/', 'POST', {
        fee_name: `${tag}_fee_${i}`,
        base_fee: 10 + i,
        unit: 'per_month',
        is_active: true,
      });
      if (r.status !== 201) throw new Error('fee ' + r.status);
      feeIds.push(r.body.id);
    }
    log('fee_configs_create_3', true, feeIds.join(','));
    let r = await j(`/fee-configs/${feeIds[0]}`, 'GET');
    log('fee_configs_get', r.status === 200, r.status);
    r = await j(`/fee-configs/${feeIds[1]}`, 'PUT', { fee_name: `${tag}_fee_2x` });
    log('fee_configs_put', r.status === 200, r.status);
    r = await del(`/fee-configs/${feeIds[2]}`);
    log('fee_configs_delete', r.status === 204, r.status);
  } catch (e) {
    log('fee_configs_block', false, e.message);
  }

  return { part: 1, tag, steps, summary: steps.filter((s) => !s.ok).length === 0 ? 'all_ok' : 'has_failures' };
})();
