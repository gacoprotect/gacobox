"""Blackbox.ai Farm — TUI Menu Application."""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any

# Load .env file first
from dotenv import load_dotenv
load_dotenv()

# Force UTF-8 on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box

from config import Config
from dashboard import FarmDashboard
from exporter import export_all
from injector import inject_keys, find_9router_db, list_injected, remove_keys
from models import WORKING_MODELS, test_all, fetch_all_models
from providers.blackbox import AccountResult, BlackboxClient
from providers.tempmail import generate_email

STATE_FILE = "state.json"
console = Console()

# ─── Helpers ──────────────────────────────────────────────────────────

def generate_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))

def load_state(output_dir: str) -> dict[str, Any]:
    p = Path(output_dir) / STATE_FILE
    if not p.exists():
        return {"target": 0, "accounts": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"target": 0, "accounts": []}

def save_state(output_dir: str, state: dict[str, Any]) -> None:
    p = Path(output_dir) / STATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

def append_key(output_dir: str, record: dict[str, Any]) -> None:
    p = Path(output_dir) / "keys.txt"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{record['email']}:{record['password']}:{record['api_key']}\n")

def done_emails(state: dict[str, Any]) -> set[str]:
    return {a.get("email", "") for a in state.get("accounts", []) if a.get("success")}

def count_keys() -> int:
    p = Path("output/keys.txt")
    if not p.exists():
        return 0
    return len([l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()])

# ─── Key input helper ─────────────────────────────────────────────────

def get_key_input(prompt: str, default: str = "", width: int = 20) -> str:
    """Simple numbered/text input."""
    console.print(f"  {prompt} [{default}]: ", end="")
    try:
        val = input().strip()
    except (EOFError, KeyboardInterrupt):
        val = ""
    return val if val else default

def get_bool_input(prompt: str, default: bool = True) -> bool:
    """Toggle boolean."""
    label = "ON " if default else "OFF"
    console.print(f"  {prompt} [{label}] (space to toggle): ", end="")
    try:
        val = input().strip().lower()
    except (EOFError, KeyboardInterrupt):
        val = ""
    if val == "" or val == " ":
        return not default if val == " " else default
    return val in ("on", "yes", "true", "1")

def wait_key(prompt: str = "Press Enter to continue...") -> None:
    console.print(f"\n  {prompt}", end="")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

# ─── TUI Menus ────────────────────────────────────────────────────────

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def draw_header():
    console.print()
    console.print(Panel(
        Text("BLACKBOX FARM v2.0", style="bold cyan", justify="center"),
        subtitle=f"{count_keys()} keys harvested | 32 models",
        box=box.DOUBLE,
        width=50,
    ))

def main_menu() -> str | None:
    clear()
    draw_header()

    options = [
        ("Register Accounts", "reg"),
        ("Test Models", "test"),
        ("View Harvested Keys", "keys"),
        ("Export Keys", "export"),
        ("Inject to 9Router", "inject"),
        ("Run Status", "status"),
        ("Quit", "quit"),
    ]
    idx = 0

    while True:
        clear()
        draw_header()

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column("sel", style="bold cyan")
        table.add_column("opt")
        for i, (label, _) in enumerate(options):
            sel = ">>>" if i == idx else "  "
            style = "bold white" if i == idx else "dim"
            table.add_row(sel, Text(label, style=style))
        console.print(table)

        ch = _getch()
        if ch in ("up", "p"):
            idx = (idx - 1) % len(options)
        elif ch in ("down", "n"):
            idx = (idx + 1) % len(options)
        elif ch in ("enter",):
            return options[idx][1]
        elif ch in ("q", "escape"):
            return "quit"

def _getch() -> str:
    """Read a single keypress. Works on Windows + Unix."""
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            return {b"H": "up", b"P": "down", b"M": "right", b"K": "left"}.get(ch2, "")
        return ch.decode("utf-8", errors="replace") if ch else ""
    else:
        import tty, termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                ch2 = sys.stdin.read(1)
                ch3 = sys.stdin.read(1)
                return {"[A": "up", "[B": "down", "[C": "right", "[D": "left"}.get(ch2 + ch3, "")
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)

# ─── Register Menu ────────────────────────────────────────────────────

