"""Container healthcheck: the consumer loop touched the heartbeat file recently."""

from __future__ import annotations

import os
import sys
import time

MAX_AGE_SECONDS = 180


def main() -> int:
    path = os.environ.get("HEARTBEAT_FILE", "/tmp/queue-adapter.heartbeat")
    try:
        age = time.time() - os.stat(path).st_mtime
    except FileNotFoundError:
        print("no heartbeat yet")
        return 1
    if age > MAX_AGE_SECONDS:
        print(f"heartbeat stale ({int(age)}s)")
        return 1
    print(f"ok ({int(age)}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
