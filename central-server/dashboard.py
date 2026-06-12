#!/usr/bin/env python3
"""Ragnarok Central Server — Live TUI Dashboard.

Run: python3 dashboard.py
Requires: pip install rich psycopg2-binary requests
"""
import os, sys, time, subprocess, socket
from datetime import datetime

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich import box
    import psycopg2
    import requests
except ImportError:
    print("Installing dependencies...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "rich", "psycopg2-binary", "requests", "-q"])
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.layout import Layout
    from rich.live import Live
    from rich.text import Text
    from rich.align import Align
    from rich import box
    import psycopg2
    import requests

# --- Config ---
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_USER = os.getenv("DB_USER", "admin")
DB_PASS = os.getenv("DB_PASSWORD", "Ats@123*")
DB_NAME = os.getenv("DB_NAME", "email_service")
API_URL = os.getenv("API_URL", "http://localhost")

console = Console()

BANNER = """
[bold cyan]╔══════════════════════════════════════════════════════════════╗
║     ⚡ RAGNAROK CENTRAL SERVER — LIVE DASHBOARD ⚡          ║
╚══════════════════════════════════════════════════════════════╝[/bold cyan]
"""

def get_db():
    try:
        return psycopg2.connect(host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASS, dbname=DB_NAME)
    except:
        return None

def check_service(name, check_fn):
    try:
        ok = check_fn()
        return f"[bold green]● ONLINE[/bold green]" if ok else f"[bold red]● OFFLINE[/bold red]"
    except:
        return f"[bold red]● OFFLINE[/bold red]"

def check_docker(container):
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container],
                          capture_output=True, text=True, timeout=3)
        return r.stdout.strip() == "true"
    except:
        return False

def check_port(host, port):
    try:
        s = socket.socket(); s.settimeout(1); s.connect((host, int(port))); s.close()
        return True
    except:
        return False

def check_api():
    try:
        r = requests.get(f"{API_URL}/api/v1/health", timeout=2)
        return r.status_code == 200
    except:
        return False

def build_status_panel():
    tbl = Table(box=box.SIMPLE_HEAVY, show_header=False, expand=True, padding=(0, 2))
    tbl.add_column("Service", style="bold white", width=22)
    tbl.add_column("Status", width=18)
    tbl.add_column("Details", style="dim")

    tbl.add_row("🐘 PostgreSQL", check_service("pg", lambda: check_port(DB_HOST, DB_PORT)),
                f"{DB_HOST}:{DB_PORT}/{DB_NAME}")
    tbl.add_row("🐇 RabbitMQ", check_service("rmq", lambda: check_docker("ragnarok_rabbitmq") or check_port("localhost", 5672)),
                "Queue: email_queue")
    tbl.add_row("🌐 Nginx", check_service("ngx", lambda: check_docker("ragnarok_nginx")),
                "Port 80 — Load Balancer")
    tbl.add_row("🚀 FastAPI Web", check_service("api", check_api),
                API_URL)
    tbl.add_row("⚙️  Worker", check_service("wrk", lambda: check_docker("central-server_worker_1")),
                "RabbitMQ Consumer")
    return Panel(tbl, title="[bold yellow]🔧 SERVICE HEALTH[/bold yellow]", border_style="yellow", expand=True)

def build_stats_panel():
    conn = get_db()
    if not conn:
        return Panel("[bold red]Cannot connect to database[/bold red]",
                     title="[bold magenta]📊 STATISTICS[/bold magenta]", border_style="magenta")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM emails")
    total_emails = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM attachments")
    total_att = cur.fetchone()[0]
    cur.execute("SELECT COALESCE(SUM(size), 0) FROM attachments")
    total_size = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT sender) FROM emails")
    unique_senders = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM emails WHERE processed_at >= CURRENT_DATE")
    today = cur.fetchone()[0]
    cur.close(); conn.close()

    size_mb = total_size / (1024 * 1024)
    tbl = Table(box=box.SIMPLE, show_header=False, expand=True, padding=(0, 2))
    tbl.add_column("Metric", style="bold cyan", width=22)
    tbl.add_column("Value", style="bold white")
    tbl.add_row("📧 Total Emails", f"[bold green]{total_emails}[/bold green]")
    tbl.add_row("📎 Total Attachments", f"[bold blue]{total_att}[/bold blue]")
    tbl.add_row("💾 Storage Used", f"[bold yellow]{size_mb:.2f} MB[/bold yellow]")
    tbl.add_row("👥 Unique Senders", f"[bold magenta]{unique_senders}[/bold magenta]")
    tbl.add_row("📅 Today's Emails", f"[bold green]{today}[/bold green]")
    return Panel(tbl, title="[bold magenta]📊 STATISTICS[/bold magenta]", border_style="magenta", expand=True)

