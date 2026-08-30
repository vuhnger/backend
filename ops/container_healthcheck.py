import os
import sys
import urllib.request

HEALTH_URL_VARIABLE = "HEALTH_URL"
REQUEST_TIMEOUT_SECONDS = 4


def main() -> int:
    health_url = os.environ.get(HEALTH_URL_VARIABLE)
    if not health_url:
        return 0
    try:
        with urllib.request.urlopen(health_url, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            return 0 if response.status == 200 else 1
    except Exception:
        return 1


if __name__ == "__main__":
    sys.exit(main())
