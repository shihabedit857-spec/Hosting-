# Auto-loaded by Python when this dir is on PYTHONPATH
try:
    import fs_jail  # noqa: F401
except Exception as _e:
    import sys
    print(f"[APON-JAIL] load failed: {_e}", file=sys.stderr)
