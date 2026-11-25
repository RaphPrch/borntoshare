import assert from 'node:assert/strict';

import { redirectFor } from './route-access';

const admin = { admin: true, staff: true, features: ['governance', 'fives'] };
const guardian = { admin: false, staff: true, features: ['governance', 'fives'] };
const user = { admin: false, staff: false, features: ['governance'] };

// Everyone has his tasks and his dashboard
for (const who of [admin, guardian, user]) {
  assert.equal(redirectFor('/tasks', who), null);
  assert.equal(redirectFor('/dashboard', who), null);
}
// The screens about the folders: staff only, the old address of the Assistant included
for (const path of ['/assistant', '/pilot', '/exposure', '/reports', '/five-s/explore', '/observability', '/access-reviews/3']) {
  assert.equal(redirectFor(path, user), '/dashboard', path);
  assert.equal(redirectFor(path, guardian), null, path);
}
// The evidence of the platform: administrators only
assert.equal(redirectFor('/evidence', guardian), '/dashboard');
assert.equal(redirectFor('/evidence', admin), null);
// 5S only: no access requests nor Access Explorer, the guardian lands on the 5S
const fivesOnlyGuardian = { admin: false, staff: true, features: ['fives'] };
assert.equal(redirectFor('/access-requests', fivesOnlyGuardian), '/five-s');
assert.equal(redirectFor('/exposure', fivesOnlyGuardian), '/five-s');
assert.equal(redirectFor('/dashboard', fivesOnlyGuardian), '/five-s');
assert.equal(redirectFor('/five-s', fivesOnlyGuardian), null);
console.log('route access: rules by role and license ok');
