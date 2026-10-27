"""Share identical files without mixing interpreter-specific package contents."""

import hashlib
import os
from pathlib import Path
import sys


def deduplicate(root):
    files = {}
    for packages in sorted(root.glob("python*")):
        for path in sorted(packages.rglob("*")):
            if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
                continue
            key = (path.relative_to(packages), hashlib.sha256(path.read_bytes()).digest())
            if key in files:
                target = os.path.relpath(files[key], path.parent)
                path.unlink()
                path.symlink_to(target)
            else:
                files[key] = path


if __name__ == "__main__":
    deduplicate(Path(sys.argv[1]))
