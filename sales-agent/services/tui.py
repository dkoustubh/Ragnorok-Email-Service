"""Terminal User Interface (TUI) for the Windows Sales Agent.
Uses standard ANSI codes for cross-platform colors, layouts, and loaders.
"""
import os
import sys
import time
import re
from pathlib import Path
from loguru import logger


# ANSI color codes
CLEAR_SCREEN = "\033[H\033[2J"
CURSOR_HOME = "\033[H"
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"
WHITE = "\033[37m"

DOT_GREEN = f"{GREEN}●{RESET}"
DOT_RED = f"{RED}●{RESET}"
DOT_YELLOW = f"{YELLOW}●{RESET}"
DOT_BLUE = f"{BLUE}●{RESET}"

# Enable ANSI codes on Windows
if sys.platform == "win32":
    os.system("color")


def print_header():
    print(f"{CYAN}{BOLD}")
    print("  ╦═╗┌─┐┌─┐┌┐┌┌─┐┬─┐┌─┐┬┌─  ┌─┐┌┬┐┌─┐┬  ┬  ┌─┐┌─┐┌─┐┌┐┌┌┬┐")
    print("  ╠╦╝├─┤│ ┬│││├─┤├┬┘│ │├┴┐  ├┤ │││├─┤│  │  ├─┤│ ┬├┤ │││ │ ")
    print("  ╩╚═┴─┴└─┘┘└┘┴─┴┴└─└─┘┴ ┴  └─┘┴ ┴┴─┴┴─┘┴─┘┴─┴└─┘└─┘┘└┘ ┴ ")
    print(f"{RESET}")
    print(f"{BOLD}============================================================={RESET}")
    print(f"       {BOLD}RFQ INTERCEPTION & ARCHIVING SYSTEM{RESET}")
    print(f"{BOLD}============================================================={RESET}\n")


def prompt_email() -> str:
    """Prompt the user to enter their email address with input validation."""
    while True:
        print_header()
        print(f"{BOLD}📧 First-Time Setup: Sales Account Mapping{RESET}")
        print("Please enter your active Sales Email ID (Outlook/Gmail).")
        print("This will register this machine to your account.\n")
        
        email = input(f"👉 {BOLD}Email ID:{RESET} ").strip()
        
        # Simple email regex validation
        if re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
            # Save it to .env
            _save_email_to_env(email)
            print(f"\n{GREEN}✔ Email verified and saved! Starting Sales Agent...{RESET}")
            time.sleep(1.5)
            return email
        else:
            print(f"\n{RED}❌ Invalid email address format. Please try again.{RESET}")
            time.sleep(2)
            print(CLEAR_SCREEN, end="")


def _save_email_to_env(email: str):
    """Save the monitored email directly into the .env file."""
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    
    # Read existing content
    content = ""
    if env_path.exists():
        content = env_path.read_text()

    # Replace or append MONITORED_EMAIL
    if "MONITORED_EMAIL=" in content:
        content = re.sub(r"MONITORED_EMAIL=.*", f"MONITORED_EMAIL={email}", content)
    else:
        content += f"\nMONITORED_EMAIL={email}\n"
        
    env_path.write_text(content.strip() + "\n")


class Dashboard:
    def __init__(self, monitored_email: str, forward_email: str):
        self.monitored_email = monitored_email
        self.forward_email = forward_email
        self.checkpoints = {
            "env": {"status": "loading", "label": "Environment Configuration"},
            "db": {"status": "loading", "label": "SQLite Deduplication Database"},
            "outlook": {"status": "loading", "label": "Outlook Desktop App Link"},
            "poller": {"status": "loading", "label": "Interception Loop Status"},
        }
        self.logs = []

    def update_checkpoint(self, name: str, status: str):
        """Set checkpoint status: 'ok', 'failed', 'loading', 'warning', 'idle'."""
        if name in self.checkpoints:
            self.checkpoints[name]["status"] = status
            self.draw()

    def add_log(self, status_char: str, message: str):
        """Add message to the live scroll view.
        status_char: 'G' (green), 'B' (blue), 'Y' (yellow), 'R' (red), 'I' (info)
        """
        timestamp = time.strftime("%H:%M:%S")
        if status_char == "G":
            prefix = f"{GREEN}🟢{RESET}"
        elif status_char == "B":
            prefix = f"{BLUE}🔵{RESET}"
        elif status_char == "Y":
            prefix = f"{YELLOW}🟡{RESET}"
        elif status_char == "R":
            prefix = f"{RED}🔴{RESET}"
        else:
            prefix = "🔍"
            
        self.logs.append(f"[{timestamp}] {prefix} {message}")
        if len(self.logs) > 6:
            self.logs.pop(0)
        self.draw()

    def draw(self):
        """Redraw the terminal screen with the latest state dashboard."""
        sys.stdout.write(CLEAR_SCREEN)
        sys.stdout.write(CURSOR_HOME)
        
        print(f"{CYAN}{BOLD}============================================================={RESET}")
        print(f"               ⚡ {BOLD}RAGNAROK SALES AGENT ACTIVE{RESET}               ")
        print(f"{CYAN}{BOLD}============================================================={RESET}")
        print(f"  👤 {BOLD}Monitored Email:{RESET} {self.monitored_email}")
        print(f"  ➡️ {BOLD}Forward Target:{RESET}  {self.forward_email}")
        print(f"  ⏰ {BOLD}Polling Rate:{RESET}    Every 60s")
        print(f"-------------------------------------------------------------")
        print(f"  {BOLD}SYSTEM CHECKPOINTS:{RESET}")
        
        # Draw Checkpoints
        for key, cp in self.checkpoints.items():
            status = cp["status"]
            if status == "ok":
                dot = DOT_GREEN
                text = f"{GREEN}Ready{RESET}"
            elif status == "failed":
                dot = DOT_RED
                text = f"{RED}Failing / Off{RESET}"
            elif status == "warning":
                dot = DOT_YELLOW
                text = f"{YELLOW}Warning / Idle{RESET}"
            elif status == "loading":
                dot = DOT_BLUE
                text = f"{BLUE}Connecting...{RESET}"
            else:
                dot = DOT_YELLOW
                text = status
                
            print(f"   {dot} {cp['label']:<32} : {text}")
            
        print(f"-------------------------------------------------------------")
        print(f"  {BOLD}LIVE ACTIVITY LOGS (Scroll):{RESET}")
        
        # Draw live log streams
        if not self.logs:
            print("   (Waiting for incoming emails...)")
        else:
            for log in self.logs:
                print(f"   {log}")
                
        print(f"{CYAN}{BOLD}============================================================={RESET}")
        print(f"  Press {BOLD}Ctrl+C{RESET} to safely exit the background process.")
        sys.stdout.flush()


def show_progress_bar(label: str, seconds: float):
    """Draw a progress bar with loaded metrics."""
    width = 30
    for i in range(width + 1):
        percent = int((i / width) * 100)
        filled = "=" * i
        empty = " " * (width - i)
        sys.stdout.write(f"\r  {label} [{filled}>{empty}] {percent}%")
        sys.stdout.flush()
        time.sleep(seconds / width)
    print()
