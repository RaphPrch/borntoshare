import subprocess
import os
from pathlib import Path
from tempfile import TemporaryDirectory

def test_kerberos(params: dict):
    principal = params["principal"]  # e.g. user or user@REALM (we accept both)
    password = params["password"]
    realm = params.get("realm")
    timeout = int(params.get("timeout", 7))

    princ = principal if ("@" in principal or not realm) else f"{principal}@{realm}"

    job_id = str(params.get("job_id") or "adhoc")
    with TemporaryDirectory(prefix=f"krb5cc_{job_id}_") as temp_dir:
        cache_path = Path(temp_dir) / "ccache"
        env = dict(os.environ)
        env["KRB5CCNAME"] = f"FILE:{cache_path}"
        try:
            subprocess.run(
                ["kinit", princ],
                input=password.encode(),
                capture_output=True,
                timeout=timeout,
                check=True,
                env=env,
            )
            return True, "Kerberos authentication successful", {"principal": princ}
        except subprocess.CalledProcessError as e:
            stderr = (e.stderr or b"").decode(errors="ignore")
            return False, "Kerberos authentication failed", {"principal": princ, "stderr": stderr[:4000]}
        except subprocess.TimeoutExpired:
            return False, "Kerberos timeout", {"principal": princ}