def menu_register():
    count = 10
    workers = 3
    headless = True
    domain = "catchmail.io"
    key_name = "auto-farm-key"

    while True:
        clear()
        console.print(Panel(Text("Register Accounts", style="bold cyan"), box=box.DOUBLE, width=50))

        state = load_state("output")
        done = len(done_emails(state))

        options = ["START (New)", "RESUME (Continue)", "Back"]
        idx = 0
        while True:
            clear()
            console.print(Panel(Text("Register Accounts", style="bold cyan"), box=box.DOUBLE, width=50))
            if done > 0:
                console.print(f"  [dim]Previous run: {done} accounts completed[/dim]\n")

            t = Table(box=box.SIMPLE, show_header=False)
            t.add_column("sel", style="bold cyan")
            t.add_column("field", style="bold")
            t.add_column("value")
            t.add_row("", "Count:", str(count))
            t.add_row("", "Workers:", str(workers))
            t.add_row("", "Headless:", "ON" if headless else "OFF")
            t.add_row("", "Domain:", domain)
            t.add_row("", "Key Name:", key_name)
            console.print(t)
            console.print()

            for i, o in enumerate(options):
                sel = ">>>" if i == idx else "  "
                console.print(f"  {sel} {o}")

            ch = _getch()
            if ch in ("up", "p"):
                idx = (idx - 1) % len(options)
            elif ch in ("down", "n"):
                idx = (idx + 1) % len(options)
            elif ch in ("enter",):
                if idx == 0:
                    _do_register(count, workers, headless, domain, key_name, resume=False)
                    return
                elif idx == 1:
                    if done == 0:
                        console.print("  [yellow]No previous accounts to resume.[/yellow]")
                        wait_key()
                    else:
                        _do_register(count, workers, headless, domain, key_name, resume=True)
                        return
                else:
                    return
            elif ch in ("q", "escape"):
                return
            elif ch in ("1", "2", "3", "4", "5"):
                field_idx = int(ch) - 1
                if field_idx == 0:
                    val = get_key_input("Count", str(count))
                    try: count = max(1, int(val))
                    except: pass
                elif field_idx == 1:
                    val = get_key_input("Workers", str(workers))
                    try: workers = max(1, int(val))
                    except: pass
                elif field_idx == 2:
                    headless = not headless
                elif field_idx == 3:
                    val = get_key_input("Domain", domain)
                    if val: domain = val
                elif field_idx == 4:
                    val = get_key_input("Key Name", key_name)
                    if val: key_name = val

def _do_register(count: int, workers: int, headless: bool, domain: str, key_name: str = "auto-farm-key", resume: bool = False):
    cfg = Config(
        max_workers=workers,
        headless=headless,
        tempmail_domain=domain,
        key_name=key_name,
    )
    state = load_state(cfg.output_dir)

    if resume:
        already = done_emails(state)
        remaining = max(0, count - len(already))
        if remaining == 0:
            console.print(f"  [yellow]All {count} accounts already done.[/yellow]")
            wait_key()
            return
        console.print(f"  [dim]Resuming: {len(already)} done, {remaining} to go[/dim]")
        count = remaining

    dashboard = FarmDashboard(total=count, max_workers=workers)
    dashboard.start()
    try:
        asyncio.run(_drive(cfg, count, dashboard, state))
    except KeyboardInterrupt:
        pass
    finally:
        dashboard.stop()
        accounts = state.get("accounts", [])
        ok = [a for a in accounts if a.get("success")]
        console.print(f"\n  Done: {len(ok)} succeeded, {len(accounts) - len(ok)} failed")
        wait_key()

async def _drive(cfg, count, dashboard, state):
    sem = asyncio.Semaphore(cfg.max_workers)
    launched = 0
    tasks = []
    skip = done_emails(state)  # Skip already done accounts

    async def _account(wid, email, password):
        async with sem:
            result = AccountResult(email=email, password=password)
            start = time.monotonic()
            client = None
            try:
                dashboard.update_worker(wid, status="registering", email=email)
                client = BlackboxClient(cfg)
                await client.start()
                api_key = await client.register_and_create_key(email, password)
                result.api_key = api_key
                result.success = True
                dashboard.update_worker(wid, status="done", email=email)
            except Exception as e:
                result.error = str(e)[:200]
                dashboard.update_worker(wid, status="failed", error=result.error)
            finally:
                if client:
                    try: await client.stop()
                    except: pass
                result.elapsed = time.monotonic() - start
                record = {"email": result.email, "password": result.password,
                         "api_key": result.api_key, "success": result.success,
                         "error": result.error, "elapsed": round(result.elapsed, 2)}
                state["accounts"].append(record)
                state["target"] = count
                save_state(cfg.output_dir, state)
                if result.api_key:
                    append_key(cfg.output_dir, record)

    while launched < count:
        email = generate_email(cfg.tempmail_domain)
        while email in skip:  # Skip if already registered
            email = generate_email(cfg.tempmail_domain)
        password = generate_password()
        tasks.append(asyncio.create_task(_account(launched % workers, email, password)))
        launched += 1
        await asyncio.sleep(secrets.SystemRandom().uniform(*cfg.delay_range))

    await asyncio.gather(*tasks, return_exceptions=True)

