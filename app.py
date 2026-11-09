from pathlib import Path
import os

from runtime import create_app, read_settings
from project import SPEC, run

directory = Path(__file__).resolve().parent
app = create_app(SPEC, run, directory)

if __name__ == "__main__":
    settings = read_settings(directory)
    app.run(host="127.0.0.1", port=int(settings.get("PORT", "5050")), debug=False)
