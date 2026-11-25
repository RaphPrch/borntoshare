"""Entry point of the wizard as a single executable (PyInstaller): the same application as the container, its pages
and its SQL packs inside. Started by scripts/wizard-native.sh; WIZARD_PORT and SECRETS_DIR as with the container."""
import os

import uvicorn

from backend.app.main import app

if __name__ == "__main__":
    uvicorn.run(app, host=os.environ.get("WIZARD_HOST", "0.0.0.0"), port=int(os.environ.get("WIZARD_PORT", "8080")), log_level="info")
