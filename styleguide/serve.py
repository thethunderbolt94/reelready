#!/usr/bin/env python3
"""Open the ReelReady style guide: starts the Studio app on its Styles page (#styles).

    python3 styleguide/serve.py            # rebuild from styles/, serve, open the browser on #styles
    python3 styleguide/serve.py --no-open  # don't open a browser tab
    python3 styleguide/serve.py --port 4900

The style guide is one page of the Studio (studio/serve.py: Library, Review, Styles). This wrapper keeps the
old command working. Port comes from reelready.config.json (studio.port, default 4810); if the Studio is
already running it just opens that page. styleguide/build.py still builds styleguide/index.html.
"""
import importlib.util
import sys
from pathlib import Path

STUDIO = Path(__file__).resolve().parent.parent / "studio" / "serve.py"
spec = importlib.util.spec_from_file_location("reelready_studio", STUDIO)
studio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(studio)

if __name__ == "__main__":
    sys.exit(studio.main(sys.argv[1:], default_page="styles", label="Style guide"))
