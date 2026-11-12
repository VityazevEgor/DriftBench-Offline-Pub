"""DriftBench-Offline dataset generation package."""

import os
import sys

__version__ = "1.0.0"

if sys.platform == "win32":
    extra_paths = []
    user_path = os.environ.get("LOCALAPPDATA", "")
    if user_path:
        winget_pkgs = os.path.join(user_path, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_pkgs):
            for root, dirs, files in os.walk(winget_pkgs):
                if "helm.exe" in files or "kind.exe" in files:
                    extra_paths.append(root)
    docker_bin = r"C:\Program Files\Docker\Docker\resources\bin"
    if os.path.isdir(docker_bin):
        extra_paths.append(docker_bin)

    cur_path = os.environ.get("PATH", "")
    for p in extra_paths:
        if p not in cur_path:
            cur_path = f"{p};{cur_path}"
    os.environ["PATH"] = cur_path
