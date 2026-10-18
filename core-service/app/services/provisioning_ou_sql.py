from __future__ import annotations


def effective_group_ou_case_sql() -> str:
    """SQL CASE expression used to resolve effective target OU for provisioning.

    Expected table aliases in caller query:
      - se  (storage_endpoints)
      - zpp (zone_provisioning_policy)
      - ids (identity_sources)
    """

    base_candidates = [
        "NULLIF(zpp.base_ou_dn, '')",
        "NULLIF(zpp.static_ou_dn, '')",
        "NULLIF(ids.default_group_ou_dn, '')",
    ]

    base_coalesce = ",\n                       ".join(base_candidates)

    return f"""
              CASE
                WHEN COALESCE(NULLIF(se.sub_ou_dn, ''), '') <> ''
                     AND INSTR(UPPER(se.sub_ou_dn), 'DC=') = 0
                     AND COALESCE(
                       {base_coalesce}
                     ) IS NOT NULL
                  THEN CONCAT(
                    TRIM(BOTH ',' FROM se.sub_ou_dn),
                    ',',
                    TRIM(
                      BOTH ',' FROM COALESCE(
                        {base_coalesce}
                      )
                    )
                  )
                ELSE COALESCE(
                  NULLIF(TRIM(BOTH ',' FROM se.sub_ou_dn), ''),
                  {base_coalesce}
                )
              END
    """.strip()
