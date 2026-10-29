"""Legacy smoke entry point; importing this module never contacts a provider."""

from scripts.live_api_smoke import main

if __name__ == "__main__":
    raise SystemExit(main())
