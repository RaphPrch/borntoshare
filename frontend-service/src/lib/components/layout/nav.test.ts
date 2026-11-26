import assert from 'node:assert/strict';

import { activeItem, buildNav, type NavContext } from './nav';

const ctx = (over: Partial<NavContext>): NavContext => ({ admin: false, staff: false, features: ['governance'], pending: 0, critical: 0, ...over });
const labels = (c: NavContext) => Object.fromEntries(buildNav(c).map((section) => [section.label, section.items.map((item) => item.label)]));

// Administrator, governance and 5S: the target menu, minus the entries without a feature yet
assert.deepEqual(labels(ctx({ admin: true, staff: true, features: ['governance', 'fives'] })), {
  Workspace: ['Dashboard', 'Assistant', 'My Tasks'],
  Governance: ['Storage Roots', 'Access Management', 'Governance Jobs', 'Policies'],
  'Storage Intelligence': ['Explorer', 'Inventory', 'Analytics', 'Insights & Recommendations', 'Evidence Center'],
  Administration: ['Storage Endpoints', 'Zones', 'Identity & Users', 'Settings']
});

// Without the 5S module: Storage Intelligence keeps what comes from the governance
assert.deepEqual(labels(ctx({ admin: true, staff: true }))['Storage Intelligence'], ['Insights & Recommendations', 'Evidence Center']);

// A guardian: no administration, no platform evidence, his own view of the jobs
const guardian = labels(ctx({ staff: true, features: ['governance', 'fives'] }));
assert.equal(guardian.Administration, undefined);
assert.deepEqual(guardian['Storage Intelligence'], ['Explorer', 'Inventory', 'Analytics', 'Insights & Recommendations']);
assert.ok(guardian.Governance.includes('Access Management') && !guardian.Governance.includes('Policies'));

// A user: his dashboard, his tasks, the folders and his requests; nothing about the platform
assert.deepEqual(labels(ctx({})), { Workspace: ['Dashboard', 'My Tasks'], Governance: ['Storage Roots', 'Access Management'] });

// 5S only (no governance): no access management (nor its Explorer)
const fivesOnly = labels(ctx({ admin: true, staff: true, features: ['fives'] }));
assert.ok(!fivesOnly.Governance.includes('Access Management'));

// No personal name anywhere in the menu
assert.ok(!JSON.stringify(buildNav(ctx({ admin: true, staff: true, features: ['governance', 'fives'] }))).match(/rapha/i));

// The old address of the Assistant still lights its entry; the Explorer is a tab of Access Management
const sections = buildNav(ctx({ admin: true, staff: true, features: ['governance', 'fives'] }));
assert.equal(activeItem(sections, '/pilot')?.item.label, 'Assistant');
assert.equal(activeItem(sections, '/access-explorer')?.item.label, 'Access Management');
const access = (c: NavContext) => buildNav(c).flatMap((s) => s.items).find((item) => item.href === '/access-requests')?.tabs?.map((tab) => tab.href);
assert.deepEqual(access(ctx({ staff: true })), ['/access-requests', '/access-reviews', '/access-explorer']);
// A user: his requests only, no reviews nor Explorer
assert.deepEqual(access(ctx({})), ['/access-requests']);
// The cockpit of the data: one entry, its tabs (overview, recommendations, topology, exposure, reports)
for (const path of ['/insights', '/insights/recommendations', '/insights/topology', '/insights/exposure', '/reports', '/reports/storage']) {
  assert.equal(activeItem(sections, path)?.item.label, 'Insights & Recommendations', path);
}
const cockpit = (c: NavContext) => buildNav(c).flatMap((s) => s.items).find((item) => item.href === '/insights')?.tabs?.map((tab) => tab.href);
assert.deepEqual(cockpit(ctx({ admin: true, staff: true })), ['/insights', '/insights/recommendations', '/insights/topology', '/insights/exposure', '/reports']);
// A guardian: no topology (hosts of the servers); without the governance: no exposure
assert.deepEqual(cockpit(ctx({ staff: true })), ['/insights', '/insights/recommendations', '/insights/exposure', '/reports']);
assert.deepEqual(cockpit(ctx({ admin: true, staff: true, features: ['fives'] })), ['/insights', '/insights/recommendations', '/insights/topology', '/reports']);
// Storage Endpoints is the configuration only
assert.equal(buildNav(ctx({ admin: true, staff: true })).flatMap((s) => s.items).find((item) => item.href === '/admin/storage-endpoints')?.tabs, undefined);
assert.equal(activeItem(sections, '/access-reviews/4')?.item.label, 'Access Management');
assert.equal(activeItem(sections, '/five-s/report/12')?.item.label, 'Explorer');
console.log('nav: menus by role and license ok');
