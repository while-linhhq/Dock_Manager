/**
 * Chạy tuần tự hai suite (giống logic dùng trong Chrome MCP evaluate_script).
 * Usage: node mcp_run_all.cjs
 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

(async () => {
  const files = ['mcp_api_suite_part1.js', 'mcp_api_suite_part2.js'];
  const combined = { parts: [], allOk: true };
  for (const f of files) {
    const code = fs.readFileSync(path.join(__dirname, f), 'utf8');
    const ctx = {
      fetch,
      console,
      URLSearchParams,
      setTimeout,
      clearTimeout,
    };
    const p = vm.runInNewContext(code, ctx, { filename: f, timeout: 120000 });
    const r = await p;
    combined.parts.push(r);
    const steps = r.steps || [];
    const bad = steps.filter((s) => !s.ok);
    if (bad.length) {
      combined.allOk = false;
      combined.failures = combined.failures || [];
      combined.failures.push({ file: f, steps: bad });
    }
    console.log('\n=== ' + f + ' ===');
    console.log(JSON.stringify(r, null, 2));
  }
  console.log('\n=== SUMMARY ===');
  console.log(JSON.stringify({ allOk: combined.allOk, failures: combined.failures || [] }));
  process.exit(combined.allOk ? 0 : 1);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
