/**
 * Part 2 (sau part 1 hoặc chạy độc lập): invoices, payments, cameras, port-configs,
 * auth/register + users CRUD, detections, port-logs, dashboard, exports, audit, /users/me
 *
 * detections/port_logs: POST tạo bản ghi dùng một lần rồi DELETE → luôn mong đợi 204.
 */
(async () => {
  const base = 'http://127.0.0.1:8080/api/v1';
  const steps = [];
  const log = (name, ok, detail) => {
    steps.push({ name, ok, detail: detail == null ? null : String(detail).slice(0, 500) });
  };

  const ts = Date.now();
  const tag = `T${ts}`;
  // Unique per run: avoids DB unique on rtsp_url colliding with seeded rows or parallel runs.
  const rtspRunSalt = `${tag}_${Math.random().toString(36).slice(2, 11)}`;

  let token = '';
  try {
    const lr = await fetch(`${base}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: 'admin', password: 'admin123' }),
    });
    const lj = await lr.json();
    if (!lr.ok) throw new Error('login');
    token = lj.access_token;
    log('auth_login', true, lr.status);
  } catch (e) {
    log('auth_login', false, e.message);
    return { part: 2, steps, error: 'login_failed' };
  }

  try {
    let r = await fetch(base + '/roles/', { headers: { Authorization: 'Bearer ' + token } });
    log('roles_list', r.status === 200, r.status);
    r = await fetch(base + '/users/?limit=5', { headers: { Authorization: 'Bearer ' + token } });
    log('users_list', r.status === 200, r.status);
    r = await fetch(base + '/vessel-types/', { headers: { Authorization: 'Bearer ' + token } });
    log('vessel_types_list', r.status === 200, r.status);
  } catch (e) {
    log('list_reads', false, e.message);
  }

  const h = (extra = {}) => ({ Authorization: 'Bearer ' + token, ...extra });
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

  let vesselId = null;
  try {
    const r = await fetch(base + '/vessels/?limit=5', { headers: h() });
    const list = await r.json();
    if (Array.isArray(list) && list.length) vesselId = list[0].id;
    log('prefetch_vessel', vesselId != null, String(vesselId));
  } catch (e) {
    log('prefetch_vessel', false, e.message);
  }

  const invIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/invoices/', 'POST', {
        invoice_number: `${tag}_INV_${i}`,
        vessel_id: vesselId,
        total_amount: 100 + i,
        payment_status: 'UNPAID',
        items: [{ unit_price: 50, amount: 100 + i, description: 'line' }],
      });
      if (r.status !== 201) throw new Error('inv ' + r.status + JSON.stringify(r.body));
      invIds.push(r.body.id);
    }
    log('invoices_create_3', true, invIds.join(','));
    let r = await j(`/invoices/${invIds[0]}`, 'GET');
    log('invoices_get', r.status === 200, r.status);
    r = await j(`/invoices/${invIds[1]}`, 'PUT', { notes: 'note-upd' });
    log('invoices_put', r.status === 200, r.status);
    r = await j(`/invoices/${invIds[0]}/payments`, 'POST', {
      invoice_id: invIds[0],
      amount: '10.00',
      payment_method: 'cash',
    });
    log('invoices_payment_post', r.status === 201, r.status);
    r = await j(`/invoices/${invIds[0]}/payments`, 'GET');
    log('invoices_payments_list', r.status === 200, Array.isArray(r.body) ? r.body.length : 0);
    r = await del(`/invoices/${invIds[2]}`);
    log('invoices_delete', r.status === 204, r.status);
  } catch (e) {
    log('invoices_block', false, e.message);
  }

  const camIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await j('/cameras/', 'POST', {
        camera_name: `${tag}_cam_${i}`,
        rtsp_url: `rtsp://127.0.0.1/${rtspRunSalt}/cam${i}/path`,
        is_active: true,
      });
      if (r.status !== 201) throw new Error('cam ' + r.status);
      camIds.push(r.body.id);
    }
    log('cameras_create_3', true, camIds.join(','));
    let r = await j(`/cameras/${camIds[0]}`, 'GET');
    log('cameras_get', r.status === 200, r.status);
    r = await j(`/cameras/${camIds[1]}`, 'PUT', { description: 'd' });
    log('cameras_put', r.status === 200, r.status);
    r = await del(`/cameras/${camIds[2]}`);
    log('cameras_delete', r.status === 204, r.status);
  } catch (e) {
    log('cameras_block', false, e.message);
  }

  const cfgKeys = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const k = `${tag}_cfg_${i}`;
      const r = await j('/port-configs/', 'POST', {
        key: k,
        value: `v${i}`,
        description: 'd',
      });
      if (r.status !== 201) throw new Error('pc ' + r.status + JSON.stringify(r.body));
      cfgKeys.push(k);
    }
    log('port_configs_create_3', true, cfgKeys.join(','));
    let r = await j(`/port-configs/${encodeURIComponent(cfgKeys[0])}`, 'GET');
    log('port_configs_get', r.status === 200, r.status);
    r = await j(`/port-configs/${encodeURIComponent(cfgKeys[1])}`, 'PUT', {
      value: 'updated',
    });
    log('port_configs_put', r.status === 200, r.status);
    r = await del(`/port-configs/${encodeURIComponent(cfgKeys[2])}`);
    log('port_configs_delete', r.status === 204, r.status);
  } catch (e) {
    log('port_configs_block', false, e.message);
  }

  const regIds = [];
  try {
    for (let i = 1; i <= 3; i++) {
      const r = await fetch(`${base}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: `${tag}_u_${i}`,
          password: 'TestPass123!',
          full_name: `User ${i}`,
          email: `${tag}_u_${i}@test.local`,
        }),
      });
      const b = await r.json();
      if (r.status !== 201) throw new Error('reg ' + r.status + JSON.stringify(b));
      regIds.push(b.id);
    }
    log('auth_register_3', true, regIds.join(','));
    let r = await j(`/users/${regIds[0]}`, 'GET');
    log('users_get', r.status === 200, r.status);
    r = await j(`/users/${regIds[1]}`, 'PUT', { full_name: 'Renamed' });
    log('users_put', r.status === 200, r.status);
    r = await del(`/users/${regIds[2]}`);
    log('users_delete', r.status === 204, r.status);
  } catch (e) {
    log('users_block', false, e.message);
  }

  try {
    let r = await j('/detections/?limit=20', 'GET');
    log('detections_list', r.status === 200, Array.isArray(r.body) ? r.body.length : 'na');
    const dets = Array.isArray(r.body) ? r.body : [];
    if (dets.length) {
      const id = dets[0].id;
      r = await j(`/detections/${id}`, 'GET');
      log('detections_get', r.status === 200, r.status);
      r = await j(`/detections/${id}/media`, 'GET');
      log('detections_media', r.status === 200, 'len ' + (Array.isArray(r.body) ? r.body.length : 0));
      if (dets[0].is_accepted !== true) {
        r = await j(`/detections/${id}/verify`, 'POST', { is_accepted: true });
        log('detections_verify_post', r.status === 200, r.status);
      } else {
        log('detections_verify_post', true, 'skip_already');
      }
    } else {
      log('detections_get', true, 'skip_no_rows');
      log('detections_media', true, 'skip_no_rows');
      log('detections_verify_post', true, 'skip_no_rows');
    }
    const detDispose = {
      track_id: `${tag}_det_${Math.random().toString(36).slice(2, 11)}`,
    };
    if (vesselId != null) detDispose.vessel_id = vesselId;
    r = await j('/detections/', 'POST', detDispose);
    if (r.status !== 201) throw new Error('det_create ' + r.status + JSON.stringify(r.body));
    r = await del(`/detections/${r.body.id}`);
    log('detections_delete', r.status === 204, r.status);
  } catch (e) {
    log('detections_block', false, e.message);
  }

  try {
    let r = await j('/port-logs/?limit=20', 'GET');
    log('port_logs_list', r.status === 200, Array.isArray(r.body) ? r.body.length : 'na');
    const logs = Array.isArray(r.body) ? r.body : [];
    if (logs.length) {
      const id = logs[0].id;
      r = await j(`/port-logs/${id}`, 'GET');
      log('port_logs_get', r.status === 200, r.status);
    } else {
      log('port_logs_get', true, 'skip_no_rows');
    }
    r = await j('/port-logs/', 'POST', {
      track_id: `${tag}_plog_${Math.random().toString(36).slice(2, 11)}`,
    });
    if (r.status !== 201) throw new Error('plog_create ' + r.status + JSON.stringify(r.body));
    r = await del(`/port-logs/${r.body.id}`);
    log('port_logs_delete', r.status === 204, r.status);
  } catch (e) {
    log('port_logs_block', false, e.message);
  }

  try {
    const r = await fetch(base + '/dashboard/stats', { headers: h() });
    const b = await r.json();
    log('dashboard_stats', r.status === 200, r.status);
  } catch (e) {
    log('dashboard_stats', false, e.message);
  }

  try {
    const r = await fetch(base + '/exports/port-logs', { headers: h() });
    log('exports_port_logs', r.status === 200, r.status);
  } catch (e) {
    log('exports_port_logs', false, e.message);
  }

  try {
    const r = await fetch(base + '/audit-logs/?limit=5', { headers: h() });
    const b = await r.json();
    log('audit_logs_list', r.status === 200, Array.isArray(b) ? b.length : 0);
  } catch (e) {
    log('audit_logs_list', false, e.message);
  }

  try {
    const r = await fetch(base + '/users/me', { headers: h() });
    log('users_me', r.status === 200, r.status);
  } catch (e) {
    log('users_me', false, e.message);
  }

  return { part: 2, tag, steps, failed: steps.filter((s) => !s.ok).length };
})();
