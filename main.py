"""Blackbox.ai Farm — Modern TUI Application."""
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
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich import box
from rich.style import Style

from config import Config
from dashboard import FarmDashboard
from exporter import export_all
from injector import inject_keys, find_9router_db, list_injected, remove_keys
from models import WORKING_MODELS, test_all
from providers.blackbox import AccountResult, BlackboxClient
from providers.tempmail import generate_email

STATE_FILE = "state.json"
console = Console()

# ─── Color Theme ──────────────────────────────────────────────────────

class Theme:
    """Modern color theme."""
    PRIMARY = "cyan"
    SUCCESS = "green"
    WARNING = "yellow"
    ERROR = "red"
    DIM = "dim white"
    BOLD = "bold white"
    ACCENT = "bold cyan"
    HEADER_BG = "on dark_blue"
    MENU_SEL = "bold cyan on grey11"
    MENU_DIM = "grey50"

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

def _first_key() -> str:
    p = Path("output/keys.txt")
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8").splitlines():
        parts = line.split(":")
        if len(parts) >= 3 and parts[2].strip():
            return parts[2].strip()
    return ""

def wait_key(prompt: str = "Press Enter to continue...") -> None:
    console.print(f"\n  [dim]{prompt}[/dim]", end="")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

def clear():
    os.system("cls" if os.name == "nt" else "clear")

# ─── Modern UI Components ─────────────────────────────────────────────

def draw_banner():
    """Draw modern banner."""
    banner = """
  ╔═══════════════════════════════════════════════════╗
  ║                                                   ║
  ║   ██████╗ ██████╗ ██╗██╗   ██╗███████╗███████╗  ║
  ║  ██╔════╝██╔═══██╗██║██║   ██║██╔════╝██╔════╝  ║
  ║  ██║     ██║   ██║██║██║   ██║█████╗  ███████╗  ║
  ║  ██║     ██║   ██║██║╚██╗ ██╔╝██╔══╝  ╚════██║  ║
  ║  ╚██████╗╚██████╔╝██║ ╚████╔╝ ███████╗███████║  ║
  ║   ╚═════╝ ╚═════╝ ╚═╝  ╚═══╝  ╚══════╝╚══════╝  ║
  ║                                                   ║
  ║   [bold cyan]AI Model Farm Tool[/bold cyan]                          ║
  ║   [dim]v2.1 — 32 Free Models[/dim]                      ║
  ║                                                   ║
  ╚═══════════════════════════════════════════════════╝
"""
    console.print(banner, style="white")

def draw_status_bar():
    """Draw status bar with key count."""
    keys = count_keys()
    db = find_9router_db()
    db_status = "[green]Connected[/green]" if db else "[red]Not found[/red]"
    console.print(f"  [dim]Keys: [bold]{keys}[/bold] | DB: {db_status}[/dim]\n")

def draw_menu(options: list[tuple[str, str, str]], selected: int = -1):
    """Draw modern menu with descriptions."""
    for i, (num, title, desc) in enumerate(options):
        if i == selected:
            console.print(f"  [bold white on grey11]  {num}  {title:<20}[/bold white on grey11] [dim]{desc}[/dim]")
        else:
            console.print(f"  [cyan]{num}[/cyan]  [white]{title}[/white]  [dim]{desc}[/dim]")
    console.print()

