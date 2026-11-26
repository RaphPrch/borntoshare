import assert from 'node:assert/strict';

import { activeItem, buildNav, type NavContext } from './nav';

const ctx = (over: Partial<NavContext>): NavContext => ({ admin: false, staff: false, features: ['governance'], pending: 0, critical: 0, ...over });
const labels = (c: NavContext) => Object.fromEntries(buildNav(c).map((section) => [section.label, section.items.map((item) => item.label)]));

// Administrator, governance and 5S: the target menu, minus the entries without a feature yet
assert.deepEqual(labels(ctx({ admin: true, staff: true, features: ['governance', 'fives'] })), {
  Workspace: ['Dashboard', 'Assistant', 'My Tasks'],
  Governance: ['Storage Roots', 'Access Management', 'Access Explorer', 'Governance Jobs', 'Policies'],
  'Storage Intelligence': ['Explorer', 'Inventory', 'Analytics', 'Insights & Recommendations', 'Evidence Center'],
  Administration: ['Storage Endpoints', 'Zones', 'Identity & Users', 'Settings']
});

// Without the 5S module: Storage Intelligence keeps what comes from the governance
assert.deepEqual(labels(ctx({ admin: true, staff: true }))['Storage Intelligence'], ['Insights & Recommendations', 'Evidence Center']);

// A guardian: no administration, no platform evidence, his own view of the jobs
const guardian = labels(ctx({ staff: true, features: ['governance', 'fives'] }));
assert.equal(guardian.Administration, undefined);
assert.deepEqual(guardian['Storage Intelligence'], ['Explorer', 'Inventory', 'Analytics', 'Insights & Recommendations']);
assert.ok(guardian.Governance.includes('Access Explorer') && !guardian.Governance.includes('Policies'));

// A user: his dashboard, his tasks, the folders and his requests; nothing about the platform
assert.deepEqual(labels(ctx({})), { Workspace: ['Dashboard', 'My Tasks'], Governance: ['Storage Roots', 'Access Management'] });

// 5S only (no governance): no access management nor Access Explorer
const fivesOnly = labels(ctx({ admin: true, staff: true, features: ['fives'] }));
assert.ok(!fivesOnly.Governance.includes('Access Management') && !fivesOnly.Governance.includes('Access Explorer'));

// No personal name anywhere in the menu
assert.ok(!JSON.stringify(buildNav(ctx({ admin: true, staff: true, features: ['governance', 'fives'] }))).match(/rapha/i));

// The old address of the Assistant still lights its entry; Access Explorer is no longer a tab of Access Management
const sections = buildNav(ctx({ admin: true, staff: true, features: ['governance', 'fives'] }));
assert.equal(activeItem(sections, '/pilot')?.item.label, 'Assistant');
assert.equal(activeItem(sections, '/exposure')?.item.label, 'Access Explorer');
assert.equal(activeItem(sections, '/access-explorer')?.item.label, 'Access Explorer');
// The storage map is a tab of Storage Endpoints (administrators only)
assert.equal(activeItem(sections, '/admin/storage-topology')?.item.label, 'Storage Endpoints');
assert.ok(activeItem(sections, '/admin/storage-topology')?.item.tabs?.some((tab) => tab.href === '/admin/storage-topology'));
assert.equal(activeItem(sections, '/access-reviews/4')?.item.label, 'Access Management');
assert.equal(activeItem(sections, '/five-s/report/12')?.item.label, 'Explorer');
console.log('nav: menus by role and license ok');
