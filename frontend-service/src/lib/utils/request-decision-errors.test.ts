import {
  mapAccessRequestDecisionError,
  mapAccessRequestDecisionErrorFromBulk
} from './request-decision-errors';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testGroupNameMissingMappedToFriendlyMessage(): void {
  const mapped = mapAccessRequestDecisionError({
    detail: {
      code: 'GOVERNED_GROUP_NAME_MISSING',
      requested_permission: 'READ',
      storage_root_id: 42
    },
    reason: null
  });

  assert(mapped.title === 'Decision blocked', 'title should be Decision blocked');
  assert(mapped.severity === 'warning', 'missing group name should be warning severity');
  assert(mapped.message.includes('naming policy'), 'message should point to the naming policy');
  assert(mapped.actionHref === '/storage-roots?selected=42', 'actionHref should target storage root page');
}

function testInvalidAccessLevelIsBlocked(): void {
  const mapped = mapAccessRequestDecisionError({ detail: { code: 'INVALID_ACCESS_LEVEL' }, reason: null });
  assert(mapped.title === 'Decision blocked', 'invalid level should block the decision');
}

function testReasonOnlyFallsBackToBackendMessage(): void {
  const mapped = mapAccessRequestDecisionError({
    detail: null,
    reason: 'unexpected backend failure'
  });

  assert(mapped.code === null, 'reason-only payload should not infer technical code');
  assert(mapped.message === 'unexpected backend failure', 'reason-only payload should preserve backend message');
}

function testUnknownErrorFallsBackToGenericMessage(): void {
  const mapped = mapAccessRequestDecisionError({
    detail: null,
    reason: null
  });

  assert(mapped.title === 'Decision failed', 'unknown should use generic title');
  assert(mapped.message === 'The request could not be applied. Review the request configuration and try again.', 'unknown should use generic message');
}

function testBulkMapperUsesFirstFailedItem(): void {
  const mapped = mapAccessRequestDecisionErrorFromBulk(
    {
      ok: false,
      decision: 'approve',
      requested_ids: [1],
      updated_ids: [],
      failed_ids: [1],
      failed_reasons: {},
      failed_details: {
        1: {
          code: 'INVALID_REQUEST_PERMISSION',
          message: 'invalid permission'
        }
      },
      updated_count: 0,
      executions_started: 0
    },
    {}
  );

  assert(mapped.code === 'INVALID_REQUEST_PERMISSION', 'bulk mapper should pick first failed detail code');
  assert(mapped.title === 'Decision blocked', 'invalid permission should map to blocked title');
}

async function run(): Promise<void> {
  testGroupNameMissingMappedToFriendlyMessage();
  testInvalidAccessLevelIsBlocked();
  testReasonOnlyFallsBackToBackendMessage();
  testUnknownErrorFallsBackToGenericMessage();
  testBulkMapperUsesFirstFailedItem();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
