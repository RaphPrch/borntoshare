import {
  filterIdentityRowsByImportPolicy,
  shouldResetGovernanceDraftFromOwners,
} from './storage-root-governance';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testShouldResetGovernanceDraftFromOwners(): void {
  assert(shouldResetGovernanceDraftFromOwners(false) === true, 'draft should reset when not dirty');
  assert(shouldResetGovernanceDraftFromOwners(true) === false, 'draft should not reset when dirty');
}

function testFilterIdentityRowsByImportPolicy(): void {
  const rows = [
    { id: 1, is_import_candidate: false },
    { id: 2, is_import_candidate: true },
    { id: 3 },
  ];

  const keepAll = filterIdentityRowsByImportPolicy(rows, true);
  assert(keepAll.length === 3, 'includeImportCandidates=true should keep all rows');

  const filtered = filterIdentityRowsByImportPolicy(rows, false);
  assert(filtered.length === 2, 'includeImportCandidates=false should remove import candidates');
  assert(filtered.some((row) => row.id === 1), 'row #1 should remain');
  assert(filtered.some((row) => row.id === 3), 'row #3 should remain');
  assert(!filtered.some((row) => row.id === 2), 'row #2 should be filtered out');
}

async function run(): Promise<void> {
  testShouldResetGovernanceDraftFromOwners();
  testFilterIdentityRowsByImportPolicy();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});