# ─── View Keys ────────────────────────────────────────────────────────

def menu_keys():
    clear()
    p = Path("output/keys.txt")
    console.print(Panel(Text("Harvested Keys", style="bold cyan"), box=box.DOUBLE, width=50))

    if not p.exists():
        console.print("  [dim]No keys found. Run register first.[/dim]")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    console.print(f"  Total: {len(lines)} keys\n")

    table = Table(box=box.SIMPLE, show_header=True)
    table.add_column("#", style="dim")
    table.add_column("Email")
    table.column("Email").overflow = "ellipsis"
    table.add_column("Key")
    table.column("Key").overflow = "ellipsis"

    for i, line in enumerate(lines[:50], 1):
        parts = line.split(":")
        if len(parts) >= 3:
            table.add_row(str(i), parts[0][:30], parts[2][:25] + "...")

    if len(lines) > 50:
        console.print(f"  ... and {len(lines) - 50} more")

    console.print(table)
    wait_key()

# ─── Test Models ──────────────────────────────────────────────────────

def menu_test():
    clear()
    console.print(Panel(Text("Test Models", style="bold cyan"), box=box.DOUBLE, width=50))

    # Get key from keys.txt or ask
    key = _first_key()
    if key:
        console.print(f"  Using key: {key[:20]}...")
    else:
        key = get_key_input("API Key")
        if not key:
            console.print("  [red]No key provided[/red]")
            wait_key()
            return

    console.print("  Testing 32 models... (this takes ~30 seconds)\n")
    try:
        results = asyncio.run(test_all(key, WORKING_MODELS[:32]))
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")
        wait_key()
        return

    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]

    table = Table(box=box.SIMPLE, show_header=True, title=f"Results: {len(ok)} OK / {len(fail)} FAIL")
    table.add_column("Status", style="bold")
    table.add_column("Model")
    for r in results:
        status = "[green]OK[/green]" if r.ok else "[red]ERR[/red]"
        table.add_row(status, r.model)

    console.print(table)

    # Save results
    Path("output").mkdir(exist_ok=True)
    Path("output/model_test.json").write_text(json.dumps({
        "ok": [r.model for r in ok],
        "fail": [{"model": r.model, "error": r.detail} for r in fail],
    }, indent=2), encoding="utf-8")

    wait_key()

# ─── Export ────────────────────────────────────────────────────────────

def menu_export():
    clear()
    console.print(Panel(Text("Export Keys", style="bold cyan"), box=box.DOUBLE, width=50))

    state = load_state("output")
    accounts = [a for a in state.get("accounts", []) if a.get("api_key")]
    if not accounts:
        console.print("  [dim]No successful accounts to export.[/dim]")
        wait_key()
        return

    options = ["TXT", "JSON", "CSV", "ALL formats", "Back"]
    idx = 0

    while True:
        clear()
        console.print(Panel(Text("Export Keys", style="bold cyan"), box=box.DOUBLE, width=50))
        console.print(f"  {len(accounts)} accounts ready\n")
        for i, o in enumerate(options):
            sel = ">>>" if i == idx else "  "
            console.print(f"  {sel} {o}")

        ch = _getch()
        if ch in ("up", "p"): idx = (idx - 1) % len(options)
        elif ch in ("down", "n"): idx = (idx + 1) % len(options)
        elif ch in ("enter",):
            if idx == 4: return
            written = export_all("output", accounts)
            for fmt, path in written.items():
                console.print(f"  [green]{fmt.upper()}[/green] -> {path}")
            wait_key()
            return
        elif ch in ("q", "escape"): return

# ─── Inject to 9Router ────────────────────────────────────────────────

