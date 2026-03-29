"""CLI entry point for sls-cli."""

from __future__ import annotations

from pathlib import Path

import click


# Well-known DLL locations per platform
_DEFAULT_DLL_PATHS = [
    # macOS (Steam)
    Path.home()
    / "Library/Application Support/Steam/steamapps/common"
    / "Slay the Spire 2/SlayTheSpire2.app/Contents/Resources"
    / "data_sts2_macos_arm64/sts2.dll",
    # Linux (Steam)
    Path.home()
    / ".steam/steam/steamapps/common/Slay the Spire 2"
    / "Slay the Spire 2_Data/Managed/sts2.dll",
    # Windows (Steam) — unlikely on this machine but for completeness
    Path("C:/Program Files (x86)/Steam/steamapps/common")
    / "Slay the Spire 2/Slay the Spire 2_Data/Managed/sts2.dll",
]


def _find_dll() -> Path | None:
    """Try to auto-detect the StS2 DLL location."""
    for p in _DEFAULT_DLL_PATHS:
        if p.is_file():
            return p
    return None


@click.group()
def main() -> None:
    """Slay the Spire 2 in your terminal."""


@main.command()
@click.argument("sts2_path", type=click.Path(exists=True), required=False)
@click.option(
    "-o", "--output",
    type=click.Path(),
    default=None,
    help="Output directory for game data (default: game_data/)",
)
@click.option(
    "--keep-decompiled",
    is_flag=True,
    default=False,
    help="Keep intermediate decompiled C# files (for debugging).",
)
def extract(sts2_path: str | None, output: str | None, keep_decompiled: bool) -> None:
    """Extract game data from your StS2 installation.

    STS2_PATH is the path to sts2.dll. If omitted, auto-detects from
    common Steam installation locations.
    """
    from sts2_tui.adapter.pipeline import extract_game_data

    if sts2_path is None:
        detected = _find_dll()
        if detected is None:
            raise click.ClickException(
                "Could not auto-detect sts2.dll. "
                "Please provide the path: sls-cli extract /path/to/sts2.dll"
            )
        sts2_path = str(detected)
        click.echo(f"Auto-detected DLL: {sts2_path}")

    click.echo(f"Extracting game data from: {sts2_path}")

    try:
        result_dir = extract_game_data(
            dll_path=sts2_path,
            output_dir=output,
            keep_decompiled=keep_decompiled,
        )
    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except RuntimeError as e:
        raise click.ClickException(f"Extraction failed:\n{e}")

    # Print summary
    import json

    manifest_path = result_dir / "manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text())
        click.echo(f"\nGame data written to: {result_dir}")
        for category, count in manifest.items():
            click.echo(f"  {category}: {count} entries")
    else:
        click.echo(f"Game data written to: {result_dir}")


@main.command()
def play() -> None:
    """Start a new run."""
    from sts2_tui.tui.app import SlsApp
    app = SlsApp()
    app.run()


if __name__ == "__main__":
    main()
