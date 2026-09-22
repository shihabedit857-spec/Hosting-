"""
SECURITY PACKAGE — Single entry point for all security layers.
═══════════════════════════════════════════════════════════════════
Usage:
    from security import (
        scan_source, scan_file_path, scan_zip_path,
        scan_directory_recursive,
        run_sandboxed, sandbox_status, install_hint,
        get_terminal, shutdown_terminal, shutdown_all_terminals,
        quota_bar, dir_size_mb,
        cleanup_all,
    )
═══════════════════════════════════════════════════════════════════
"""
from .guard import (
    scan_source,
    scan_file_path,
    scan_zip_path,
    scan_directory_recursive,
)

from .sandbox import (
    run_sandboxed,
    sandbox_status,
    install_hint,
    get_terminal,
    shutdown_terminal,
    shutdown_all_terminals,
    quota_bar,
    dir_size_mb,
    cleanup_all,
)

__all__ = [
    'scan_source', 'scan_file_path', 'scan_zip_path',
    'scan_directory_recursive',
    'run_sandboxed', 'sandbox_status', 'install_hint',
    'get_terminal', 'shutdown_terminal', 'shutdown_all_terminals',
    'quota_bar', 'dir_size_mb',
    'cleanup_all',
]