def menu_inject():
    clear()
    console.print(Panel(Text("Inject to 9Router", style="bold cyan"), box=box.DOUBLE, width=50))

    db = find_9router_db()
    if db:
        console.print(f"  [green]Found 9Router DB:[/green] {db}")
    else:
        console.print("  [red]Provider DB not found![/red]")
        console.print("  Searched locations:")
        for p in _discover_db_paths():
            console.print(f"    {p}")
        console.print("\n  Set PROVIDER_DB_PATH env var or pass --db-path.")
        wait_key()
        return

    # Check keys
    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  [dim]No keys to inject. Run register first.[/dim]")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    console.print(f"  Keys to inject: {len(lines)}")

    # Check existing
    existing = list_injected(str(db))
    console.print(f"  Already in 9Router: {len(existing)}")

    options = ["INJECT", "VIEW injected keys", "REMOVE all blackbox keys", "Back"]
    idx = 0

    while True:
        clear()
        console.print(Panel(Text("Inject to 9Router", style="bold cyan"), box=box.DOUBLE, width=50))
        console.print(f"  DB: {db}")
        console.print(f"  Keys ready: {len(lines)}")
        console.print(f"  Already injected: {len(existing)}\n")

        for i, o in enumerate(options):
            sel = ">>>" if i == idx else "  "
            console.print(f"  {sel} {o}")

        ch = _getch()
        if ch in ("up", "p"): idx = (idx - 1) % len(options)
        elif ch in ("down", "n"): idx = (idx + 1) % len(options)
        elif ch in ("enter",):
            if idx == 0:  # INJECT
                try:
                    count = inject_keys("output/keys.txt", str(db))
                    console.print(f"\n  [green]Injected {count} new keys![/green]")
                    existing = list_injected(str(db))
                except Exception as e:
                    console.print(f"\n  [red]Error: {e}[/red]")
                wait_key()
            elif idx == 1:  # VIEW
                clear()
                console.print(Panel(Text("Injected Keys in 9Router", style="bold cyan"), box=box.DOUBLE, width=50))
                existing = list_injected(str(db))
                if not existing:
                    console.print("  [dim]No blackbox keys in 9Router.[/dim]")
                else:
                    table = Table(box=box.SIMPLE, show_header=True)
                    table.add_column("#", style="dim")
                    table.add_column("ID")
                    table.add_column("Email")
                    table.add_column("Status")
                    for i, row in enumerate(existing, 1):
                        table.add_row(str(i), row.get("id", "")[:20], row.get("email", "")[:25], row.get("status", ""))
                    console.print(table)
                wait_key()
            elif idx == 2:  # REMOVE
                count = remove_keys(str(db))
                console.print(f"\n  [yellow]Removed {count} blackbox keys from 9Router.[/yellow]")
                existing = list_injected(str(db))
                wait_key()
            elif idx == 3:  # BACK
                return
        elif ch in ("q", "escape"): return

import os
from injector import _discover_db_paths

# ─── Status ────────────────────────────────────────────────────────────

def menu_status():
    clear()
    console.print(Panel(Text("Run Status", style="bold cyan"), box=box.DOUBLE, width=50))

    state = load_state("output")
    accounts = state.get("accounts", [])
    ok = [a for a in accounts if a.get("success")]
    failed = [a for a in accounts if not a.get("success")]

    table = Table(box=box.SIMPLE, show_header=False)
    table.add_column("field", style="bold")
    table.add_column("value")
    table.add_row("Target:", str(state.get("target", 0)))
    table.add_row("Success:", f"[green]{len(ok)}[/green]")
    table.add_row("Failed:", f"[red]{len(failed)}[/red]")
    table.add_row("Keys on disk:", str(count_keys()))
    console.print(table)

    if failed:
        console.print("\n  [bold]Recent failures:[/bold]")
        for a in failed[-5:]:
            console.print(f"    [red]{a.get('email', '?')[:30]}[/red]: {a.get('error', '?')[:60]}")

    wait_key()

def _first_key() -> str:
    p = Path("output/keys.txt")
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[2].strip():
            return parts[2].strip()
    return ""

# ─── Main Loop ─────────────────────────────────────────────────────────

def main():
    try:
        while True:
            choice = main_menu()
            if choice is None or choice == "quit":
                clear()
                console.print("  [bold cyan]Goodbye![/bold cyan]\n")
                break
            elif choice == "reg":
                menu_register()
            elif choice == "test":
                menu_test()
            elif choice == "keys":
                menu_keys()
            elif choice == "export":
                menu_export()
            elif choice == "inject":
                menu_inject()
            elif choice == "status":
                menu_status()
    except KeyboardInterrupt:
        clear()
        console.print("\n  [bold cyan]Goodbye![/bold cyan]\n")

if __name__ == "__main__":
    main()
