import assert from 'node:assert/strict';
import { test } from 'node:test';
import { apiToVietnamInput, vietnamInputToApi } from '../src/utils/date-time.ts';

for (const timezone of ['UTC', 'Asia/Ho_Chi_Minh', 'America/New_York']) {
  test(`detection form uses Vietnam time in ${timezone}`, () => {
    process.env.TZ = timezone;
    assert.equal(apiToVietnamInput('2026-11-25T04:30:02.370914'), '2026-11-25T11:30:02');
    assert.equal(apiToVietnamInput('2026-11-25T04:32:27.064126Z'), '2026-11-25T11:32:27');
    assert.equal(apiToVietnamInput('2026-11-25T11:32:27+07:00'), '2026-11-25T11:32:27');
    assert.equal(vietnamInputToApi('2026-11-25T00:00:00'), '2026-11-24T17:00:00.000Z');
    assert.equal(vietnamInputToApi('2026-11-25T11:30:02'), '2026-11-25T04:30:02.000Z');
    assert.equal(vietnamInputToApi('2026-11-25T11:30'), '2026-11-25T04:30:00.000Z');
  });
}
test('empty and invalid times', () => {
  assert.equal(apiToVietnamInput(null), '');
  assert.equal(apiToVietnamInput('invalid'), '');
  assert.equal(vietnamInputToApi(''), null);
  assert.throws(() => vietnamInputToApi('2026-02-30T11:30:00'));
  assert.throws(() => vietnamInputToApi('2026-11-25T25:00:00'));
});
