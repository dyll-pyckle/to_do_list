#!/usr/bin/env python3
"""
Ultimate To-Do CLI
Features:
 - JSON storage with backups
 - Autosave & config
 - Colorized pretty table
 - Search, sort, filtering
 - Add/edit/remove items, mark done/undone
 - Repeating tasks (daily, weekly, monthly, every N days, specific weekdays)
 - Undo stack
 - Notifications for due/today/overdue items on startup
 - Export to CSV
"""

import json
import os
import shutil
import uuid
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import csv

# -------------------------
# Configuration & Defaults
# -------------------------
DATA_FILE = "to_do.json"
CONFIG_FILE = "config.json"
BACKUP_DIR = "backups"
DEFAULT_CONFIG = {
    "autosave": True,
    "backup_on_save": True,
    "backup_keep": 10,
    "color": True,
    "default_sort": {"key": "date", "reverse": False},
    "undo_depth": 10,
    "reminder_days": 3,  # notify for tasks due within this many days
    "date_format": "iso",  # 'iso' expects YYYY-MM-DD but parser accepts DD/MM/YYYY too
}

# -------------------------
# ANSI Colors (toggleable)
# -------------------------
class Colors:
    RED = "\033[91m"
    YELLOW = "\033[93m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

# -------------------------
# Utility helpers
# -------------------------
def load_config() -> dict:
    if not os.path.exists(CONFIG_FILE):
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_FILE, "r") as f:
            cfg = json.load(f)
        # fill missing keys
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return DEFAULT_CONFIG.copy()

def save_config(cfg: dict):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=4)

CFG = load_config()

def colored(text: str, color_code: str) -> str:
    if not CFG.get("color", True):
        return text
    return f"{color_code}{text}{Colors.RESET}"

def ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)

def make_backup(data):
    if not CFG.get("backup_on_save", True):
        return
    ensure_backup_dir()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fname = f"to_do_backup_{ts}.json"
    path = os.path.join(BACKUP_DIR, fname)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    # prune old backups
    backups = sorted(os.listdir(BACKUP_DIR))
    keep = CFG.get("backup_keep", 10)
    if len(backups) > keep:
        for old in backups[: len(backups) - keep]:
            try:
                os.remove(os.path.join(BACKUP_DIR, old))
            except Exception:
                pass

# -------------------------
# Storage and undo stack
# -------------------------
UNDO_STACK: List[List[dict]] = []

def push_undo(state: List[dict]):
    depth = CFG.get("undo_depth", 10)
    # store deep copy
    copy_state = json.loads(json.dumps(state))
    UNDO_STACK.append(copy_state)
    if len(UNDO_STACK) > depth:
        UNDO_STACK.pop(0)

def undo(last_state_holder: dict) -> Optional[List[dict]]:
    # returns restored state or None
    if not UNDO_STACK:
        print("Nothing to undo.")
        return None
    restored = UNDO_STACK.pop()
    save_data(restored)
    print("Undo successful.")
    return restored

def load_data() -> List[dict]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)
        # compat: if old list-of-lists, convert
        if data and isinstance(data[0], list):
            converted = []
            for row in data:
                # expected [item, date, priority] optionally
                item = row[0] if len(row) > 0 else ""
                d = row[1] if len(row) > 1 else ""
                p = row[2] if len(row) > 2 else "low"
                converted.append({
                    "id": str(uuid.uuid4()),
                    "item": item,
                    "date": d,
                    "priority": p,
                    "completed": False,
                    "repeat": None,
                    "notes": "",
                    "created": datetime.now().isoformat()
                })
            save_data(converted)
            return converted
        return data
    except Exception:
        return []

def save_data(data: List[dict]):
    try:
        make_backup(data)
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print("Error saving data:", e)

# -------------------------
# Date parsing and helpers
# -------------------------
def parse_date(s: str) -> Optional[date]:
    """Accepts 'YYYY-MM-DD' or 'DD/MM/YYYY' or empty string. Returns date or None."""
    s = s.strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            pass
    # try forgiving parse: accept dd-mm-yyyy too
    try:
        return datetime.strptime(s.replace("-", "/"), "%d/%m/%Y").date()
    except Exception:
        return None

