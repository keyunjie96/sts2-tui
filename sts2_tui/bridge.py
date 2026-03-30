"""EngineBridge — async subprocess bridge to the sts2-cli headless engine.

Communicates with the real STS2 game engine via a JSON-line protocol over
stdin/stdout of a .NET subprocess.  All I/O is offloaded to a background
thread so the Textual event loop is never blocked.

Protocol reference
------------------
Start process → read ``{"type": "ready", ...}``
Send ``{"cmd": "start_run", ...}`` → read state
Send ``{"cmd": "action", "action": "<name>", "args": {...}}`` → read state
Send ``{"cmd": "quit"}`` → process exits

See ``sts2-cli-engine/python/play_full_run.py`` for the canonical client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

# Where we expect sts2-cli to live, in priority order.
_STS2_CLI_SEARCH_PATHS: list[Path] = [
    Path(__file__).resolve().parent.parent / "deps" / "sts2-cli",  # deps/sts2-cli inside repo
    Path(__file__).resolve().parent.parent.parent / "sts2-cli",  # sibling project (../sts2-cli)
]


def _find_sts2_cli_dir() -> Path:
    """Locate the sts2-cli project root.

    Search order:
    1. ``STS2_CLI_PATH`` environment variable
    2. ``./sts2-cli-engine/`` relative to repo root
    3. ``/tmp/sts2-cli``
    """
    env = os.environ.get("STS2_CLI_PATH")
    if env:
        p = Path(env)
        if p.is_dir():
            return p

    for candidate in _STS2_CLI_SEARCH_PATHS:
        if candidate.is_dir():
            return candidate

    raise FileNotFoundError(
        "Cannot locate sts2-cli directory.  "
        "Set the STS2_CLI_PATH environment variable or place it at ./sts2-cli-engine/"
    )


def _find_dotnet() -> str:
    """Locate a working ``dotnet`` binary."""
    candidates = [
        os.path.expanduser("~/.dotnet-arm64/dotnet"),
        os.path.expanduser("~/.dotnet/dotnet"),
        "dotnet",
    ]
    for p in candidates:
        try:
            r = subprocess.run(
                [p, "--version"], capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    raise FileNotFoundError(
        ".NET SDK not found.  Install .NET 9+ from https://dotnet.microsoft.com/download"
    )


def _find_game_dir() -> str | None:
    """Auto-detect the STS2 Steam install (used for runtime DLL resolution)."""
    system = platform.system()
    candidates: list[str] = []
    if system == "Darwin":
        base = os.path.expanduser(
            "~/Library/Application Support/Steam/steamapps/common/"
            "Slay the Spire 2/SlayTheSpire2.app/Contents/Resources"
        )
        candidates = [
            os.path.join(base, "data_sts2_macos_arm64"),
            os.path.join(base, "data_sts2_macos_x86_64"),
        ]
    elif system == "Linux":
        for steam in ["~/.steam/steam", "~/.local/share/Steam"]:
            candidates.append(
                os.path.expanduser(f"{steam}/steamapps/common/Slay the Spire 2")
            )
    elif system == "Windows":
        candidates = [r"C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2"]

    for d in candidates:
        if os.path.isdir(d):
            return d
    return None


# ---------------------------------------------------------------------------
# BridgeError
# ---------------------------------------------------------------------------


class BridgeError(Exception):
    """Raised when the sts2-cli process returns an error or crashes."""


# ---------------------------------------------------------------------------
# EngineBridge
# ---------------------------------------------------------------------------


class EngineBridge:
    """Async bridge to a sts2-cli subprocess.

    All public methods are coroutines safe to call from Textual's event loop.
    Blocking subprocess I/O is performed on a dedicated daemon thread.

    Typical usage::

        bridge = EngineBridge()
        ready = await bridge.start()
        state = await bridge.start_run("Ironclad", seed="42")
        state = await bridge.play_card(0, target=0)
        state = await bridge.end_turn()
        await bridge.quit()
    """

    def __init__(self) -> None:
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()  # guards _proc stdin/stdout
        self._sts2_dir: Path | None = None
        self._dotnet: str | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> dict[str, Any]:
        """Start (or restart) the sts2-cli process.

        Returns the ``{"type": "ready", "version": "..."}`` handshake.
        """
        # Tear down any previous process.
        if self._proc is not None:
            await self._stop_process()

        self._sts2_dir = await asyncio.to_thread(_find_sts2_cli_dir)
        self._dotnet = await asyncio.to_thread(_find_dotnet)

        # Ensure the project is built.
        await self._ensure_built()

        # Spawn the subprocess.
        project_csproj = str(
            self._sts2_dir / "src" / "Sts2Headless" / "Sts2Headless.csproj"
        )
        env = {**os.environ}
        game_dir = _find_game_dir()
        if game_dir:
            env["STS2_GAME_DIR"] = game_dir
        env.setdefault("STS2_GAME_DIR", str(self._sts2_dir / "lib"))

        self._proc = subprocess.Popen(
            [self._dotnet, "run", "--no-build", "--project", project_csproj],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
            cwd=str(self._sts2_dir),
            env=env,
        )

        ready = await self._read_json_line()
        if ready.get("type") != "ready":
            raise BridgeError(f"Expected ready message, got: {ready}")
        log.info("sts2-cli ready: %s", ready)
        return ready

    async def quit(self) -> None:
        """Send the quit command and terminate the process."""
        if self._proc is None:
            return
        try:
            await self._send_raw({"cmd": "quit"})
        except Exception:
            pass
        await self._stop_process()

    def is_running(self) -> bool:
        """Return ``True`` if the subprocess is alive."""
        return self._proc is not None and self._proc.poll() is None

    # ------------------------------------------------------------------
    # High-level commands
    # ------------------------------------------------------------------

    async def send(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Send an arbitrary command dict and return the parsed response.

        Raises :class:`BridgeError` on protocol errors or process death.
        """
        resp = await self._send_and_read(cmd)
        if resp.get("type") == "error":
            raise BridgeError(resp.get("message", "unknown engine error"))
        return resp

    async def start_run(
        self,
        character: str = "Ironclad",
        seed: str | None = None,
        ascension: int = 0,
        *,
        lang: str = "en",
        god_mode: bool = False,
    ) -> dict[str, Any]:
        """Start a new run and return the first decision state."""
        cmd: dict[str, Any] = {
            "cmd": "start_run",
            "character": character,
            "ascension": ascension,
            "lang": lang,
            "god_mode": god_mode,
        }
        if seed is not None:
            cmd["seed"] = seed
        return await self.send(cmd)

    async def play_card(
        self, index: int, target: int | None = None
    ) -> dict[str, Any]:
        """Play a card from the hand (0-indexed)."""
        args: dict[str, Any] = {"card_index": index}
        if target is not None:
            args["target_index"] = target
        return await self.send(
            {"cmd": "action", "action": "play_card", "args": args}
        )

    async def end_turn(self) -> dict[str, Any]:
        """End the player's turn."""
        return await self.send({"cmd": "action", "action": "end_turn"})

    async def choose(self, index: int) -> dict[str, Any]:
        """Choose an option (event, rest site, etc.) by index."""
        return await self.send(
            {
                "cmd": "action",
                "action": "choose_option",
                "args": {"option_index": index},
            }
        )

    async def select_map_node(self, col: int, row: int) -> dict[str, Any]:
        """Select a map node to travel to."""
        return await self.send(
            {
                "cmd": "action",
                "action": "select_map_node",
                "args": {"col": col, "row": row},
            }
        )

    async def select_card_reward(self, index: int) -> dict[str, Any]:
        """Pick a card from the reward screen."""
        return await self.send(
            {
                "cmd": "action",
                "action": "select_card_reward",
                "args": {"card_index": index},
            }
        )

    async def skip_card_reward(self) -> dict[str, Any]:
        """Skip the card reward."""
        return await self.send(
            {"cmd": "action", "action": "skip_card_reward"}
        )

    async def collect_potion_reward(self, potion_index: int) -> dict[str, Any]:
        """Collect a potion from the reward screen."""
        return await self.send(
            {
                "cmd": "action",
                "action": "collect_potion_reward",
                "args": {"potion_index": potion_index},
            }
        )

    async def discard_potion_for_reward(
        self, discard_index: int, potion_index: int
    ) -> dict[str, Any]:
        """Discard a belt potion and collect a reward potion."""
        return await self.send(
            {
                "cmd": "action",
                "action": "discard_potion_for_reward",
                "args": {
                    "discard_index": discard_index,
                    "potion_index": potion_index,
                },
            }
        )

    async def skip_potion_reward(self, potion_index: int | None = None) -> dict[str, Any]:
        """Skip one or all pending potion rewards."""
        args: dict[str, Any] = {}
        if potion_index is not None:
            args["potion_index"] = potion_index
        return await self.send(
            {"cmd": "action", "action": "skip_potion_reward", "args": args}
        )

    async def use_potion(
        self, index: int, target: int | None = None
    ) -> dict[str, Any]:
        """Use a potion at *index*, optionally targeting a monster."""
        args: dict[str, Any] = {"potion_index": index}
        if target is not None:
            args["target_index"] = target
        return await self.send(
            {"cmd": "action", "action": "use_potion", "args": args}
        )

    async def proceed(self) -> dict[str, Any]:
        """Send a generic ``proceed`` action (advance past non-interactive states)."""
        return await self.send({"cmd": "action", "action": "proceed"})

    async def leave_room(self) -> dict[str, Any]:
        """Leave the current room (shop, event after choosing, etc.)."""
        return await self.send({"cmd": "action", "action": "leave_room"})

    async def get_state(self) -> dict[str, Any]:
        """Request the current game state.

        Note: the engine currently responds with the last decision state
        when the ``action`` ``proceed`` is sent, but there is no
        dedicated ``state`` command.  We use ``proceed`` as a proxy
        and return whatever the engine responds with.
        """
        # The sts2-cli protocol does not have a standalone "get state"
        # command, but sending proceed at a decision point returns the
        # current state.
        return await self.send({"cmd": "action", "action": "proceed"})

    async def get_map(self) -> dict[str, Any]:
        """Fetch the full map data."""
        return await self.send({"cmd": "get_map"})

    async def select_bundle(self, index: int) -> dict[str, Any]:
        """Select a card bundle (Neow's Scroll Boxes, etc.)."""
        return await self.send(
            {
                "cmd": "action",
                "action": "select_bundle",
                "args": {"bundle_index": index},
            }
        )

    async def select_cards(self, indices: str) -> dict[str, Any]:
        """Select cards by comma-separated indices (card select decisions)."""
        return await self.send(
            {
                "cmd": "action",
                "action": "select_cards",
                "args": {"indices": indices},
            }
        )

    async def skip_select(self) -> dict[str, Any]:
        """Skip a card selection decision."""
        return await self.send({"cmd": "action", "action": "skip_select"})

    # ------------------------------------------------------------------
    # Internal I/O (runs in background threads)
    # ------------------------------------------------------------------

    async def _send_and_read(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Write *cmd* as a JSON line and read the JSON response.

        All blocking I/O is done on a thread via :func:`asyncio.to_thread`.
        """
        return await asyncio.to_thread(self._send_and_read_sync, cmd)

    def _send_and_read_sync(self, cmd: dict[str, Any]) -> dict[str, Any]:
        """Thread-safe: write a command and return the response dict."""
        with self._lock:
            self._write_line_sync(cmd)
            return self._read_json_line_sync()

    async def _send_raw(self, cmd: dict[str, Any]) -> None:
        """Write a command without waiting for a response."""
        await asyncio.to_thread(self._write_line_sync, cmd)

    def _write_line_sync(self, cmd: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.poll() is not None:
            raise BridgeError("sts2-cli process is not running")
        line = json.dumps(cmd)
        log.debug("bridge > %s", line[:300])
        try:
            proc.stdin.write(line + "\n")  # type: ignore[union-attr]
            proc.stdin.flush()  # type: ignore[union-attr]
        except (BrokenPipeError, OSError) as exc:
            raise BridgeError(f"Failed to write to sts2-cli: {exc}") from exc

    async def _read_json_line(self, timeout: float = 30.0) -> dict[str, Any]:
        """Read one JSON line from stdout (skipping non-JSON lines).

        Raises BridgeError if no response within *timeout* seconds.
        """
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._read_json_line_sync),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            raise BridgeError(
                f"sts2-cli: no response within {timeout}s (engine likely stuck). "
                "Try pressing Esc to go back."
            )

    def _read_json_line_sync(self) -> dict[str, Any]:
        """Blocking: read lines until we get valid JSON."""
        proc = self._proc
        if proc is None:
            raise BridgeError("sts2-cli process is not running")
        while True:
            raw = proc.stdout.readline()  # type: ignore[union-attr]
            if not raw:
                # EOF — process likely crashed.
                # stderr is DEVNULL to avoid pipe deadlocks, so no snippet.
                exit_code = proc.poll()
                crash_msg = (
                    f"sts2-cli crashed (exit code {exit_code})\n"
                )
                try:
                    crash_log = Path.home() / ".sts2-tui-crash.log"
                    # Rotate: if log exceeds 1 MB, truncate to last 500 KB
                    _MAX_LOG_SIZE = 1_048_576   # 1 MB
                    _KEEP_TAIL = 524_288        # 500 KB
                    try:
                        if crash_log.is_file() and crash_log.stat().st_size > _MAX_LOG_SIZE:
                            data = crash_log.read_bytes()
                            crash_log.write_bytes(data[-_KEEP_TAIL:])
                    except Exception:
                        pass  # best-effort rotation
                    with open(crash_log, "a") as f:
                        from datetime import datetime
                        f.write(f"\n--- {datetime.now().isoformat()} ---\n")
                        f.write(crash_msg)
                    log.error("Crash report written to %s", crash_log)
                except Exception:
                    pass
                raise BridgeError(
                    f"sts2-cli: EOF on stdout (exit code {exit_code}). "
                    f"Crash log: ~/.sts2-tui-crash.log"
                )
            line = raw.strip()
            if line.startswith("{"):
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise BridgeError(
                        f"sts2-cli: invalid JSON on stdout: {exc}  line: {line[:200]}"
                    ) from exc
                log.debug("bridge < type=%s decision=%s", resp.get("type"), resp.get("decision"))
                return resp
            # Skip build warnings, .NET banner lines, etc.
            log.debug("bridge [skip] %s", line[:120])

    # ------------------------------------------------------------------
    # Build helpers
    # ------------------------------------------------------------------

    async def _ensure_built(self) -> None:
        """Build the C# project if not already compiled."""
        assert self._sts2_dir is not None
        assert self._dotnet is not None

        lib_dll = self._sts2_dir / "lib" / "sts2.dll"
        if not lib_dll.is_file():
            raise BridgeError(
                f"sts2-cli lib not found at {lib_dll}.  "
                "Run setup.sh in the sts2-cli directory first."
            )

        exe_dll = (
            self._sts2_dir
            / "src"
            / "Sts2Headless"
            / "bin"
            / "Debug"
            / "net9.0"
            / "Sts2Headless.dll"
        )
        if exe_dll.is_file() and exe_dll.stat().st_mtime >= lib_dll.stat().st_mtime:
            return  # Already built and up-to-date.

        log.info("Building sts2-cli ...")
        project_csproj = str(
            self._sts2_dir / "src" / "Sts2Headless" / "Sts2Headless.csproj"
        )
        result = await asyncio.to_thread(
            subprocess.run,
            [self._dotnet, "build", project_csproj],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(self._sts2_dir),
        )
        if result.returncode != 0:
            raise BridgeError(
                f"sts2-cli build failed (exit {result.returncode}):\n{result.stderr[:1000]}"
            )
        log.info("sts2-cli build succeeded")

    # ------------------------------------------------------------------
    # Process cleanup
    # ------------------------------------------------------------------

    async def _stop_process(self) -> None:
        """Terminate and reap the subprocess."""
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        try:
            proc.terminate()
            await asyncio.to_thread(proc.wait, timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> EngineBridge:
        await self.start()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.quit()
