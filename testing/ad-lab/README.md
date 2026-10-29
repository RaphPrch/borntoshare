# AD lab

Test Active Directory (Samba 4 AD DC) for end-to-end tests: `make ad-lab-up`, then `register.py`.
Never on a production host. Documentation: [docs/ad-lab.md](../../docs/ad-lab.md).

## Jeu de démonstration (tous les cas de figure)

`demo_seed.py` crée sous `\\\\adlab.example.test\\projects\\Demo` un dossier par situation, en passant par BornToShare
(demandes, approbations, worker) sauf ce qu'un administrateur ferait à la main sur le serveur :

| Dossier | Situation |
|---|---|
| Finance | conforme : groupes lecture et modification, membres, garants |
| Ressources humaines | conforme + une demande à décider |
| Juridique | accès se terminant dans 5 et 20 jours |
| Direction | héritage NTFS rompu (badge « Sans héritage »), conforme |
| Marketing (et Campagnes) | groupe AD posé à la main : écart à examiner ; sous-dossier gouverné |
| Achats | entrée hors BornToShare, acceptée |
| Comptabilité | ACE d'un groupe BornToShare retirée à la main |
| Archives 2019 | dossier supprimé sur le serveur : injoignable |
| Projets | gouverné, personne n'a encore accès |

```
podman run --rm --network <réseau> -e B2S_URL=http://frontend-service:3000 -e B2S_ORIGIN=https://<borntoshare> \
  -e B2S_USER=<admin local> -e B2S_PASSWORD_FILE=/run/pw -v <fichier du mot de passe>:/run/pw:ro,z \
  -v ./testing/ad-lab:/lab:ro,z --entrypoint python3 b2s-ad-lab:latest /lab/demo_seed.py --reset
```

`--reset` reconstruit le jeu, `--purge-e2e` retire les dossiers laissés par d'anciennes recettes.
`e2e_check.py` nettoie désormais ses dossiers à la fin (`E2E_KEEP=1` pour les garder).
