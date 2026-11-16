import { resolveDirectRoute } from './service-routes';

declare const process: { exitCode?: number };

function assert(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

/** Pages that called a path the proxy did not know showed « API route not found » (access reviews, monthly report). */
function testEveryPageOfTheCoreIsRouted(): void {
  for (const path of ['/api/access-reviews', '/api/access-reviews/4', '/api/access-reviews/4/decisions', '/api/monthly-report/preview', '/api/monthly-report/send']) {
    const route = resolveDirectRoute(path);
    assert(route?.service === 'core', `${path} goes to the core`);
  }
  // Applying a review revokes accesses: an orchestration of the governance routes
  assert(resolveDirectRoute('/api/access-reviews/4/apply')?.path === '/governance/access-reviews/4/apply', 'apply is orchestrated');
  assert(resolveDirectRoute('/api/internal/anything') === null, 'internal routes stay closed');
}

try {
  testEveryPageOfTheCoreIsRouted();
  console.log('service-routes tests passed');
} catch (error) {
  console.error(error);
  process.exitCode = 1;
}
