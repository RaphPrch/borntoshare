import assert from 'node:assert/strict';
import { applySuggestion, folderSuggestions, matchesFolderQuery, parseFolderQuery, removeFilter } from './folder-query';

const rows = [
  { storage_root_id: 1, storage_root_name: 'Finance', root_path: '\\\\172.22.98.56\\PiloteB2S\\Finance', zone_name: 'CORP', storage_endpoint_name: 'FILER01',
    tags: [{ label: 'Données RH' }], guardian_names: ['Alice Martin', 'alice.martin'], guardians_count: 1, open_alerts_count: 0,
    last_probe_status: 'success', content_size_bytes: 2 * 1024 ** 3, dfs_path: '\\\\corp.local\\brest\\Corporate\\Finance' },
  { storage_root_id: 2, storage_root_name: 'Archives', root_path: '\\\\172.22.98.56\\Archives', zone_name: 'MAISON', storage_endpoint_name: 'FILER01',
    tags: [], guardian_names: [], guardians_count: 0, open_alerts_count: 3, open_alert_types: 'missing_guardian,acl_profile_missing',
    last_probe_status: 'failed', content_size_bytes: 0, inheritance_broken: true }
];
const ids = (query: string) => rows.filter((row) => matchesFolderQuery(row, parseFolderQuery(query).filters)).map((row) => row.storage_root_id);

// separates the filters from the free text
{
    const parsed = parseFolderQuery('compta tag:"Données RH" -est:alerte gardien:');
    assert.equal(parsed.text, 'compta');
    assert.deepEqual(parsed.filters.map((f) => [f.key, f.value, f.neg]), [['tag', 'Données RH', false], ['is', 'alerte', true]]);
}

// filters by tag, guardian, zone, DFS, state and size
{
    assert.deepEqual(ids('tag:donnees'), [1]);
    assert.deepEqual(ids('gardien:alice'), [1]);
    assert.deepEqual(ids('g:martin zone:corp'), [1]);
    assert.deepEqual(ids('dfs:brest'), [1]);
    assert.deepEqual(ids('est:sans-gardien'), [2]);
    assert.deepEqual(ids('est:heritage-rompu'), [2]);
    assert.deepEqual(ids('est:injoignable'), [2]);
    assert.deepEqual(ids('-est:alerte'), [1]);
    assert.deepEqual(ids('alerte:acl'), [2]);
    assert.deepEqual(ids('taille>1Go'), [1]);
    assert.deepEqual(ids('taille<1Mo'), [2]);
    assert.deepEqual(ids('serveur:filer01 partage:archives'), [2]);
}

// proposes values for the key being typed and for a plain word
{
    assert.deepEqual(folderSuggestions('gardien:al', rows).map((s) => s.insert), ['gardien:"Alice Martin"']);
    assert.equal(folderSuggestions('rh', rows).some((s) => s.insert === 'tag:"Données RH"'), true);
    assert.deepEqual(folderSuggestions('est:gard', rows).map((s) => s.insert), ['est:sans-gardien']);
}

// replaces the word being typed and removes a filter
{
    assert.equal(applySuggestion('compta gardien:al', 'gardien:"Alice Martin"'), 'compta gardien:"Alice Martin" ');
    assert.equal(applySuggestion('', 'tag:'), 'tag:');
    assert.equal(removeFilter('compta tag:RH est:alerte', 'tag:RH'), 'compta est:alerte');
}
console.log('folder-query: ok');
