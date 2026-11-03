import { toAppError, upstreamErrorOf } from './normalize';

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

// What an ApiError carries: the whole BFF answer, the refusal of the core under error.details.upstream_detail
const bffAnswer = {
  error: {
    code: 'BFF_UPSTREAM_ERROR',
    message: '2 active access(es)',
    details: {
      upstream_status: 409,
      upstream_detail: { error: { code: 'STORAGE_ROOT_HAS_ACCESSES', message: '2 active access(es)', details: { roots: 2 } } }
    }
  }
};
const apiError = Object.assign(new Error('2 active access(es)'), { name: 'ApiError', status: 409, code: 'BFF_UPSTREAM_ERROR', details: bffAnswer });

assert(upstreamErrorOf(bffAnswer)?.code === 'STORAGE_ROOT_HAS_ACCESSES', 'code under error.details');
assert((upstreamErrorOf(bffAnswer)?.details as any)?.roots === 2, 'details of the core refusal');
assert(upstreamErrorOf(bffAnswer.error.details)?.code === 'STORAGE_ROOT_HAS_ACCESSES', 'code under the details themselves');
assert(upstreamErrorOf({ error: { code: 'X' } }) === null, 'no core refusal');
assert(toAppError(apiError).code === 'STORAGE_ROOT_HAS_ACCESSES', `business code wins: ${toAppError(apiError).code}`);

const french = Object.assign(new Error('x'), { name: 'ApiError', status: 403, details: { error: { message: 'Access forbidden' } } });
assert(typeof toAppError(french).message === 'string' && toAppError(french).message.length > 0, 'a message');

console.log('normalize: ok');
