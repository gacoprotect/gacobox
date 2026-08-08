"""Real-time Rich terminal dashboard for the farm."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.text import Text

from providers.warp import Rotation

_STATUS_ICONS = {
    "idle": "[ ]",
    "registering": "[>]",
    "waiting_verify": "[?]",
    "verifying_otp": "[~]",
    "creating_key": "[*]",
    "success": "[OK]",
    "failed": "[!!]",
    "cooldown": "[z]",
}


@dataclass
class WorkerState:
    """Per-worker row shown in the dashboard."""

    worker_id: int
    status: str = "idle"
    email: str = ""
    error: str = ""
    started_at: float = 0.0
    done: bool = False
    note: str = ""

    @property
    def icon(self) -> str:
        if self.status.startswith("resend"):
            return "[@]"
        return _STATUS_ICONS.get(self.status, "❓")

    @property
    def elapsed(self) -> str:
        if not self.started_at:
            return "-"
        return f"{int(time.monotonic() - self.started_at)}s"


class FarmDashboard:
    """Thread-safe-ish Rich Live dashboard. Updates are pushed from the async loop."""

    def __init__(
        self,
        total: int,
        max_workers: int,
        provider: str = "",
        proxies: int = 0,
        warp: int = 0,
        warp_available: bool = True,
    ) -> None:
        self._total = total
        self._provider = provider
        self._proxies = proxies
        self._warp = warp
        self._warp_ip = ""
        self._warp_note = "" if warp_available else "warp-cli not installed"
        self._warp_style = "cyan" if warp_available else "bold red"
        self._success = 0
        self._failed = 0
        self._start: float = time.monotonic()
        self._console = Console()
        self._workers: dict[int, WorkerState] = {
            i: WorkerState(worker_id=i) for i in range(max_workers)
        }
        self._live: Live | None = None
        self._progress: Progress | None = None
        self._task: object = None

    def start(self) -> None:
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TextColumn("• [green]{task.fields[done]} done"),
            TextColumn("[red]{task.fields[failed]} failed"),
            TextColumn("• speed [cyan]{task.fields[speed]}"),
            TextColumn("ETA [yellow]{task.fields[eta]}"),
        )
        self._task = self._progress.add_task(
            "Farm", total=self._total, done=0, failed=0, speed="0/s", eta="?"
        )
        # Live must pull _build() on every tick; passing a static renderable
        # freezes elapsed timers between worker events.
        self._live = Live(
            get_renderable=self._build,
            console=self._console,
            refresh_per_second=4,
            screen=True,
        )
        self._live.start()

    def stop(self) -> None:
        if self._live:
            try:
                self._live.stop()
            except Exception:
                pass
            self._live = None

    def update_worker(self, worker_id: int, **changes: object) -> None:
        w = self._workers.get(worker_id)
        if w is None:
            return
        # A finished worker keeps its result until a new account claims the
        # slot, which only a new email signals. Without this the post-result
        # cooldown overwrote the success/failed status and cleared `done`, so
        # a completed run ended with every row reading "cooldown".
        if w.done and "email" not in changes:
            return
        for key, value in changes.items():
            if hasattr(w, key):
                setattr(w, key, value)
        w.done = False
        w.note = ""
        self._render()

    def worker_note(self, worker_id: int, note: str) -> None:
        """Show what a finished worker is waiting on, without clearing its result.

        `update_worker` deliberately ignores finished rows so the run does not
        end with every row reading "cooldown". Waiting on the WARP gate happens
        after the result is in, so it needs a channel that leaves `done` alone.
        """
        w = self._workers.get(worker_id)
        if w is None:
            return
        w.note = note
        self._render()

    def finish_worker(self, worker_id: int, *, success: bool, error: str = "") -> None:
        w = self._workers.get(worker_id)
        if w is None:
            return
        w.status = "success" if success else "failed"
        w.error = error
        w.done = True
        if success:
            self._success += 1
        else:
            self._failed += 1
        self._render()

    def _render(self) -> None:
        if self._live and self._progress and self._task is not None:
            elapsed = time.monotonic() - self._start
            done = self._success + self._failed
            speed = done / elapsed if elapsed > 0 else 0
            remaining = self._total - done
            eta = remaining / speed if speed > 0 else 0
            self._progress.update(
                self._task,
                completed=done,
                done=str(self._success),
                failed=str(self._failed),
                speed=f"{speed:.2f}/s",
                eta=f"{int(eta)}s" if eta else "?",
            )
            self._live.update(self._build())

    def _build(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(Panel(Group(self._progress, self._header()), border_style="blue"), size=5),
            Layout(self._workers_table()),
        )
        return layout

    def _header(self) -> Text:
        text = Text()
        text.append("  BLACKBOX.AI FARM  ", style="bold white on blue")
        text.append(f"  Total: {self._total}  ")
        text.append(f"Success: {self._success}  ", style="bold green")
        text.append(f"Failed: {self._failed}  ", style="bold red")
        if self._provider:
            text.append(f"Mail: {self._provider}  ", style="cyan")
        if self._proxies:
            text.append(f"Proxies: {self._proxies}  ", style="cyan")
        else:
            text.append("Proxies: none  ", style="yellow")
        if self._warp:
            label = self._warp_ip or "connecting"
            if self._warp_note:
                label += f" ({self._warp_note})"
            text.append(f"WARP-{self._warp}: {label}  ", style=self._warp_style)
        return text

    def warp_ip(self, ip: str) -> None:
        self._warp_ip = ip
        self._render()

    def warp_rotated(self, result: "Rotation") -> None:
        if result.ip:
            self._warp_ip = result.ip
        if result.fatal:
            self._warp_style = "bold red"
            self._warp_note = result.detail or "unavailable"
        elif result.moved:
            self._warp_style = "cyan"
            self._warp_note = ""
        else:
            # The tunnel still works, the egress just did not change, so the
            # run continues on an IP the site has already seen.
            self._warp_style = "yellow"
            self._warp_note = result.detail or "IP unchanged"
        self._render()

    def _workers_table(self) -> Table:
        table = Table(title="Workers", expand=True, header_style="bold magenta")
        table.add_column("ID", width=4, justify="center")
        table.add_column("Status", width=15, justify="center")
        table.add_column("Email", max_width=38)
        table.add_column("Elapsed", width=8, justify="right")
        table.add_column("Error", max_width=42, style="red")
        for w in self._workers.values():
            status = f"{w.icon} {w.status}"
            if w.note:
                status = f"[z] {w.note}"
            table.add_row(
                str(w.worker_id),
                status,
                w.email or "-",
                w.elapsed,
                w.error[:42] if w.error else "",
            )
        return table