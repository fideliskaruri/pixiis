"""Pixiis entry point — unified game launcher & voice dashboard."""

from __future__ import annotations

import argparse
import sys

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
    print("Library scan not yet implemented (Phase 3)")


def cmd_daemon() -> None:
    """Run background daemon."""
    print("Daemon mode not yet implemented (Phase 5)")


def cmd_ui() -> None:
    """Open dashboard UI."""
    from pixiis.ui import launch_ui

    launch_ui()


def cmd_full() -> None:
    """Default: launch daemon + UI together."""
    print(f"Pixiis v{__version__}")
    print("Full launch not yet implemented — use --scan, --daemon, or --ui")


def main() -> None:
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
