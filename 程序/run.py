"""平台入口：python run.py [--profile standalone|replset|shard] [--demo]"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from libplat.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
