-- Automatic tags: smart policies (Politiques) that put a tag on the folders matching a condition and remove it
-- when they no longer match (action remove_tag). From the sensitivity scan (rules version 3) and the path.
-- Created once, then theirs to change or switch off: a policy or a tag of the same name is left as it is.
-- Idempotent: can be applied again.

INSERT INTO tags (name, color, family)
SELECT seed.name, seed.color, 'Automatique'
FROM (
  SELECT 'Mots de passe' AS name, '#dc2626' AS color UNION ALL
  SELECT 'Clés et jetons', '#b91c1c' UNION ALL
  SELECT 'Données personnelles', '#9333ea' UNION ALL
  SELECT 'Données bancaires', '#7c3aed' UNION ALL
  SELECT 'Fichiers à risque', '#d97706' UNION ALL
  SELECT 'Ressources humaines', '#16a34a' UNION ALL
  SELECT 'Finance', '#2563eb' UNION ALL
  SELECT 'Juridique', '#b45309'
) seed
WHERE NOT EXISTS (SELECT 1 FROM tags t WHERE LOWER(t.name) = LOWER(seed.name) AND t.deleted_at IS NULL);

INSERT INTO governance_policies (name, description, enabled, condition_query, actions_json, created_by, updated_by)
SELECT seed.name, seed.description, 1, seed.query,
       JSON_OBJECT('add_tag', (SELECT t.id FROM tags t WHERE LOWER(t.name) = LOWER(seed.tag) AND t.deleted_at IS NULL ORDER BY t.id LIMIT 1),
                   'remove_tag', TRUE, 'alert', NULL, 'notify_guardians', FALSE, 'jobs', NULL),
       'BornToShare', 'BornToShare'
FROM (
  SELECT 'Tag automatique · Mots de passe' AS name, 'Dossiers où l''analyse a trouvé des mots de passe, des fichiers ou des coffres de mots de passe.' AS description,
         'est:mot-de-passe' AS query, 'Mots de passe' AS tag UNION ALL
  SELECT 'Tag automatique · Clés et jetons', 'Dossiers où l''analyse a trouvé des clés privées, des clés d''API ou des jetons.',
         'est:cle-ou-jeton', 'Clés et jetons' UNION ALL
  SELECT 'Tag automatique · Données personnelles', 'Dossiers où l''analyse a trouvé des numéros de sécurité sociale (vérifiés par leur clé).',
         'est:donnees-personnelles', 'Données personnelles' UNION ALL
  SELECT 'Tag automatique · Données bancaires', 'Dossiers où l''analyse a trouvé des IBAN ou des numéros de carte (vérifiés par leur clé).',
         'est:bancaire', 'Données bancaires' UNION ALL
  SELECT 'Tag automatique · Fichiers à risque', 'Dossiers qui contiennent des sauvegardes ou bases de données, des boîtes mail ou des programmes.',
         'est:fichiers-a-risque', 'Fichiers à risque' UNION ALL
  SELECT 'Tag automatique · Ressources humaines', 'Dossiers dont le chemin contient le mot RH.',
         'chemin:rh', 'Ressources humaines' UNION ALL
  SELECT 'Tag automatique · Finance', 'Dossiers dont le chemin contient le mot Finance.',
         'chemin:finance', 'Finance' UNION ALL
  SELECT 'Tag automatique · Juridique', 'Dossiers dont le chemin contient le mot Juridique.',
         'chemin:juridique', 'Juridique'
) seed
WHERE NOT EXISTS (SELECT 1 FROM governance_policies p WHERE p.name = seed.name);
