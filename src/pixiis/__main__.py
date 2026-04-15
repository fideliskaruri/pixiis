"""Pixiis entry point — unified game launcher & voice dashboard."""

from __future__ import annotations

import argparse
import logging
import os
import sys
import warnings

# Suppress noisy third-party messages before any imports
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")  # hide pygame hello
warnings.filterwarnings("ignore", category=DeprecationWarning, module="pkg_resources")

from pixiis import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pixiis",
        description="Unified game launcher & voice dashboard with controller support",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pixiis {__version__}",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--daemon",
        action="store_true",
        help="Run as background daemon only (tray icon, controller, voice — no UI window)",
    )
    mode.add_argument(
        "--ui",
        action="store_true",
        help="Open the dashboard UI (connects to running daemon)",
    )
    mode.add_argument(
        "--scan",
        action="store_true",
        help="Scan for installed games/apps and print results",
    )

    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config.toml (default: %%APPDATA%%/pixiis/config.toml)",
    )

    return parser


def cmd_scan() -> None:
    """One-shot library scan."""
    from pixiis.core import get_config
    from pixiis.library.registry import AppRegistry

    print(f"Pixiis v{__version__} — Scanning libraries...\n")
    config = get_config()
    registry = AppRegistry(config)
    apps = registry.scan_all()

    if not apps:
        print("No games or apps found.")
        print("Check that Steam/Xbox is installed, or add manual entries to config.")
        return

    # Group by source
    from collections import defaultdict
    by_source: dict[str, list] = defaultdict(list)
    for app in apps:
        by_source[app.source.value].append(app)

    for source, source_apps in sorted(by_source.items()):
        print(f"── {source.upper()} ({len(source_apps)}) ──")
        for app in sorted(source_apps, key=lambda a: a.name.lower()):
            icon = "✓" if app.icon_path else " "
            print(f"  [{icon}] {app.name}")
            if app.launch_command:
                print(f"      → {app.launch_command}")
        print()

    print(f"Total: {len(apps)} apps/games found.")


def cmd_daemon() -> None:
    """Run background daemon (tray icon, controller — no UI window)."""
    from pixiis.daemon import DaemonService

    svc = DaemonService()
    sys.exit(svc.start(show_ui=False))


def cmd_ui() -> None:
    """Open dashboard UI (connects to running daemon or starts one)."""
    from pixiis.daemon.ipc import DaemonIPC

    if DaemonIPC.is_running() is not None:
        resp = DaemonIPC.send_command("show")
        if resp is not None:
            return
        # Daemon lock exists but unresponsive — start fresh

    from pixiis.daemon import DaemonService

    svc = DaemonService()
    sys.exit(svc.start(show_ui=True))


def cmd_full() -> None:
    """Default: launch daemon + UI together."""
    from pixiis.daemon import DaemonService

    svc = DaemonService()
    sys.exit(svc.start(show_ui=True))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(message)s",
    )

    parser = build_parser()
    args = parser.parse_args()

    if args.scan:
        cmd_scan()
    elif args.daemon:
        cmd_daemon()
    elif args.ui:
        cmd_ui()
    else:
        cmd_full()


if __name__ == "__main__":
    main()