def build_recent_panel():
    conn = get_db()
    if not conn:
        return Panel("[bold red]DB offline[/bold red]", title="📬 RECENT EMAILS", border_style="green")
    cur = conn.cursor()
    cur.execute("""
        SELECT e.id, e.sender, e.subject, e.processed_at,
               COUNT(a.id) as att_count, COALESCE(SUM(a.size),0) as att_size
        FROM emails e LEFT JOIN attachments a ON e.id = a.email_id
        GROUP BY e.id ORDER BY e.processed_at DESC LIMIT 8
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    tbl = Table(box=box.ROUNDED, expand=True, header_style="bold cyan")
    tbl.add_column("#", style="dim", width=4)
    tbl.add_column("From", style="bold white", width=28, no_wrap=True)
    tbl.add_column("Subject", style="green", ratio=1, no_wrap=True)
    tbl.add_column("📎", justify="center", width=4)
    tbl.add_column("Size", justify="right", width=8)
    tbl.add_column("Received", style="dim", width=18)

    for r in rows:
        sz = f"{r[5]/1024:.1f}K" if r[5] > 0 else "—"
        ts = r[3].strftime("%Y-%m-%d %H:%M") if r[3] else "—"
        sender = r[1][:26] + ".." if len(str(r[1])) > 28 else r[1]
        subj = r[2][:40] + ".." if len(str(r[2])) > 42 else r[2]
        att_icon = f"[bold yellow]{r[4]}[/bold yellow]" if r[4] > 0 else "[dim]0[/dim]"
        tbl.add_row(str(r[0]), sender, subj, att_icon, sz, ts)

    if not rows:
        tbl.add_row("—", "[dim]No emails received yet[/dim]", "", "", "", "")

    return Panel(tbl, title="[bold green]📬 RECENT EMAILS[/bold green]", border_style="green", expand=True)

def build_attachments_panel():
    conn = get_db()
    if not conn:
        return Panel("[bold red]DB offline[/bold red]", title="📎 ATTACHMENTS", border_style="blue")
    cur = conn.cursor()
    cur.execute("""
        SELECT a.filename, a.content_type, a.size, e.sender
        FROM attachments a JOIN emails e ON a.email_id = e.id
        ORDER BY a.id DESC LIMIT 6
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()

    tbl = Table(box=box.SIMPLE, expand=True, header_style="bold blue")
    tbl.add_column("Filename", style="bold white", ratio=1, no_wrap=True)
    tbl.add_column("Type", style="cyan", width=20)
    tbl.add_column("Size", justify="right", style="yellow", width=10)
    tbl.add_column("From", style="dim", width=24, no_wrap=True)

    for r in rows:
        sz = f"{r[2]/1024:.1f} KB" if r[2] and r[2] > 1024 else f"{r[2] or 0} B"
        ct = (r[1] or "unknown")[:20]
        tbl.add_row(r[0], ct, sz, (r[3] or "")[:24])

    if not rows:
        tbl.add_row("[dim]No attachments yet[/dim]", "", "", "")

    return Panel(tbl, title="[bold blue]📎 RECENT ATTACHMENTS[/bold blue]", border_style="blue", expand=True)

def build_dashboard():
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=5),
        Layout(name="top", size=9),
        Layout(name="middle", size=12),
        Layout(name="bottom", size=10),
    )
    layout["top"].split_row(
        Layout(name="status", ratio=1),
        Layout(name="stats", ratio=1),
    )

    layout["header"].update(Align.center(Text.from_markup(BANNER.strip())))
    layout["status"].update(build_status_panel())
    layout["stats"].update(build_stats_panel())
    layout["middle"].update(build_recent_panel())
    layout["bottom"].update(build_attachments_panel())
    return layout

def main():
    console.clear()
    console.print("[bold cyan]Starting Ragnarok Dashboard... (Ctrl+C to exit)[/bold cyan]\n")
    try:
        with Live(build_dashboard(), console=console, refresh_per_second=0.5, screen=True) as live:
            while True:
                time.sleep(3)
                live.update(build_dashboard())
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Dashboard stopped.[/bold yellow]")

if __name__ == "__main__":
    main()
