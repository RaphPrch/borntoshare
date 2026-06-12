import { effectiveRootProbeStatus, rootToneFromProbeStatus } from './storage-root-reachability';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

function testRuntimePriority(): void {
  assert(
    effectiveRootProbeStatus({ runtimeStatus: 'failed', persistedStatus: 'success' }) === 'failed',
    'runtime failed must override persisted success'
  );
  assert(
    effectiveRootProbeStatus({ runtimeStatus: 'success', persistedStatus: 'failed' }) === 'success',
    'runtime success must override persisted failed'
  );
}

function testUnknownRuntimeFallsBackToPersisted(): void {
  assert(
    effectiveRootProbeStatus({ runtimeStatus: 'mystery', persistedStatus: 'failed' }) === 'failed',
    'non-canonical runtime should fallback to persisted status'
  );
  assert(
    effectiveRootProbeStatus({ runtimeStatus: '', persistedStatus: 'success' }) === 'success',
    'empty runtime should fallback to persisted status'
  );
}

function testToneMapping(): void {
  assert(
    rootToneFromProbeStatus({ runtimeStatus: 'failed', persistedStatus: 'success' }) === 'error',
    'failed runtime should force error tone'
  );
  assert(
    rootToneFromProbeStatus({ runtimeStatus: '', persistedStatus: 'failed' }) === 'error',
    'failed persisted should map to error tone'
  );
  assert(
    rootToneFromProbeStatus({ runtimeStatus: '', persistedStatus: 'success' }) === 'healthy',
    'success persisted should map to healthy tone'
  );
}

async function run(): Promise<void> {
  testRuntimePriority();
  testUnknownRuntimeFallsBackToPersisted();
  testToneMapping();
}

run().catch((err) => {
  console.error(err);
  process.exitCode = 1;
});
