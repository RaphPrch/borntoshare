import assert from 'node:assert/strict';
import {
  dependencyCountDeleteMessage,
  dependencyDeleteMessage,
  deleteErrorStatus,
  isDependencyDeleteError
} from './delete-guard';

assert.equal(deleteErrorStatus({ status: 409 }), 409);
assert.equal(isDependencyDeleteError({ status: 409, message: 'Conflict' }), true);
assert.equal(
  isDependencyDeleteError({ message: 'Storage root is still referenced by dependent records and cannot be deleted' }),
  true
);
assert.equal(isDependencyDeleteError({ status: 500, message: 'Internal server error' }), false);
assert.equal(
  dependencyDeleteMessage('zone', 'storage endpoints'),
  'This zone cannot be deleted while storage endpoints are still attached.'
);
assert.equal(
  dependencyCountDeleteMessage('endpoint', 1, 'storage root'),
  'This endpoint cannot be deleted while 1 storage root is still attached.'
);
assert.equal(
  dependencyCountDeleteMessage('endpoint', 2, 'storage root'),
  'This endpoint cannot be deleted while 2 storage roots are still attached.'
);

console.log('delete-guard tests passed');