def prompt_input(label: str, default: str = "", password: bool = False) -> str:
    """Modern input prompt."""
    default_str = f" [dim]({default})[/dim]" if default else ""
    try:
        val = input(f"  [cyan]→[/cyan] {label}{default_str}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return default
    return val if val else default

def prompt_choice(label: str, options: list[str], default: int = 0) -> str:
    """Choice prompt with numbered options."""
    console.print(f"\n  [bold]{label}[/bold]")
    for i, opt in enumerate(options, 1):
        marker = "[bold cyan]>[/bold cyan]" if i - 1 == default else " "
        console.print(f"  {marker} [cyan]{i}[/cyan] {opt}")
    try:
        raw = input("\n  [cyan]→[/cyan] Pilih: ").strip()
    except (EOFError, KeyboardInterrupt):
        return options[default]
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return options[default]

# ─── Main Menu ────────────────────────────────────────────────────────

def main_menu() -> str | None:
    """Modern main menu."""
    clear()
    draw_banner()
    draw_status_bar()

    options = [
        ("1", "Register", "Buat akun baru & harvest API keys"),
        ("2", "Test Models", "Cek model mana yang work"),
        ("3", "View Keys", "Lihat semua API keys"),
        ("4", "Export", "Export keys ke file"),
        ("5", "Inject 9Router", "Masukkan keys ke 9Router DB"),
        ("6", "Status", "Lihat status terakhir"),
        ("7", "Quit", "Keluar dari aplikasi"),
    ]

    draw_menu(options)

    try:
        raw = input("  [cyan]→[/cyan] Pilih [1-7]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return "quit"

    if raw in ("1", "reg"):
        return "reg"
    elif raw in ("2", "test"):
        return "test"
    elif raw in ("3", "keys"):
        return "keys"
    elif raw in ("4", "export"):
        return "export"
    elif raw in ("5", "inject"):
        return "inject"
    elif raw in ("6", "status"):
        return "status"
    elif raw in ("7", "q", "x", "quit"):
        return "quit"
    return None

# ─── Register Menu ────────────────────────────────────────────────────

def menu_register():
    """Modern register menu."""
    count = 10
    workers = 3
    headless = True
    domain = "catchmail.io"

    state = load_state("output")
    done = len(done_emails(state))

    while True:
        clear()
        console.print(Panel(
            Text("Register New Accounts", style="bold cyan"),
            box=box.ROUNDED,
            width=50,
        ))

        if done > 0:
            console.print(f"  [dim]Previously completed: {done} accounts[/dim]\n")

        # Settings display
        table = Table(box=None, show_header=False, padding=(0, 2))
        table.add_column("key", style="dim")
        table.add_column("val", style="bold")
        table.add_row("Count:", str(count))
        table.add_row("Workers:", str(workers))
        table.add_row("Headless:", "ON" if headless else "OFF")
        table.add_row("Domain:", domain)
        console.print(table)
        console.print()

        # Menu
        console.print("  [cyan]1[/cyan]  [bold]START[/bold] — Register baru")
        if done > 0:
            console.print("  [cyan]2[/cyan]  [bold]RESUME[/bold] — Lanjut dari sebelumnya")
        console.print("  [cyan]3[/cyan]  Edit Count")
        console.print("  [cyan]4[/cyan]  Edit Workers")
        console.print("  [cyan]5[/cyan]  Toggle Headless")
        console.print("  [cyan]6[/cyan]  Edit Domain")
        console.print("  [cyan]7[/cyan]  Back")
        console.print()

        try:
            raw = input("  [cyan]→[/cyan] Pilih: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "1":
            _do_register(count, workers, headless, domain, resume=False)
            return
        elif raw == "2" and done > 0:
            _do_register(count, workers, headless, domain, resume=True)
            return
        elif raw == "3":
            val = prompt_input("Count", str(count))
            if val.isdigit(): count = max(1, int(val))
        elif raw == "4":
            val = prompt_input("Workers", str(workers))
            if val.isdigit(): workers = max(1, int(val))
        elif raw == "5":
            headless = not headless
        elif raw == "6":
            val = prompt_input("Domain", domain)
            if val: domain = val
        elif raw in ("7", "q", "x", "b"):
            return

def _do_register(count: int, workers: int, headless: bool, domain: str, resume: bool = False):
    cfg = Config(max_workers=workers, headless=headless, tempmail_domain=domain)
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
        console.print(f"\n  [green]Done: {len(ok)} succeeded, {len(accounts) - len(ok)} failed[/green]")

        # Auto-inject keys to 9Router
        if ok:
            db = find_9router_db()
            if db:
                try:
                    injected = inject_keys("output/keys.txt", str(db))
                    console.print(f"  [green]Auto-injected {injected} keys to 9Router![/green]")
                except Exception as e:
                    console.print(f"  [yellow]Auto-inject failed: {e}[/yellow]")
            else:
                console.print("  [dim]9Router DB not found, skipping auto-inject.[/dim]")

        wait_key()

async def _drive(cfg, count, dashboard, state):
    sem = asyncio.Semaphore(cfg.max_workers)
    launched = 0
    tasks = []
    skip = done_emails(state)

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
        while email in skip:
            email = generate_email(cfg.tempmail_domain)
        password = generate_password()
        tasks.append(asyncio.create_task(_account(launched % cfg.max_workers, email, password)))
        launched += 1
        await asyncio.sleep(secrets.SystemRandom().uniform(*cfg.delay_range))

    await asyncio.gather(*tasks, return_exceptions=True)

# ─── View Keys ────────────────────────────────────────────────────────

def menu_keys():
    """View harvested keys."""
    clear()
    console.print(Panel(
        Text("Harvested API Keys", style="bold cyan"),
        box=box.ROUNDED,
        width=50,
    ))

    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  [dim]No keys found. Run register first.[/dim]")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    console.print(f"  [bold]Total: {len(lines)} keys[/bold]\n")

    table = Table(box=box.SIMPLE_HEAVY, show_header=True)
    table.add_column("#", style="dim", width=4)
    table.add_column("Email", width=30)
    table.add_column("API Key", width=30)

    for i, line in enumerate(lines[:50], 1):
        parts = line.split(":")
        if len(parts) >= 3:
            email = parts[0][:28]
            key = parts[2][:25] + "..."
            table.add_row(str(i), email, key)

    if len(lines) > 50:
        console.print(f"  [dim]... and {len(lines) - 50} more[/dim]")

    console.print(table)
    wait_key()

# ─── Test Models ──────────────────────────────────────────────────────

def menu_test():
    """Test available models."""
    clear()
    console.print(Panel(
        Text("Test AI Models", style="bold cyan"),
        box=box.ROUNDED,
        width=50,
    ))

    key = _first_key()
    if key:
        console.print(f"  Using key: [dim]{key[:20]}...[/dim]")
    else:
        key = prompt_input("API Key")
        if not key:
            console.print("  [red]No key provided[/red]")
            wait_key()
            return

    console.print("\n  [dim]Testing 32 models... (this takes ~30 seconds)[/dim]\n")
    try:
        results = asyncio.run(test_all(key, WORKING_MODELS[:32]))
    except Exception as e:
        console.print(f"  [red]Error: {e}[/red]")
        wait_key()
        return

    ok = [r for r in results if r.ok]
    fail = [r for r in results if not r.ok]

    table = Table(box=box.SIMPLE_HEAVY, show_header=True, title=f"Results: {len(ok)} OK / {len(fail)} FAIL")
    table.add_column("Status", width=8)
    table.add_column("Model", width=40)
    for r in results:
        status = "[green]OK[/green]" if r.ok else "[red]ERR[/red]"
        table.add_row(status, r.model)

    console.print(table)

    Path("output").mkdir(exist_ok=True)
    Path("output/model_test.json").write_text(json.dumps({
        "ok": [r.model for r in ok],
        "fail": [{"model": r.model, "error": r.detail} for r in fail],
    }, indent=2), encoding="utf-8")

    wait_key()

# ─── Export ────────────────────────────────────────────────────────────

def menu_export():
    """Export keys to file."""
    clear()
    console.print(Panel(
        Text("Export Keys", style="bold cyan"),
        box=box.ROUNDED,
        width=50,
    ))

    state = load_state("output")
    accounts = [a for a in state.get("accounts", []) if a.get("api_key")]
    if not accounts:
        console.print("  [dim]No successful accounts to export.[/dim]")
        wait_key()
        return

    console.print(f"  [bold]{len(accounts)} accounts ready[/bold]\n")
    console.print("  [cyan]1[/cyan]  Export TXT")
    console.print("  [cyan]2[/cyan]  Export JSON")
    console.print("  [cyan]3[/cyan]  Export CSV")
    console.print("  [cyan]4[/cyan]  Export ALL formats")
    console.print("  [cyan]5[/cyan]  Back")
    console.print()

    try:
        raw = input("  [cyan]→[/cyan] Pilih: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if raw in ("1", "2", "3", "4"):
        written = export_all("output", accounts)
        console.print()
        for fmt, path in written.items():
            console.print(f"  [green]{fmt.upper()}[/green] → {path}")
        wait_key()
    elif raw in ("5", "q", "x", "b"):
        return

# ─── Inject to 9Router ────────────────────────────────────────────────

def menu_inject():
    """Inject keys to provider database."""
    clear()
    console.print(Panel(
        Text("Inject to Database", style="bold cyan"),
        box=box.ROUNDED,
        width=50,
    ))

    db = find_9router_db()
    if not db:
        console.print("  [red]Database not found![/red]")
        console.print("  Set [dim]PROVIDER_DB_PATH[/dim] in .env file")
        wait_key()
        return

    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  [dim]No keys to inject. Run register first.[/dim]")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = list_injected(str(db))

    while True:
        clear()
        console.print(Panel(
            Text("Inject to Database", style="bold cyan"),
            box=box.ROUNDED,
            width=50,
        ))
        console.print(f"  DB: [dim]{db}[/dim]")
        console.print(f"  Keys ready: [bold]{len(lines)}[/bold]")
        console.print(f"  Already injected: [bold]{len(existing)}[/bold]\n")

        console.print("  [cyan]1[/cyan]  INJECT all keys")
        console.print("  [cyan]2[/cyan]  VIEW injected keys")
        console.print("  [cyan]3[/cyan]  REMOVE all keys")
        console.print("  [cyan]4[/cyan]  Back")
        console.print()

        try:
            raw = input("  [cyan]→[/cyan] Pilih: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "1":
            try:
                count = inject_keys("output/keys.txt", str(db))
                console.print(f"\n  [green]Injected {count} new keys![/green]")
                existing = list_injected(str(db))
            except Exception as e:
                console.print(f"\n  [red]Error: {e}[/red]")
            wait_key()
        elif raw == "2":
            clear()
            console.print(Panel(Text("Injected Keys", style="bold cyan"), box=box.ROUNDED, width=50))
            existing = list_injected(str(db))
            if not existing:
                console.print("  [dim]No keys in database.[/dim]")
            else:
                table = Table(box=box.SIMPLE_HEAVY, show_header=True)
                table.add_column("#", style="dim", width=4)
                table.add_column("ID", width=25)
                table.add_column("Email", width=30)
                for i, row in enumerate(existing, 1):
                    table.add_row(str(i), row.get("id", "")[:23], row.get("email", "")[:28])
                console.print(table)
            wait_key()
        elif raw == "3":
            count = remove_keys(str(db))
            console.print(f"\n  [yellow]Removed {count} keys.[/yellow]")
            existing = list_injected(str(db))
            wait_key()
        elif raw in ("4", "q", "x", "b"):
            return

# ─── Status ────────────────────────────────────────────────────────────

def menu_status():
    """Show run status."""
    clear()
    console.print(Panel(
        Text("Run Status", style="bold cyan"),
        box=box.ROUNDED,
        width=50,
    ))

    state = load_state("output")
    accounts = state.get("accounts", [])
    ok = [a for a in accounts if a.get("success")]
    failed = [a for a in accounts if not a.get("success")]

    table = Table(box=None, show_header=False, padding=(0, 2))
    table.add_column("key", style="dim")
    table.add_column("val", style="bold")
    table.add_row("Target:", str(state.get("target", 0)))
    table.add_row("Success:", f"[green]{len(ok)}[/green]")
    table.add_row("Failed:", f"[red]{len(failed)}[/red]")
    table.add_row("Keys on disk:", str(count_keys()))
    console.print(table)

    if failed:
        console.print("\n  [bold]Recent failures:[/bold]")
        for a in failed[-5:]:
            console.print(f"    [red]{a.get('email', '?')[:30]}[/red]: {a.get('error', '?')[:50]}")

    wait_key()

# ─── Main Loop ─────────────────────────────────────────────────────────

def main():
    try:
        while True:
            choice = main_menu()
            if choice is None or choice == "quit":
                clear()
                console.print("\n  [bold cyan]Goodbye![/bold cyan]\n")
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