def format_date_for_display(d: Optional[date]) -> str:
    return d.isoformat() if d else ""

def days_until(d: Optional[date]) -> Optional[int]:
    if d is None:
        return None
    return (d - date.today()).days

# -------------------------
# Repeat rule handling
# -------------------------
def next_date_for_repeat(d: Optional[date], rule: Optional[str]) -> Optional[date]:
    """Given a date and repeat rule, compute next occurrence date.
    Supported rules:
      - None or empty -> None
      - 'daily'
      - 'weekly'
      - 'monthly'
      - 'every N days' where N is integer (e.g., 'every 7 days')
      - comma-separated weekdays, like 'mon,wed,fri'
    """
    if d is None or not rule:
        return None
    rule = rule.strip().lower()
    if rule == "daily":
        return d + timedelta(days=1)
    if rule == "weekly":
        return d + timedelta(weeks=1)
    if rule == "monthly":
        # simple approach: add 1 month by incrementing month, keeping day when possible
        try:
            month = d.month + 1
            year = d.year
            if month > 12:
                month = 1
                year += 1
            day = min(d.day, [31,
                              29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
            return date(year, month, day)
        except Exception:
            return d + timedelta(days=30)
    if rule.startswith("every "):
        # try "every N days"
        parts = rule.split()
        if len(parts) >= 3 and parts[2].startswith("day"):
            try:
                n = int(parts[1])
                return d + timedelta(days=n)
            except Exception:
                pass
    # weekdays like "mon,tue"
    day_map = {"mon":0,"monday":0,"tue":1,"tuesday":1,"wed":2,"wednesday":2,
               "thu":3,"thursday":3,"fri":4,"friday":4,"sat":5,"saturday":5,
               "sun":6,"sunday":6}
    if "," in rule or rule in day_map:
        try:
            tokens = [t.strip() for t in rule.split(",")]
            weekdays = [day_map[t] for t in tokens if t in day_map]
            if not weekdays:
                return None
            # find the next date after d that matches any weekday
            for i in range(1, 15):  # look up to two weeks
                candidate = d + timedelta(days=i)
                if candidate.weekday() in weekdays:
                    return candidate
        except Exception:
            return None
    return None

# -------------------------
# Task helpers
# -------------------------
def new_task(item: str, date_str: str = "", priority: str = "low", repeat: Optional[str]=None, notes: str="") -> dict:
    d = parse_date(date_str)
    return {
        "id": str(uuid.uuid4()),
        "item": item.strip(),
        "date": format_date_for_display(d) if d else "",
        "priority": priority.lower() if priority else "low",
        "completed": False,
        "repeat": repeat,
        "notes": notes,
        "created": datetime.now().isoformat()
    }

# -------------------------
# Display formatting
# -------------------------
def color_priority(p: str) -> str:
    p = (p or "").lower()
    if p == "high":
        return colored(p, Colors.RED)
    if p == "medium":
        return colored(p, Colors.YELLOW)
    return colored(p or "low", Colors.GREEN)

def status_text(done: bool) -> str:
    return "✔" if done else " "

def build_table_rows(tasks: List[dict]) -> List[List[str]]:
    rows = []
    for t in tasks:
        d = parse_date(t.get("date","")) if t.get("date") else None
        days = days_until(d) if d else None
        # highlight overdue/today via color in priority cell or item
        item_text = t["item"]
        if d:
            if days is not None and days < 0:
                item_text = colored(item_text, Colors.RED)
            elif days == 0:
                item_text = colored(item_text, Colors.CYAN)
        rows.append([
            t["item"],
            t.get("date",""),
            t.get("priority",""),
            "✔" if t.get("completed") else "",
            t.get("repeat") or "",
            t.get("notes","")
        ])
    return rows

def print_table(tasks: List[dict]):
    rows = build_table_rows(tasks)
    if not rows:
        print("Nothing to display.\n")
        return

    HEADERS = ["Item", "Date", "Priority", "Done", "Repeat", "Notes"]
    widths = [
        max(len(HEADERS[0]), *(len(str(r[0])) for r in rows)),
        max(len(HEADERS[1]), *(len(str(r[1])) for r in rows)),
        max(len(HEADERS[2]), *(len(str(r[2])) for r in rows)),
        max(len(HEADERS[3]), *(len(str(r[3])) for r in rows)),
        max(len(HEADERS[4]), *(len(str(r[4])) for r in rows)),
        max(len(HEADERS[5]), *(len(str(r[5])) for r in rows)),
    ]

    sep = " | "
    header_row = f"{HEADERS[0]:<{widths[0]}}{sep}{HEADERS[1]:<{widths[1]}}{sep}{HEADERS[2]:<{widths[2]}}{sep}{HEADERS[3]:<{widths[3]}}{sep}{HEADERS[4]:<{widths[4]}}{sep}{HEADERS[5]:<{widths[5]}}"
    print()
    print(header_row)
    print("-" * (sum(widths) + len(sep) * 5))

    for i, t in enumerate(tasks, 1):
        d = parse_date(t.get("date","")) if t.get("date") else None
        days = days_until(d) if d else None

        item_display = t["item"]
        priority_display = t.get("priority","")
        if priority_display:
            priority_display = color_priority(priority_display)
        # overdue/today highlight item name
        if d:
            if days is not None and days < 0:
                item_display = colored(item_display, Colors.RED)
            elif days == 0:
                item_display = colored(item_display, Colors.CYAN)

        done_display = "✔" if t.get("completed") else ""

        print(f"{i:>2}. {item_display:<{widths[0]}}{sep}{t.get('date',''):<{widths[1]}}{sep}{priority_display:<{widths[2]}}{sep}{done_display:<{widths[3]}}{sep}{(t.get('repeat') or ''):<{widths[4]}}{sep}{(t.get('notes') or ''):<{widths[5]}}")

    print()

# -------------------------
# Commands
# -------------------------
def list_all(tasks: List[dict], show_completed: bool = True):
    if not show_completed:
        tasks = [t for t in tasks if not t.get("completed")]
    print_table(tasks)

def add_item(tasks: List[dict]):
    item = input("Item to add > ").strip()
    if not item:
        print("Empty item; cancelled.")
        return tasks
    if any(t["item"].lower() == item.lower() for t in tasks):
        print("Item already exists.")
        return tasks
    date_str = input("Due date (YYYY-MM-DD or DD/MM/YYYY) [optional] > ").strip()
    if date_str and parse_date(date_str) is None:
        print("Unrecognized date format. Use YYYY-MM-DD or DD/MM/YYYY.")
        return tasks
    priority = input("Priority (high/medium/low) [low] > ").strip().lower() or "low"
    if priority not in ("high","medium","low"):
        print("Invalid priority; defaulting to low.")
        priority = "low"
    repeat = input("Repeat rule (daily/weekly/monthly/every N days/mon,wed) [optional] > ").strip() or None
    notes = input("Notes [optional] > ").strip() or ""
    push_undo(tasks)
    t = new_task(item, date_str, priority, repeat, notes)
    tasks.append(t)
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Item added.")
    return tasks

def find_task_by_identifier(tasks: List[dict], identifier: str) -> Optional[dict]:
    """Identifier can be numeric index (1-based), full/partial name, or id."""
    identifier = identifier.strip()
    if not identifier:
        return None
    # numeric
    if identifier.isdigit():
        idx = int(identifier) - 1
        if 0 <= idx < len(tasks):
            return tasks[idx]
    # id exact
    for t in tasks:
        if t.get("id") == identifier:
            return t
    # name partial (case-insensitive)
    matches = [t for t in tasks if identifier.lower() in t["item"].lower()]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print("Multiple matches found:")
        for i, m in enumerate(matches, 1):
            print(f"  {i}. {m['item']} (id: {m['id']})")
        print("Be more specific or use numeric index.")
        return None
    return None

def remove_item(tasks: List[dict]):
    identifier = input("Item to remove (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Item not found or ambiguous.")
        return tasks
    confirm = input(f"Delete '{t['item']}'? (y/n) > ").strip().lower()
    if confirm not in ("y","yes"):
        print("Cancelled.")
        return tasks
    push_undo(tasks)
    tasks = [x for x in tasks if x["id"] != t["id"]]
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Deleted.")
    return tasks

def rename_item(tasks: List[dict]):
    identifier = input("Which item to rename (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Not found.")
        return tasks
    new_name = input(f"Rename '{t['item']}' to > ").strip()
    if not new_name:
        print("Empty name; cancelled.")
        return tasks
    push_undo(tasks)
    t["item"] = new_name
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Renamed.")
    return tasks

def change_priority(tasks: List[dict]):
    identifier = input("Change priority for (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Not found.")
        return tasks
    new_p = input("New priority (high/medium/low) > ").strip().lower()
    if new_p not in ("high","medium","low"):
        print("Invalid priority.")
        return tasks
    push_undo(tasks)
    t["priority"] = new_p
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Priority updated.")
    return tasks

def change_date(tasks: List[dict]):
    identifier = input("Change date for (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Not found.")
        return tasks
    new_date = input("New date (YYYY-MM-DD or DD/MM/YYYY) [empty to clear] > ").strip()
    if new_date and parse_date(new_date) is None:
        print("Invalid date format.")
        return tasks
    push_undo(tasks)
    t["date"] = new_date or ""
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Date updated.")
    return tasks

def toggle_done(tasks: List[dict]):
    identifier = input("Mark done/undone for (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Not found.")
        return tasks
    push_undo(tasks)
    t["completed"] = not t.get("completed", False)
    # handle repeating tasks: if marked done and has repeat, create next occurrence
    if t["completed"] and t.get("repeat"):
        d = parse_date(t.get("date",""))
        next_d = next_date_for_repeat(d, t.get("repeat"))
        if next_d:
            new = new_task(t["item"], next_d.isoformat(), t.get("priority","low"), t.get("repeat"), t.get("notes",""))
            tasks.append(new)
            print("Next occurrence created for repeating task.")
    if CFG.get("autosave", True):
        save_data(tasks)
    print(f"Marked {'done' if t['completed'] else 'not done'}.")
    return tasks

def edit_notes(tasks: List[dict]):
    identifier = input("Edit notes for (index/name/id) > ").strip()
    t = find_task_by_identifier(tasks, identifier)
    if not t:
        print("Not found.")
        return tasks
    new_notes = input("New notes [empty to clear] > ").strip()
    push_undo(tasks)
    t["notes"] = new_notes
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Notes updated.")
    return tasks

def search_tasks(tasks: List[dict]):
    q = input("Search query (keyword in name/notes) > ").strip().lower()
    if not q:
        print("Empty query.")
        return
    found = [t for t in tasks if q in t["item"].lower() or q in (t.get("notes","").lower())]
    if not found:
        print("No results.")
        return
    print_table(found)

def sort_tasks(tasks: List[dict]):
    print("Sort by:\n 1: name\n 2: date\n 3: priority\n 4: done\n 5: created\n  (enter to cancel)")
    choice = input("> ").strip()
    if choice == "1":
        tasks.sort(key=lambda t: t["item"].lower())
    elif choice == "2":
        def date_key(t):
            pd = parse_date(t.get("date",""))
            return pd or date.max
        tasks.sort(key=date_key)
    elif choice == "3":
        order = {"high":0,"medium":1,"low":2}
        tasks.sort(key=lambda t: order.get(t.get("priority","low"), 3))
    elif choice == "4":
        tasks.sort(key=lambda t: t.get("completed", False))
    elif choice == "5":
        tasks.sort(key=lambda t: t.get("created",""))
    else:
        print("Cancelled.")
        return tasks
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Sorted.")
    return tasks

def export_csv(tasks: List[dict]):
    fname = input("CSV filename to create [tasks_export.csv] > ").strip() or "tasks_export.csv"
    try:
        with open(fname, "w", newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["id","item","date","priority","completed","repeat","notes","created"])
            for t in tasks:
                writer.writerow([t.get(k,"") for k in ("id","item","date","priority","completed","repeat","notes","created")])
        print(f"Exported to {fname}")
    except Exception as e:
        print("Export failed:", e)

def clear_completed(tasks: List[dict]):
    completed = [t for t in tasks if t.get("completed")]
    if not completed:
        print("No completed tasks to clear.")
        return tasks
    confirm = input(f"Remove {len(completed)} completed tasks? (y/n) > ").strip().lower()
    if confirm not in ("y","yes"):
        print("Cancelled.")
        return tasks
    push_undo(tasks)
    tasks = [t for t in tasks if not t.get("completed")]
    if CFG.get("autosave", True):
        save_data(tasks)
    print("Completed tasks cleared.")
    return tasks

def show_config():
    print(json.dumps(CFG, indent=4))

def toggle_autosave():
    CFG["autosave"] = not CFG.get("autosave", True)
    save_config(CFG)
    print("Autosave:", "ON" if CFG["autosave"] else "OFF")

def undo_command(tasks: List[dict]):
    restored = undo({})
    if restored is not None:
        return restored
    return tasks

# -------------------------
# Startup notifications
# -------------------------
def notify_startup(tasks: List[dict]):
    reminder_days = CFG.get("reminder_days", 3)
    today = date.today()
    due_today = []
    overdue = []
    upcoming = []
    for t in tasks:
        d = parse_date(t.get("date","")) if t.get("date") else None
        if not d:
            continue
        days = (d - today).days
        if days < 0 and not t.get("completed"):
            overdue.append(t)
        elif days == 0 and not t.get("completed"):
            due_today.append(t)
        elif 0 < days <= reminder_days and not t.get("completed"):
            upcoming.append((t, days))
    if overdue:
        print(colored("OVERDUE tasks:", Colors.RED))
        print_table(overdue[:10])
    if due_today:
        print(colored("Due TODAY:", Colors.CYAN))
        print_table(due_today[:10])
    if upcoming:
        print(colored(f"Due in next {reminder_days} days:", Colors.MAGENTA))
        print_table([t for t, _ in upcoming][:10])

# -------------------------
# Main loop
# -------------------------
def main():
    tasks = load_data()
    # apply default sort if configured
    ds = CFG.get("default_sort", {})
    if ds:
        key = ds.get("key","date")
        rev = ds.get("reverse", False)
        # apply sort quietly
        if key == "date":
            tasks.sort(key=lambda t: parse_date(t.get("date","")) or date.max, reverse=rev)
        elif key == "name":
            tasks.sort(key=lambda t: t["item"].lower(), reverse=rev)
    notify_startup(tasks)

    while True:
        print("""
==========================
  ULTIMATE TO-DO MANAGER
==========================
1  Add item
2  Remove item
3  List all
4  List active only
5  List completed
6  Rename item
7  Toggle done/undone
8  Change priority
9  Change date
10 Edit notes
11 Search
12 Sort
13 Export CSV
14 Clear completed
15 Undo
16 Toggle autosave
17 Show config
18 Edit config (manual)
19 Backup now
20 Exit
""")
        choice = input("> ").strip()
        if choice == "1":
            push_undo(tasks); tasks = add_item(tasks)
        elif choice == "2":
            tasks = remove_item(tasks)
        elif choice == "3":
            list_all(tasks, show_completed=True)
        elif choice == "4":
            list_all(tasks, show_completed=False)
        elif choice == "5":
            completed = [t for t in tasks if t.get("completed")]
            print_table(completed)
        elif choice == "6":
            tasks = rename_item(tasks)
        elif choice == "7":
            tasks = toggle_done(tasks)
        elif choice == "8":
            tasks = change_priority(tasks)
        elif choice == "9":
            tasks = change_date(tasks)
        elif choice == "10":
            tasks = edit_notes(tasks)
        elif choice == "11":
            search_tasks(tasks)
        elif choice == "12":
            tasks = sort_tasks(tasks)
        elif choice == "13":
            export_csv(tasks)
        elif choice == "14":
            tasks = clear_completed(tasks)
        elif choice == "15":
            tasks = undo_command(tasks)
        elif choice == "16":
            toggle_autosave()
        elif choice == "17":
            show_config()
        elif choice == "18":
            print("Editing config.json manually. Open the file in an editor.")
            save_config(CFG)
        elif choice == "19":
            print("Creating immediate backup...")
            make_backup(tasks)
            print("Backup created.")
        elif choice == "20":
            if CFG.get("autosave", True):
                save_data(tasks)
            print("Goodbye!")
            break
        else:
            print("Unknown command.")

# -------------------------
# Entry point
# -------------------------
if __name__ == "__main__":
    main()
