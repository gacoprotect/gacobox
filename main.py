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

def prompt_choice(options: list[str], header: str = "") -> str:
    """Simple numbered menu — works everywhere."""
    if header:
        console.print(f"\n  [bold]{header}[/bold]\n")
    for i, label in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan]  {label}")
    console.print()
    try:
        raw = input("  Pilih: ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if raw.isdigit() and 1 <= int(raw) <= len(options):
        return options[int(raw) - 1]
    return raw

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

    while True:
        clear()
        draw_header()
        console.print()
        for i, (label, _) in enumerate(options, 1):
            console.print(f"  [cyan]{i}[/cyan]  {label}")
        console.print()

        try:
            raw = input("  Pilih [1-7]: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "quit"

        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1][1]
        elif raw.lower() in ("q", "x", "quit", "exit"):
            return "quit"

# ─── Register Menu ────────────────────────────────────────────────────

def menu_register():
    count = 10
    workers = 3
    headless = True
    domain = "catchmail.io"
    key_name = "auto-farm-key"

    state = load_state("output")
    done = len(done_emails(state))

    while True:
        clear()
        console.print(Panel(Text("Register Accounts", style="bold cyan"), box=box.DOUBLE, width=50))
        if done > 0:
            console.print(f"  [dim]Previous run: {done} accounts completed[/dim]\n")

        console.print(f"  Count:    [cyan]{count}[/cyan]")
        console.print(f"  Workers:  [cyan]{workers}[/cyan]")
        console.print(f"  Headless: [cyan]{'ON' if headless else 'OFF'}[/cyan]")
        console.print(f"  Domain:   [cyan]{domain}[/cyan]")
        console.print(f"  Key Name: [cyan]{key_name}[/cyan]")
        console.print()
        console.print("  [cyan]1[/cyan]  START (New)")
        if done > 0:
            console.print("  [cyan]2[/cyan]  RESUME (Continue)")
        console.print("  [cyan]3[/cyan]  Edit Count")
        console.print("  [cyan]4[/cyan]  Edit Workers")
        console.print("  [cyan]5[/cyan]  Toggle Headless")
        console.print("  [cyan]6[/cyan]  Edit Domain")
        console.print("  [cyan]7[/cyan]  Back")
        console.print()

        try:
            raw = input("  Pilih: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw == "1":
            _do_register(count, workers, headless, domain, key_name, resume=False)
            return
        elif raw == "2" and done > 0:
            _do_register(count, workers, headless, domain, key_name, resume=True)
            return
        elif raw == "3":
            val = input(f"  Count [{count}]: ").strip()
            if val.isdigit(): count = max(1, int(val))
        elif raw == "4":
            val = input(f"  Workers [{workers}]: ").strip()
            if val.isdigit(): workers = max(1, int(val))
        elif raw == "5":
            headless = not headless
        elif raw == "6":
            val = input(f"  Domain [{domain}]: ").strip()
            if val: domain = val
        elif raw in ("7", "q", "x", "b"):
            return

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
        tasks.append(asyncio.create_task(_account(launched % cfg.max_workers, email, password)))
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

    while True:
        clear()
        console.print(Panel(Text("Export Keys", style="bold cyan"), box=box.DOUBLE, width=50))
        console.print(f"  {len(accounts)} accounts ready\n")
        console.print("  [cyan]1[/cyan]  TXT")
        console.print("  [cyan]2[/cyan]  JSON")
        console.print("  [cyan]3[/cyan]  CSV")
        console.print("  [cyan]4[/cyan]  ALL formats")
        console.print("  [cyan]5[/cyan]  Back")
        console.print()

        try:
            raw = input("  Pilih: ").strip()
        except (EOFError, KeyboardInterrupt):
            return

        if raw in ("1", "2", "3", "4"):
            fmt_map = {"1": "txt", "2": "json", "3": "csv", "4": "all"}
            # export_all handles all formats
            written = export_all("output", accounts)
            for fmt, path in written.items():
                console.print(f"  [green]{fmt.upper()}[/green] -> {path}")
            wait_key()
            return
        elif raw in ("5", "q", "x", "b"):
            return

# ─── Inject to 9Router ────────────────────────────────────────────────

def menu_inject():
    clear()
    console.print(Panel(Text("Inject to 9Router", style="bold cyan"), box=box.DOUBLE, width=50))

    db = find_9router_db()
    if db:
        console.print(f"  [green]Found DB:[/green] {db}")
    else:
        console.print("  [red]Provider DB not found![/red]")
        console.print("  Searched locations:")
        for p in _discover_db_paths():
            console.print(f"    {p}")
        console.print("\n  Set PROVIDER_DB_PATH env var.")
        wait_key()
        return

    # Check keys
    p = Path("output/keys.txt")
    if not p.exists():
        console.print("  [dim]No keys to inject. Run register first.[/dim]")
        wait_key()
        return

    lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
    existing = list_injected(str(db))

    while True:
        clear()
        console.print(Panel(Text("Inject to Provider DB", style="bold cyan"), box=box.DOUBLE, width=50))
        console.print(f"  DB: {db}")
        console.print(f"  Keys ready: {len(lines)}")
        console.print(f"  Already injected: {len(existing)}\n")
        console.print("  [cyan]1[/cyan]  INJECT all keys")
        console.print("  [cyan]2[/cyan]  VIEW injected keys")
        console.print("  [cyan]3[/cyan]  REMOVE all keys")
        console.print("  [cyan]4[/cyan]  Back")
        console.print()

        try:
            raw = input("  Pilih: ").strip()
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
            console.print(Panel(Text("Injected Keys", style="bold cyan"), box=box.DOUBLE, width=50))
            existing = list_injected(str(db))
            if not existing:
                console.print("  [dim]No keys in DB.[/dim]")
            else:
                table = Table(box=box.SIMPLE, show_header=True)
                table.add_column("#", style="dim")
                table.add_column("ID")
                table.add_column("Email")
                for i, row in enumerate(existing, 1):
                    table.add_row(str(i), row.get("id", "")[:20], row.get("email", "")[:25])
                console.print(table)
            wait_key()
        elif raw == "3":
            count = remove_keys(str(db))
            console.print(f"\n  [yellow]Removed {count} keys.[/yellow]")
            existing = list_injected(str(db))
            wait_key()
        elif raw in ("4", "q", "x", "b"):
            return

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
