#!/usr/bin/env python
# -*- coding:utf-8 -*-

r"""____        _ _     _
|  _ \  ___ | (_)___| |_
| | | |/ _ \| | / __| __|
| |_| | (_) | | \__ \ |_
|____/ \___/|_|_|___/\__|

DoList - To-Do list on Command Line Interface
"""

from typing import Optional, Annotated
import cyclopts
from cyclopts import Parameter
from rich.console import Console
from rich import print as rprint
from .rich_table import print_table
from .database import Database, FieldDef
import os
import datetime
from .taskmodel import Task
from .colors import HEAD, ID, NAME, REDBOLD, STATUS, TAG
from .tui import run_tui
from pathlib import Path
import sys
import shutil
from .reminder_parser import parse_reminder, format_reminder, get_time_until
from .service import install_systemd_service, trigger_reminder
import json

# tomllib is only available in Python 3.11+, use tomli for older versions
if sys.version_info >= (3, 11):
    import tomllib
else:
    try:
        import tomli as tomllib
    except ImportError:
        # Fallback if tomli is not installed
        tomllib = None


# XDG Base Directory support with backwards compatibility
def get_config_dir():
    """Get config directory with XDG support and backwards compatibility."""
    # Check for XDG_CONFIG_HOME first (Linux/Unix standard)
    xdg_config = os.getenv("XDG_CONFIG_HOME")
    if xdg_config:
        config_dir = Path(xdg_config) / "dolist"
    else:
        # Default to ~/.config/dolist on Unix-like systems
        config_dir = Path.home() / ".config" / "dolist"

    # Backwards compatibility: check if old ~/.dopy exists
    old_dir = Path.home() / ".dopy"
    if old_dir.exists() and not config_dir.exists():
        return old_dir

    return config_dir


def get_legacy_config_file():
    """Get legacy config file path for backwards compatibility."""
    return Path.home() / ".dopyrc"


BASEDIR = get_config_dir()

# Create config directory if it doesn't exist
if not BASEDIR.exists():
    BASEDIR.mkdir(parents=True, exist_ok=True)

# New TOML config file
CONFIGFILE = BASEDIR / "config.toml"
LEGACY_CONFIGFILE = get_legacy_config_file()

# Migration and config loading
if LEGACY_CONFIGFILE.exists() and not CONFIGFILE.exists():
    # Migrate from legacy config
    try:
        legacy_config = eval(LEGACY_CONFIGFILE.read_text())
        # Create new TOML config
        toml_content = f"""# DoList Configuration File
# This file uses TOML format

[database]
# Database directory (default: ~/.config/dolist or $XDG_CONFIG_HOME/dolist)
dir = "{BASEDIR}"
# Database URI (default: sqlite://tasks.db)
uri = "sqlite://tasks.db"

[ui]
# TUI theme (default: textual-dark)
# Available themes: textual-dark, textual-light, nord, gruvbox, catppuccin, dracula, monokai, solarized-light, solarized-dark
theme = "textual-dark"
"""
        CONFIGFILE.write_text(toml_content)
        CONFIG = {
            "dbdir": str(BASEDIR),
            "dburi": "sqlite://tasks.db",
            "theme": "textual-dark",
        }
        print(f"Migrated legacy config from {LEGACY_CONFIGFILE} to {CONFIGFILE}")
    except Exception as e:
        print(f"Warning: Could not migrate legacy config: {e}")
        CONFIG = {"dbdir": str(BASEDIR), "dburi": "sqlite://tasks.db"}
elif CONFIGFILE.exists():
    # Load TOML config
    try:
        if tomllib is None:
            raise ImportError("TOML library not available")
        with open(CONFIGFILE, "rb") as f:
            toml_config = tomllib.load(f)

        # Default columns with priority and size at the end
        default_columns = [
            "id",
            "name",
            "tag",
            "status",
            "reminder",
            "notes",
            "created",
            "priority",
            "size",
        ]
        columns = toml_config.get("ui", {}).get("columns", default_columns)

        # Ensure 'id' is always first
        if "id" not in columns:
            columns = ["id"] + columns
        elif columns[0] != "id":
            columns.remove("id")
            columns = ["id"] + columns

        CONFIG = {
            "dbdir": toml_config.get("database", {}).get("dir", str(BASEDIR)),
            "dburi": toml_config.get("database", {}).get("uri", "sqlite://tasks.db"),
            "theme": toml_config.get("ui", {}).get("theme", "textual-dark"),
            "autorefresh_interval": toml_config.get("tui", {}).get(
                "autorefresh_interval", 30
            ),
            "reminder_cmd": toml_config.get("reminders", {}).get("reminder_cmd"),
            "day_start_hour": toml_config.get("reminders", {}).get("day_start_hour", 9),
            "columns": columns,
        }
    except Exception as e:
        print(f"Warning: Could not load config file: {e}")
        CONFIG = {
            "dbdir": str(BASEDIR),
            "dburi": "sqlite://tasks.db",
            "theme": "textual-dark",
            "autorefresh_interval": 30,
            "day_start_hour": 9,
            "columns": [
                "id",
                "name",
                "tag",
                "status",
                "reminder",
                "notes",
                "created",
                "priority",
                "size",
            ],
        }
else:
    # Create default TOML config
    default_config = f"""# DoList Configuration File
# This file uses TOML format

[database]
# Database directory (default: ~/.config/dolist or $XDG_CONFIG_HOME/dolist)
dir = "{BASEDIR}"
# Database URI (default: sqlite://tasks.db)
uri = "sqlite://tasks.db"

[ui]
# TUI theme (default: textual-dark)
# Available themes: textual-dark, textual-light, nord, gruvbox, catppuccin, dracula, monokai, solarized-light, solarized-dark
theme = "textual-dark"

# Columns to display in tables (TUI and CLI)
# The 'id' column is always required and must be first
# Available columns: id, name, tag, status, reminder, notes, created, priority, size
# Default order: all columns with priority and size at the end
columns = ["id", "name", "tag", "status", "reminder", "notes", "created", "priority", "size"]

[tui]
# Auto-refresh interval in seconds (default: 30)
# Set to 0 to disable auto-refresh
autorefresh_interval = 30

[reminders]
# Custom command to handle reminders (optional)
# If set, this command will be called with task JSON piped to stdin
# If not set, uses notify-send by default
# reminder_cmd = "/path/to/custom/reminder/handler"

# Default start hour for day-based reminders (default: 9)
# When you set a reminder like "monday" or "25" (day of month), this hour will be used
# Value should be in 24-hour format (0-23)
day_start_hour = 9
"""
    CONFIGFILE.write_text(default_config)
    CONFIG = {
        "dbdir": str(BASEDIR),
        "dburi": "sqlite://tasks.db",
        "theme": "textual-dark",
        "autorefresh_interval": 30,
        "day_start_hour": 9,
        "columns": [
            "id",
            "name",
            "tag",
            "status",
            "reminder",
            "notes",
            "created",
            "priority",
            "size",
        ],
    }

# Support legacy database location (~/.dopy/dopy.db)
legacy_db_path = Path.home() / ".dopy" / "dopy.db"
if legacy_db_path.exists() and "dopy.db" in CONFIG["dburi"]:
    # Use legacy database location
    CONFIG["dbdir"] = str(Path.home() / ".dopy")
    CONFIG["dburi"] = "sqlite://dopy.db"

DBDIR = CONFIG["dbdir"]
DBURI = CONFIG["dburi"]

console = Console()

# Global database connection
db = None
tasks = None
history = None
state = None


SHELLDOC = r"""
     ____        _ _     _
    |  _ \  ___ | (_)___| |_
    | | | |/ _ \| | / __| __|
    | |_| | (_) | | \__ \ |_
    |____/ \___/|_|_|___/\__|

[Interactive Python REPL for DoList]

Available objects:
  • tasklist  - List of all active Task objects
  • db        - Database connection
  • tasks     - Tasks table

Quick examples:
  >>> tasklist                    # Show all tasks
  >>> tasklist[0].name            # Get first task name
  >>> tasklist[0].update_status('done')  # Update task status
  >>> [t.name for t in tasklist]  # List all task names

Task management:
  >>> task = tasklist[0]          # Get a task
  >>> task.name                   # View property
  >>> task.update_name("New")     # Update name
  >>> task.add_note("A note")     # Add a note
  >>> task.delete()               # Delete task

Tips:
  • Use Tab for auto-completion
  • Use F2 to toggle between Vi/Emacs mode
  • Use Ctrl+D or quit() to exit

"""


def database(DBURI):
    """Initialize database connection."""
    _db = Database(DBURI, folder=DBDIR)
    tasks = _db.define_table(
        "dolist_tasks",
        FieldDef("name", "string"),
        FieldDef("tag", "string"),
        FieldDef("status", "string"),
        FieldDef("reminder", "string"),
        FieldDef("reminder_timestamp", "datetime"),
        FieldDef(
            "reminder_repeat", "string"
        ),  # For recurring reminders (e.g., "2 hours")
        FieldDef("notes", "list:string"),
        FieldDef("created_on", "datetime"),
        FieldDef("deleted", "boolean", default=False),
        FieldDef("priority", "integer", default=0),
        FieldDef("size", "string", default="U"),
    )

    # TaskHistory table for tracking changes
    history = _db.define_table(
        "dolist_task_history",
        FieldDef("changed_at", "datetime"),
        FieldDef("task_id", "integer"),
        FieldDef("name", "string"),
        FieldDef("tag", "string"),
        FieldDef("status", "string"),
        FieldDef("reminder", "string"),
        FieldDef("reminder_timestamp", "datetime"),
        FieldDef("reminder_repeat", "string"),
        FieldDef("notes", "list:string"),
        FieldDef("created_on", "datetime"),
        FieldDef("deleted", "boolean", default=False),
        FieldDef("priority", "integer", default=0),
        FieldDef("size", "string", default="U"),
    )

    # DolistState table for persistent UI state (sorting, filters, theme, etc.)
    state = _db.define_table(
        "dolist_state",
        FieldDef("config_key", "string"),
        FieldDef("config_value", "string"),
    )

    return _db, tasks, history, state


def init_db(use_db: Optional[str] = None):
    """Initialize global database connection.

    Returns:
        The database URI that was used
    """
    global db, tasks, history, state, DBDIR
    dburi = DBURI
    if use_db:
        # Check if it's an absolute path
        from pathlib import Path

        db_path = Path(use_db)
        if db_path.is_absolute():
            # Absolute path: override DBDIR and use just the filename in URI
            DBDIR = str(db_path.parent)
            dburi = f"sqlite://{db_path.name}"
        else:
            # Relative path: replace database name in URI
            dburi = dburi.replace("tasks", use_db).replace("dopy", use_db)
    db, tasks, history, state = database(dburi)
    return dburi


def record_task_history(task_row):
    """Record a snapshot of the task to the history table.

    Args:
        task_row: The task row to record
    """
    if history is None:
        return

    try:
        from datetime import datetime

        history.insert(
            changed_at=datetime.now(),
            task_id=task_row.id,
            name=task_row.name,
            tag=task_row.tag,
            status=task_row.status,
            reminder=task_row.reminder,
            reminder_timestamp=task_row.reminder_timestamp,
            notes=task_row.notes,
            created_on=task_row.created_on,
            deleted=task_row.deleted,
            priority=task_row.get("priority", 0),
            size=task_row.get("size", "U"),
        )
        db.commit()
    except Exception:
        # Don't fail if history recording fails
        pass


# Create the Cyclopts app
app = cyclopts.App(
    name="dolist",
    help="DoList - To-Do list on Command Line Interface",
    version="0.4.0",
)


@app.default
def default_action(
    *tokens,
    rm: Optional[int] = None,
    use: Optional[str] = None,
    actions: bool = False,
):
    """Default action - Launch TUI or perform task action.

    When called without arguments, launches the TUI.
    When called with an ID and optional action, performs the task action.

    Args:
        tokens: Task ID and action with optional arguments.
        rm: Index of note to remove (for 'note' action with --rm flag).
        use: Database name to use (optional).
        actions: Show list of available actions.

    Examples:
        dolist                   # Launch TUI
        dolist --actions         # List available actions
        dolist 1                 # Edit task 1 interactively
        dolist 1 done            # Mark task 1 as done
        dolist 2 remind tomorrow # Set reminder on task 2
        dolist 3 delay 1 hour    # Delay reminder by 1 hour (unquoted)
        dolist 4 start           # Start working on task 4
        dolist 5 note This is a note  # Add note (unquoted)
    """
    global db, tasks
    dburi = init_db(use)

    # Show available actions if --actions flag is set
    if actions:
        console.print("[bold cyan]Available Actions for Tasks:[/bold cyan]\n")
        console.print("[yellow]Status Management:[/yellow]")
        console.print(
            "  • [green]start, in-progress[/green]  - Mark task as in-progress"
        )
        console.print("  • [green]done[/green]                 - Mark task as done")
        console.print(
            "  • [green]cancel[/green]               - Mark task as cancelled"
        )
        console.print("  • [green]new[/green]                  - Mark task as new")
        console.print(
            "  • [green]post[/green]                 - Mark task as postponed"
        )
        console.print()
        console.print("[yellow]Reminder Management:[/yellow]")
        console.print(
            "  • [green]remind <time>[/green]        - Set a reminder (e.g., 'tomorrow', '2 hours')"
        )
        console.print(
            "  • [green]delay [time][/green]         - Delay reminder (default: 10 minutes)"
        )
        console.print(
            "  • [green]clear-reminder[/green]       - Clear reminder from task"
        )
        console.print()
        console.print("[yellow]Note Management:[/yellow]")
        console.print("  • [green]note <text>[/green]          - Add a note to task")
        console.print("  • [green]note --rm <index>[/green]    - Remove note by index")
        console.print()
        console.print("[yellow]Task Operations:[/yellow]")
        console.print(
            "  • [green]show[/green]                 - Show task details with notes"
        )
        console.print(
            "  • [green]edit[/green]                 - Open TUI with task selected for editing"
        )
        console.print(
            "  • [green]get[/green]                  - Open interactive Python shell for task"
        )
        console.print(
            "  • [green]delete, rm[/green]           - Delete task (soft delete)"
        )
        console.print()
        console.print("[yellow]Usage Examples:[/yellow]")
        console.print("  dolist 1            # Show task 1 details")
        console.print("  dolist 1 done       # Mark task 1 as done")
        console.print("  dolist 2 remind tomorrow")
        console.print("  dolist 3 note This is a note")
        console.print("  dolist 4 delay 1 hour")
        console.print("  dolist 5 edit       # Open TUI and edit task 5")
        return

    # Parse tokens
    if not tokens:
        # No arguments - launch TUI
        # Extract database path from URI
        db_filename = dburi.replace("sqlite://", "")
        db_path = Path(DBDIR) / db_filename
        tui_config = {
            "theme": CONFIG.get("theme", "textual-dark"),
            "config_file": str(CONFIGFILE),
            "db_path": str(db_path),
            "config_dir": DBDIR,
        }
        try:
            run_tui(db, tasks, tui_config, history, state)
        except KeyboardInterrupt:
            console.print("\n[yellow]TUI interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error running TUI: {e}[/red]")
            console.print("[yellow]Your terminal should be restored.[/yellow]")
            raise
        return

    # First token should be the task ID
    try:
        id = int(tokens[0])
    except (ValueError, IndexError):
        console.print("[red]First argument must be a task ID (number)[/red]")
        return

    # Task action mode
    row = tasks[id]
    if not row:
        rprint("[red]Task not found[/red]")
        return

    # If no action provided, show the task
    if len(tokens) == 1:
        _show_task(row)
        return

    # Extract action and remaining arguments
    action = tokens[1].lower()
    action_args = list(tokens[2:]) if len(tokens) > 2 else []

    # Handle different actions
    if action in ["start", "in-progress"]:
        row.update_record(status="in-progress")
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} marked as in-progress[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "done":
        row.update_record(status="done")
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} marked as done[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "cancel":
        row.update_record(status="cancel")
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} marked as cancelled[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "new":
        row.update_record(status="new")
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} marked as new[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "post":
        row.update_record(status="post")
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} marked as postponed[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action in ["rm", "delete"]:
        row.update_record(deleted=True)
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Task {id} deleted[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "clear-reminder":
        row.update_record(reminder=None, reminder_timestamp=None)
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Reminder cleared from task {id}[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")

    elif action == "remind":
        if not action_args:
            console.print("[red]Error: remind requires a time argument[/red]")
            console.print("Usage: dolist <id> remind <time>")
            console.print("Example: dolist 1 remind 2 hours")
            console.print("Example: dolist 1 remind 2 hours repeat  (for recurring)")
            return

        reminder_time = " ".join(action_args)
        parsed_dt, error, repeat_interval = parse_reminder(reminder_time)
        if error:
            console.print(f"[red]Error parsing reminder: {error}[/red]")
            return

        row.update_record(
            reminder=reminder_time,
            reminder_timestamp=parsed_dt,
            reminder_repeat=repeat_interval,
        )
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Reminder set for task {id}[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")
        if repeat_interval:
            console.print(
                f"[yellow]  Due: {format_reminder(parsed_dt)} (repeats every {repeat_interval})[/yellow]"
            )
        else:
            console.print(f"[yellow]  Due: {format_reminder(parsed_dt)}[/yellow]")

    elif action == "delay":
        # Check if task has a reminder
        if not row.reminder_timestamp:
            console.print(f"[red]Task {id} has no active reminder[/red]")
            console.print(
                "[yellow]Set a reminder first using: dolist {id} remind <time>[/yellow]".replace(
                    "{id}", str(id)
                )
            )
            return

        # Default to 10 minutes if no time specified
        delay_time = " ".join(action_args) if action_args else "10 minutes"

        parsed_dt, error, _ = parse_reminder(delay_time)
        if error:
            console.print(f"[red]Error parsing delay time: {error}[/red]")
            return

        # Keep the original reminder_repeat if it exists (delay doesn't change recurrence)
        row.update_record(
            reminder=f"delayed: {delay_time}", reminder_timestamp=parsed_dt
        )
        db.commit()
        record_task_history(row)
        console.print(f"[green]✓ Reminder delayed for task {id}[/green]")
        console.print(f"[cyan]  {row.name}[/cyan]")
        console.print(f"[yellow]  New due time: {format_reminder(parsed_dt)}[/yellow]")

    elif action == "note":
        row.notes = row.notes or []

        # Handle note addition (from args or stdin)
        if action_args:
            note_text = " ".join(action_args)
            row.update_record(notes=row.notes + [note_text])
            record_task_history(row)
            db.commit()
            console.print(f"[green]✓ Note added to task {id}[/green]")
            console.print(f"[cyan]  {row.name}[/cyan]")
        elif rm is None and not sys.stdin.isatty():
            # Read note from stdin (but only if not removing a note)
            stdin_content = sys.stdin.read().strip()
            if stdin_content:
                row.update_record(notes=row.notes + [stdin_content])
                db.commit()
                console.print(f"[green]✓ Note added to task {id} from stdin[/green]")
                console.print(f"[cyan]  {row.name}[/cyan]")

        # Handle note removal
        if rm is not None:
            try:
                del row.notes[rm]
                row.update_record(notes=row.notes)
                db.commit()
                console.print(f"[green]✓ Note {rm} removed from task {id}[/green]")
                console.print(f"[cyan]  {row.name}[/cyan]")
            except (IndexError, TypeError):
                console.print("[bold red]Note not found[/bold red]")
                return

        # Re-fetch the row from database to get properly deserialized notes
        row = tasks[id]
        # Show task with notes
        _show_task(row)

    elif action == "show":
        _show_task(row)

    elif action == "history":
        # Show task history
        if history is None:
            console.print("[red]History table not available[/red]")
            return

        try:
            query = history.task_id == id
            history_rows = db(query).select()

            # Sort by changed_at descending (most recent first)
            history_rows = sorted(
                history_rows, key=lambda r: r.changed_at, reverse=True
            )

            if not history_rows:
                console.print(f"[yellow]No history recorded for task {id}[/yellow]")
                console.print(f"[cyan]  {row.name}[/cyan]")
                return

            # Print history table
            from rich.table import Table
            from rich import box

            console.print(f"\n[bold]History for Task #{id}: {row.name}[/bold]")

            table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
            table.add_column("Changed At", style="cyan")
            table.add_column("Name")
            table.add_column("Tag")
            table.add_column("Status", style="yellow")
            table.add_column("Reminder")
            table.add_column("Notes")

            for hist_row in history_rows:
                changed_str = hist_row.changed_at.strftime("%Y-%m-%d %H:%M:%S")
                notes_count = len(hist_row.notes) if hist_row.notes else 0

                table.add_row(
                    changed_str,
                    hist_row.name or "",
                    hist_row.tag or "",
                    hist_row.status or "",
                    hist_row.reminder or "",
                    str(notes_count),
                )

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error loading history: {e}[/red]")

    elif action == "get":
        _get_task_shell(row)

    elif action == "edit":
        # Open TUI with this task selected
        # Extract database path from URI
        db_filename = dburi.replace("sqlite://", "")
        db_path = Path(DBDIR) / db_filename
        tui_config = {
            "theme": CONFIG.get("theme", "textual-dark"),
            "config_file": str(CONFIGFILE),
            "selected_task_id": id,
            "db_path": str(db_path),
            "config_dir": DBDIR,
        }
        try:
            run_tui(db, tasks, tui_config, history, state)
        except KeyboardInterrupt:
            console.print("\n[yellow]TUI interrupted by user[/yellow]")
        except Exception as e:
            console.print(f"\n[red]Error running TUI: {e}[/red]")
            console.print("[yellow]Your terminal should be restored.[/yellow]")
            raise

    else:
        rprint(f"[red]Unknown action: {action}[/red]")
        rprint(
            "[yellow]Valid actions: start, done, cancel, new, post, show, rm, delete, remind, delay, clear-reminder, note, get, edit, history[/yellow]"
        )


@app.command
def shell(use: Optional[str] = None):
    """Start interactive Python REPL with access to task list.

    Args:
        use: Database name to use (optional).
    """
    init_db(use)

    global tasklist
    tasklist = []
    for task in db(tasks.deleted != True).select():  # noqa: E712
        tasklist.append(Task.from_row(db, task))

    # Try to use ptpython for a better REPL experience
    try:
        from ptpython.repl import embed
        from ptpython.prompt_style import PromptStyle
        from prompt_toolkit.formatted_text import HTML

        # Custom prompt style
        class DopyPromptStyle(PromptStyle):
            def in_prompt(self):
                return HTML(
                    "<ansigreen><b>dopy</b></ansigreen> <ansicyan>&gt;&gt;&gt;</ansicyan> "
                )

            def in2_prompt(self, width):
                return HTML("<ansigreen>...</ansigreen> ")

            def out_prompt(self):
                return HTML(
                    "<ansiyellow>Out</ansiyellow> <ansicyan>&gt;&gt;&gt;</ansicyan> "
                )

        def configure(repl):
            """Configure the ptpython REPL."""
            # Enable syntax highlighting
            repl.highlight_matching_parenthesis = True
            repl.show_signature = True
            repl.show_docstring = True
            repl.show_meta_enter_message = True
            repl.completion_visualisation = "MULTI_COLUMN"
            repl.enable_history_search = True
            repl.enable_auto_suggest = True
            repl.show_status_bar = True
            repl.show_sidebar_help = True
            repl.swap_light_and_dark = False

            # Set custom prompt style
            repl.all_prompt_styles["dopy"] = DopyPromptStyle()
            repl.prompt_style = "dopy"

        # Print banner with Rich
        console.print(SHELLDOC, style="cyan")
        console.print(f"[green]Loaded {len(tasklist)} tasks[/green]\n")

        # Start ptpython REPL
        embed(globals(), locals(), configure=configure)

    except ImportError:
        # Fallback to standard REPL if ptpython is not available
        import code

        console.print(SHELLDOC, style="cyan")
        console.print(
            "[yellow]Note: Install ptpython for a better REPL experience[/yellow]\n"
        )
        code.interact(local=globals(), banner="")


@app.command
def add(
    name: Optional[str] = None,
    tag: str = "default",
    status: str = "new",
    reminder: Optional[str] = None,
    note: Optional[str] = None,
    priority: int = 0,
    size: str = "U",
    use: Optional[str] = None,
):
    """Add a new task.

    Args:
        name: Task name/description. If not provided, reads from stdin (first line as name, rest as notes).
        tag: Task tag/category (default: "default").
        status: Task status (default: "new").
        reminder: Optional reminder text (e.g., "today", "2 hours", "next week").
        note: Optional note to add to the task.
        priority: Task priority (default: 0).
        size: Task size - U/S/M/L or Undefined/Small/Medium/Large (default: "U").
        use: Database name to use (optional).
    """
    init_db(use)

    notes = []

    # Check if we should read from stdin
    if name is None or name == "-":
        # Read from stdin
        if sys.stdin.isatty():
            console.print(
                "[red]Error: No task name provided and stdin is not available[/red]"
            )
            console.print("Usage: dolist add <name> or echo 'task' | dolist add")
            return

        stdin_lines = sys.stdin.read().strip().split("\n")
        if not stdin_lines or not stdin_lines[0]:
            console.print("[red]Error: Empty input from stdin[/red]")
            return

        # First line is the task name
        name = stdin_lines[0].strip()

        # Rest of the lines become notes
        if len(stdin_lines) > 1:
            notes = [line.strip() for line in stdin_lines[1:] if line.strip()]

    if not name:
        console.print("[red]Error: Task name cannot be empty[/red]")
        return

    # Add note from --note parameter if provided
    if note:
        notes.append(note)

    created_on = datetime.datetime.now()
    reminder_timestamp = None
    reminder_repeat = None

    # Parse reminder if provided
    if reminder:
        parsed_dt, error, repeat_interval = parse_reminder(reminder)
        if error:
            rprint(
                f"[yellow]Warning: Could not parse reminder '{reminder}': {error}[/yellow]"
            )
            rprint(
                "[yellow]Task will be created without a reminder timestamp.[/yellow]"
            )
        else:
            reminder_timestamp = parsed_dt
            reminder_repeat = repeat_interval
            if repeat_interval:
                rprint(
                    f"[cyan]Recurring reminder set for: {format_reminder(parsed_dt)} (repeats every {repeat_interval})[/cyan]"
                )
            else:
                rprint(f"[cyan]Reminder set for: {format_reminder(parsed_dt)}[/cyan]")

    # Normalize size value
    size_upper = size.upper()
    if size_upper in ("SMALL", "MEDIUM", "LARGE", "UNDEFINED"):
        size_map = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L", "UNDEFINED": "U"}
        size = size_map[size_upper]
    elif size_upper not in ("U", "S", "M", "L"):
        rprint(
            f"[yellow]Warning: Invalid size '{size}', using 'U' (Undefined)[/yellow]"
        )
        size = "U"
    else:
        size = size_upper

    task_id = tasks.insert(
        name=name,
        tag=tag or "default",
        status=status or "new",
        reminder=reminder,
        reminder_timestamp=reminder_timestamp,
        reminder_repeat=reminder_repeat,
        notes=notes if notes else None,
        created_on=created_on,
        priority=priority,
        size=size,
    )
    db.commit()
    rprint(f"[green]Task {task_id} inserted[/green]")
    if notes:
        rprint(f"[cyan]Added {len(notes)} note(s)[/cyan]")


@app.command
def ls(
    all: bool = False,
    tag: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    name: Optional[str] = None,
    note: Optional[str] = None,
    date: Optional[str] = None,
    month: Optional[str] = None,
    day: Optional[str] = None,
    year: Optional[str] = None,
    priority: Optional[str] = None,
    size: Optional[str] = None,
    under: Optional[int] = None,
    json: bool = False,
    report: bool = False,
    period: str = "month",
    action: Optional[str] = None,
    action_args: Optional[str] = None,
    yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False,
    use: Optional[str] = None,
):
    """List tasks.

    Args:
        all: Show all tasks including done/cancelled.
        tag: Filter by tag.
        status: Filter by status.
        search: Search in both task names and notes (name matches first, then notes).
        name: Search only in task names.
        note: Search only in task notes.
        date: Filter by date.
        month: Filter by month.
        day: Filter by day.
        year: Filter by year.
        priority: Filter by priority (exact match or range like '>5', '>=3', '<2').
        size: Filter by size (U, S, M, L).
        under: Filter by parent task ID (shows tasks that depend on or are under this task).
        json: Output in JSON format.
        report: Generate metrics report for the filtered tasks.
        period: Period for report aggregation (day, week, month, year). Default: month.
        action: Bulk action to perform on all matching tasks (done, start, cancel, new, post, delete, rm, remind).
        action_args: Arguments for the bulk action (e.g., reminder time).
        yes: Skip confirmation prompt for bulk actions.
        use: Database name to use (optional).
    """
    init_db(use)

    query = tasks.deleted != True  # noqa: E712
    query &= (
        ~tasks.status.belongs(["done", "cancel", "post"])
        if not all and not status
        else tasks.id > 0
    )

    if tag:
        query &= tasks.tag == tag
    if status:
        query &= tasks.status == status

    # Handle specific name search
    if name:
        query &= tasks.name.like("%%%s%%" % name.lower())

    rows = db(query).select()

    # Handle general search (searches both name and notes, with name matches first)
    if search:
        name_matches = []
        note_matches = []
        search_lower = search.lower()

        for row in rows:
            # Check if search term is in name
            if search_lower in row.name.lower():
                name_matches.append(row)
            # Check if search term is in any note
            elif row.notes:
                for note in row.notes:
                    if search_lower in note.lower():
                        note_matches.append(row)
                        break  # Only add once even if multiple notes match

        # Combine with name matches first
        rows = name_matches + note_matches

    # Handle specific note search
    elif note:
        note_matches = []
        note_lower = note.lower()

        for row in rows:
            if row.notes:
                for task_note in row.notes:
                    if note_lower in task_note.lower():
                        note_matches.append(row)
                        break  # Only add once even if multiple notes match

        rows = note_matches

    # Apply priority filter (post-query filtering to support range operators)
    if priority:
        filtered_rows = []
        for row in rows:
            task_priority = row.get("priority", 0)
            include = False

            # Check for range operators
            if priority.startswith(">="):
                try:
                    val = int(priority[2:])
                    include = task_priority >= val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return
            elif priority.startswith(">"):
                try:
                    val = int(priority[1:])
                    include = task_priority > val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return
            elif priority.startswith("<="):
                try:
                    val = int(priority[2:])
                    include = task_priority <= val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return
            elif priority.startswith("<"):
                try:
                    val = int(priority[1:])
                    include = task_priority < val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return
            elif priority.startswith("="):
                try:
                    val = int(priority[1:])
                    include = task_priority == val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return
            else:
                # Exact match
                try:
                    val = int(priority)
                    include = task_priority == val
                except ValueError:
                    console.print(f"[red]Invalid priority value: {priority}[/red]")
                    return

            if include:
                filtered_rows.append(row)

        rows = filtered_rows

    # Apply size filter (post-query filtering)
    if size:
        # Normalize size input
        size_upper = size.upper()
        if size_upper in ("SMALL", "MEDIUM", "LARGE", "UNDEFINED"):
            size_map = {"SMALL": "S", "MEDIUM": "M", "LARGE": "L", "UNDEFINED": "U"}
            size_upper = size_map[size_upper]

        if size_upper not in ("U", "S", "M", "L"):
            console.print(
                f"[red]Invalid size: {size}. Use U, S, M, L (or Undefined, Small, Medium, Large)[/red]"
            )
            return

        filtered_rows = []
        for row in rows:
            task_size = row.get("size", "U")
            if task_size == size_upper:
                filtered_rows.append(row)

        rows = filtered_rows

    # Apply 'under' filter (post-query filtering for task dependencies)
    if under is not None:
        from .dependency import parse_dependencies

        filtered_rows = []
        for row in rows:
            row_notes = row.notes or []
            depends_on, under_ids = parse_dependencies(row_notes)
            # Check if this task depends on or is under the specified parent
            if depends_on == under or under in under_ids:
                filtered_rows.append(row)

        rows = filtered_rows

    # Apply date filters (post-query filtering)
    if date or month or day or year:
        filtered_rows = []
        for row in rows:
            if not row.created_on:
                continue

            include_row = True

            # Check specific date
            if date and include_row:
                try:
                    filter_date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
                    if row.created_on.date() != filter_date:
                        include_row = False
                except ValueError:
                    console.print("[red]Invalid date format. Use YYYY-MM-DD[/red]")
                    return

            # Check month
            if month and include_row:
                try:
                    month_num = int(month)
                    if not 1 <= month_num <= 12:
                        raise ValueError
                    if row.created_on.month != month_num:
                        include_row = False
                except ValueError:
                    console.print("[red]Invalid month. Use 1-12[/red]")
                    return

            # Check day
            if day and include_row:
                try:
                    day_num = int(day)
                    if not 1 <= day_num <= 31:
                        raise ValueError
                    if row.created_on.day != day_num:
                        include_row = False
                except ValueError:
                    console.print("[red]Invalid day. Use 1-31[/red]")
                    return

            # Check year
            if year and include_row:
                try:
                    year_num = int(year)
                    if row.created_on.year != year_num:
                        include_row = False
                except ValueError:
                    console.print("[red]Invalid year[/red]")
                    return

            if include_row:
                filtered_rows.append(row)

        rows = filtered_rows

    # Handle report output
    if report:
        from .reports import calculate_metrics, format_metrics_json, format_metrics_text
        from .taskmodel import Task

        # Convert rows to Task objects for metrics calculation
        task_objects = [Task.from_row(db, row) for row in rows]
        metrics = calculate_metrics(task_objects, period=period)

        # Output as JSON or with colored text charts
        if json:
            print(format_metrics_json(metrics))
        else:
            # Display beautiful colored bar charts (same as TUI)
            print(format_metrics_text(metrics))

        return

    # Handle bulk actions
    if action:
        if not rows:
            console.print("[yellow]No tasks match the filters[/yellow]")
            return

        # Confirm bulk action (unless --yes flag is set)
        if not yes:
            console.print(
                f"[yellow]About to perform action '{action}' on {len(rows)} task(s)[/yellow]"
            )
            for row in rows:
                console.print(f"  - [{row.id}] {row.name}")

            confirmation = input("\nType 'yes' to confirm: ").strip().lower()
            if confirmation != "yes":
                console.print("[green]Bulk action cancelled.[/green]")
                return

        # Perform action on each task
        for row in rows:
            if action in ["start", "in-progress"]:
                row.update_record(status="in-progress")
            elif action == "done":
                row.update_record(status="done")
            elif action == "cancel":
                row.update_record(status="cancel")
            elif action == "new":
                row.update_record(status="new")
            elif action == "post":
                row.update_record(status="post")
            elif action in ["rm", "delete"]:
                row.update_record(deleted=True)
            elif action == "remind":
                if not action_args:
                    console.print(
                        "[red]Error: remind action requires time argument[/red]"
                    )
                    console.print(
                        "Usage: dolist ls ... --action remind --action-args '2 hours'"
                    )
                    return
                parsed_dt, error, repeat_interval = parse_reminder(action_args)
                if error:
                    console.print(f"[red]Error parsing reminder: {error}[/red]")
                    return
                row.update_record(
                    reminder=action_args,
                    reminder_timestamp=parsed_dt,
                    reminder_repeat=repeat_interval,
                )
            else:
                console.print(f"[red]Unknown action: {action}[/red]")
                return

        db.commit()
        console.print(
            f"[green]✓ Action '{action}' applied to {len(rows)} task(s)[/green]"
        )
        return

    # Handle JSON output
    if json:
        import json as json_module

        tasks_data = []
        now = datetime.datetime.now()
        for row in rows:
            # Format reminder display
            reminder_display = ""

            # Safeguard: If reminder text exists but timestamp is NULL, try to recalculate
            if row.reminder and not row.reminder_timestamp:
                parsed_dt, error, repeat_interval = parse_reminder(row.reminder)
                if not error and parsed_dt:
                    row.update_record(
                        reminder_timestamp=parsed_dt,
                        reminder_repeat=repeat_interval or row.get("reminder_repeat"),
                    )
                    db.commit()
                    row._data["reminder_timestamp"] = parsed_dt

            if row.reminder_timestamp:
                # Check if reminder is in the past
                if row.reminder_timestamp < now:
                    reminder_display = ""
                else:
                    reminder_display = get_time_until(row.reminder_timestamp)
                    # Add (r) indicator for repeating reminders
                    if row.get("reminder_repeat"):
                        reminder_display = f"{reminder_display} (r)"

            task_data = {
                "id": row.id,
                "name": row.name,
                "tag": row.tag,
                "status": row.status,
                "reminder": row.reminder,
                "reminder_display": reminder_display,
                "reminder_timestamp": (
                    row.reminder_timestamp.isoformat()
                    if row.reminder_timestamp
                    else None
                ),
                "notes": row.notes or [],
                "created_on": row.created_on.isoformat() if row.created_on else None,
            }
            tasks_data.append(task_data)

        print(json_module.dumps(tasks_data, indent=2))
        return

    # Handle table output
    # Get columns from config with default fallback
    columns_config = CONFIG.get(
        "columns",
        [
            "id",
            "name",
            "tag",
            "status",
            "reminder",
            "notes",
            "created",
            "priority",
            "size",
        ],
    )

    # Import dependency functions for display
    from .dependency import get_dependency_display_info, count_children

    # Map column names to display names and formatting functions
    column_display_map = {
        "id": ("ID", lambda r: ID(str(r.id))),
        "name": ("Name", lambda r: getattr(r, "_name_display", NAME(str(r.name)))),
        "tag": ("Tag", lambda r: TAG(str(r.tag))),
        "status": (
            "Status",
            lambda r: getattr(r, "_status_display", STATUS(str(r.status))),
        ),
        "reminder": ("Reminder", lambda r: getattr(r, "_reminder_display", "")),
        "notes": ("Notes", lambda r: str(len(r.notes) if r.notes else 0)),
        "created": ("Created", lambda r: str(r.created_on.strftime("%d/%m-%H:%M"))),
        "priority": ("Priority", lambda r: str(r.get("priority", 0))),
        "size": ("Size", lambda r: str(r.get("size", "U"))),
    }

    # Build headers based on configuration
    headers = [
        HEAD(column_display_map[col][0])
        for col in columns_config
        if col in column_display_map
    ]
    table = [headers]

    now = datetime.datetime.now()
    for row in rows:
        # Format reminder display
        reminder_display = ""

        # Safeguard: If reminder text exists but timestamp is NULL, try to recalculate
        if row.reminder and not row.reminder_timestamp:
            parsed_dt, error, repeat_interval = parse_reminder(row.reminder)
            if not error and parsed_dt:
                row.update_record(
                    reminder_timestamp=parsed_dt,
                    reminder_repeat=repeat_interval or row.get("reminder_repeat"),
                )
                db.commit()
                row._data["reminder_timestamp"] = parsed_dt

        if row.reminder_timestamp:
            # Check if reminder is in the past
            if row.reminder_timestamp < now:
                # Auto-clear past reminders
                row.update_record(reminder=None, reminder_timestamp=None)
                db.commit()
                reminder_display = ""
            else:
                # Show time until reminder
                reminder_display = get_time_until(row.reminder_timestamp)
                # Add (r) indicator for repeating reminders
                if row.get("reminder_repeat"):
                    reminder_display = f"{reminder_display} (r)"

        # Store reminder display for use in lambda
        row._reminder_display = reminder_display

        # Compute dependency display info
        dep_info = get_dependency_display_info(row.id, row.notes or [])

        # Build name with dependency prefix
        name_text = str(row.name)
        if dep_info["display_prefix"]:
            name_text = f"{dep_info['display_prefix']} {name_text}"

        # Count children to add suffix
        child_count = count_children(row.id, rows)
        if child_count > 0:
            name_text = f"{name_text} ({child_count})"

        # Apply color based on dependency type
        if dep_info["prefix_type"] == "blocked":
            # Red-ish for blocked tasks
            row._name_display = REDBOLD(name_text)
            row._status_display = REDBOLD("blocked")
        elif dep_info["prefix_type"] == "under":
            # Yellow-ish for under tasks
            from termcolor import colored

            row._name_display = colored(name_text, "yellow")
            row._status_display = STATUS(str(row.status))
        else:
            row._name_display = NAME(name_text)
            row._status_display = STATUS(str(row.status))

        # Build row based on configured columns
        fields = [
            column_display_map[col][1](row)
            for col in columns_config
            if col in column_display_map
        ]
        table.append(fields)

    print_table(table)

    if rows:
        console.print(f"[green]TOTAL: {len(rows)} tasks[/green]")
    else:
        console.print("[yellow]NO TASKS FOUND[/yellow]")
        console.print("Use --help to see the usage tips")


def _show_task(task_row):
    """Helper function to show a task with all its notes."""
    headers = [HEAD(s) for s in ["ID", "Name", "Tag", "Status", "Reminder", "Created"]]
    fields = [
        ID(str(task_row.id)),
        NAME(str(task_row.name)),
        TAG(str(task_row.tag)),
        STATUS(str(task_row.status)),
        str(task_row.reminder or ""),
        str(task_row.created_on.strftime("%d/%m-%H:%M")),
    ]
    print_table([headers, fields])

    if task_row.notes:
        console.print("\n[bold cyan]NOTES:[/bold cyan]")
        for i, note in enumerate(task_row.notes):
            # Alternate colors for readability
            color = "blue" if i % 2 == 0 else "cyan"
            console.print(f"  [{color}][{i}][/{color}] {note}")
        console.print(f"\n[green]Total: {len(task_row.notes)} note(s)[/green]")
    else:
        console.print("\n[dim]No notes[/dim]")


def _get_task_shell(task_row):
    """Helper function to open interactive shell for a task."""
    task = Task.from_row(db, task_row)

    # Create a nice banner for single task editing
    task_banner = rf"""
     ____        _ _     _
    |  _ \  ___ | (_)___| |_
    | | | |/ _ \| | / __| __|
    | |_| | (_) | | \__ \ |_
    |____/ \___/|_|_|___/\__|

[Interactive Task Editor - Task #{task.id}]

Current task: {task.name}
Tag: {task.tag} | Status: {task.status}

Available methods:
  • task.update_name("new name")     - Update task name
  • task.update_status("done")       - Update status
  • task.update_tag("work")          - Update tag
  • task.add_note("note text")       - Add a note
  • task.delete()                    - Delete this task

Properties:
  • task.name, task.tag, task.status, task.reminder, task.notes

Tips:
  • Use Tab for auto-completion
  • Use Ctrl+D or quit() to exit
"""

    # Try to use ptpython for better experience
    try:
        from ptpython.repl import embed
        from ptpython.prompt_style import PromptStyle
        from prompt_toolkit.formatted_text import HTML

        class DopyPromptStyle(PromptStyle):
            def in_prompt(self):
                return HTML(
                    f"<ansigreen><b>task[{task.id}]</b></ansigreen> <ansicyan>&gt;&gt;&gt;</ansicyan> "
                )

            def in2_prompt(self, width):
                return HTML("<ansigreen>...</ansigreen> ")

            def out_prompt(self):
                return HTML(
                    "<ansiyellow>Out</ansiyellow> <ansicyan>&gt;&gt;&gt;</ansicyan> "
                )

        def configure(repl):
            repl.highlight_matching_parenthesis = True
            repl.show_signature = True
            repl.show_docstring = True
            repl.completion_visualisation = "MULTI_COLUMN"
            repl.enable_history_search = True
            repl.enable_auto_suggest = True
            repl.show_status_bar = True
            repl.all_prompt_styles["dopy"] = DopyPromptStyle()
            repl.prompt_style = "dopy"

        console.print(task_banner, style="cyan")
        embed(globals(), locals(), configure=configure)

    except ImportError:
        import code

        console.print(task_banner, style="cyan")
        code.interact(local=dict(task=task), banner="")


@app.command
def service(
    enable: bool = False,
    remind: bool = False,
    use: Optional[str] = None,
    databases: Optional[str] = None,
    verbose: bool = False,
    interval: int = 30,
):
    """Run or manage the reminder service.

    Args:
        enable: Install and enable as systemd service.
        remind: Process a reminder (reads task JSON from stdin).
        use: Database name to use (optional, deprecated - use --databases).
        databases: Colon-separated list of databases to monitor (e.g., "tasks.db:work.db").
        verbose: Enable verbose logging with detailed debugging information.
        interval: Check interval in seconds (default: 30).
    """
    if enable:
        # Install systemd service
        console.print("[bold cyan]Installing DoList Reminder Service[/bold cyan]")
        if install_systemd_service():
            console.print("[green]Service installed successfully![/green]")
        else:
            console.print("[red]Service installation failed[/red]")
            sys.exit(1)
        return

    if remind:
        # Process reminder from stdin
        try:
            task_json = sys.stdin.read()
            task_data = json.loads(task_json)
            trigger_reminder(task_data, CONFIG)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON input: {e}[/red]")
            sys.exit(1)
        except Exception as e:
            console.print(f"[red]Error processing reminder: {e}[/red]")
            sys.exit(1)
        return

    # Default: run service loop
    # Determine which databases to monitor
    db_list = []

    if databases:
        # CLI argument takes precedence
        db_names = databases.split(":")
        console.print(f"[cyan]Using databases from CLI: {db_names}[/cyan]")
    elif "databases" in CONFIG.get("reminder", {}):
        # Use config file
        db_names = CONFIG["reminder"]["databases"]
        console.print(f"[cyan]Using databases from config: {db_names}[/cyan]")
    elif use:
        # Fallback to single database from --use
        db_names = [use]
        console.print(f"[cyan]Using single database from --use: {use}[/cyan]")
    else:
        # Default database
        db_names = [None]  # None means use default database
        console.print("[cyan]Using default database[/cyan]")

    # Initialize all databases
    from .database import Database
    from .database import FieldDef
    from pathlib import Path

    for db_name in db_names:
        if db_name:
            # Check if it's an absolute path or relative
            db_path = Path(db_name)
            if db_path.is_absolute():
                # Absolute path: use parent dir as folder, filename as db name
                db_folder = str(db_path.parent)
                db_file = db_path.name
                db_uri = f"sqlite://{db_file}"
                db_obj = Database(db_uri, folder=db_folder)
                display_name = str(db_path)
            else:
                # Relative path: use BASEDIR
                db_uri = f"sqlite://{db_name}"
                db_obj = Database(db_uri, folder=str(BASEDIR))
                display_name = db_name
        else:
            # Use default database (already initialized)
            init_db(None)
            db_obj = db
            display_name = "default"

        # Define table for this database
        tasks_table = db_obj.define_table(
            "dolist_tasks",
            FieldDef("name", "string"),
            FieldDef("tag", "string"),
            FieldDef("status", "string"),
            FieldDef("reminder", "string"),
            FieldDef("reminder_timestamp", "datetime"),
            FieldDef("reminder_repeat", "string"),
            FieldDef("notes", "list:string"),
            FieldDef("created_on", "datetime"),
            FieldDef("deleted", "boolean", default=False),
            FieldDef("priority", "integer", default=0),
            FieldDef("size", "string", default="U"),
        )

        db_list.append((db_obj, tasks_table, display_name))

    console.print("[bold green]Starting DoList Reminder Service[/bold green]")
    console.print(f"[cyan]Monitoring {len(db_list)} database(s)[/cyan]")
    if verbose:
        console.print("[cyan]Verbose mode: ON[/cyan]")
    console.print(f"[cyan]Check interval: {interval} seconds[/cyan]")

    # Run multi-database service loop
    from .service import run_multi_db_service_loop

    run_multi_db_service_loop(db_list, CONFIG, check_interval=interval, verbose=verbose)


@app.command
def reset(
    use: Optional[str] = None,
    yes: Annotated[bool, Parameter(name=["--yes", "-y"])] = False,
):
    """Reset the database (WARNING: deletes all tasks after creating a backup).

    Args:
        use: Database name to use (optional).
        yes: Skip confirmation prompt (use with caution).
    """
    init_db(use)

    # Get the database file path
    dburi = DBURI
    if use:
        dburi = dburi.replace("tasks", use).replace("dopy", use)

    # Extract database filename from URI (e.g., sqlite://tasks.db -> tasks.db)
    db_filename = dburi.replace("sqlite://", "")
    db_path = Path(DBDIR) / db_filename

    if not db_path.exists():
        console.print(f"[yellow]Database file not found: {db_path}[/yellow]")
        console.print("[yellow]Nothing to reset.[/yellow]")
        return

    # Confirmation
    if not yes:
        console.print(
            f"[bold red]WARNING: This will delete all tasks from {db_path}[/bold red]"
        )
        console.print(
            "[yellow]A timestamped backup will be created before deletion.[/yellow]"
        )
        confirmation = input("\nType 'yes' to confirm: ").strip().lower()
        if confirmation != "yes":
            console.print("[green]Reset cancelled.[/green]")
            return

    # Create timestamped backup
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = Path(DBDIR) / f"{db_filename}.backup_{timestamp}"

    try:
        shutil.copy2(db_path, backup_path)
        console.print(f"[green]Backup created: {backup_path}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to create backup: {e}[/red]")
        console.print("[red]Reset aborted for safety.[/red]")
        return

    # Delete the database file
    try:
        db_path.unlink()
        console.print(f"[green]Database reset successfully: {db_path}[/green]")
        console.print("[yellow]A new database will be created on next use.[/yellow]")
    except Exception as e:
        console.print(f"[red]Failed to delete database: {e}[/red]")
        console.print(f"[yellow]Backup is still available at: {backup_path}[/yellow]")


def _parse_default_metadata(default_string: str) -> dict:
    """Parse default metadata string into a dictionary.

    Args:
        default_string: String like "tag=foo priority=5 reminder=3 days size=L"

    Returns:
        Dictionary with parsed metadata
    """
    defaults = {}
    if not default_string:
        return defaults

    # Use a simple state machine to handle multi-word values like "reminder=3 days"
    tokens = default_string.split()
    i = 0
    while i < len(tokens):
        token = tokens[i]

        if "=" in token:
            key, value = token.split("=", 1)
            key = key.strip()

            # Special handling for reminder (can be multi-word like "3 days")
            if key == "reminder":
                # Collect all subsequent tokens that don't contain '='
                reminder_parts = [value]
                i += 1
                while i < len(tokens) and "=" not in tokens[i]:
                    reminder_parts.append(tokens[i])
                    i += 1
                defaults[key] = " ".join(reminder_parts)
                continue

            # Handle priority (convert to int)
            elif key == "priority":
                try:
                    defaults[key] = int(value)
                except ValueError:
                    console.print(
                        f"[yellow]Warning: Invalid priority value '{value}', ignoring[/yellow]"
                    )

            # Handle size (normalize)
            elif key == "size":
                size_upper = value.upper()
                if size_upper in ("SMALL", "MEDIUM", "LARGE", "UNDEFINED"):
                    size_map = {
                        "SMALL": "S",
                        "MEDIUM": "M",
                        "LARGE": "L",
                        "UNDEFINED": "U",
                    }
                    defaults[key] = size_map[size_upper]
                elif size_upper in ("U", "S", "M", "L"):
                    defaults[key] = size_upper
                else:
                    console.print(
                        f"[yellow]Warning: Invalid size value '{value}', ignoring[/yellow]"
                    )

            # Handle other fields (tag, status, etc.)
            else:
                defaults[key] = value

        i += 1

    return defaults


def _parse_markdown_entry(file_path: Path) -> list[dict]:
    """Parse a markdown file containing task entries.

    Format:
        # Task name

        Optional multiline note before any list

        - Note 1
        - Note 2

        > tag tag1,tag2
        > status in-progress
        > reminder 2 hours
        > id 123

    Returns:
        List of task dictionaries with keys: name, tag, status, reminder, notes, id (optional)
    """
    content = file_path.read_text()
    tasks = []
    current_task = None
    current_notes = []
    pre_list_content = []
    in_pre_list = True

    for line in content.split("\n"):
        line_stripped = line.strip()

        # New task starts with #
        if line_stripped.startswith("#"):
            # Save previous task if exists
            if current_task:
                # Add pre-list content as first note if exists
                if pre_list_content:
                    pre_list_note = "\n".join(pre_list_content).strip()
                    if pre_list_note:
                        current_notes.insert(0, pre_list_note)

                current_task["notes"] = current_notes if current_notes else []
                tasks.append(current_task)

            # Start new task
            task_name = line_stripped.lstrip("#").strip()
            current_task = {
                "name": task_name,
                "tag": "default",
                "status": "new",
                "reminder": None,
                "notes": [],
                "priority": 0,
                "size": "U",
            }
            current_notes = []
            pre_list_content = []
            in_pre_list = True

        # Metadata lines start with >
        elif line_stripped.startswith(">"):
            metadata = line_stripped.lstrip(">").strip()

            # Parse metadata
            if metadata.startswith("tag "):
                # Tags can be separated by commas or spaces
                tag_text = metadata[4:].strip()
                # Split by commas and spaces, take the first one
                tags = [
                    t.strip() for t in tag_text.replace(",", " ").split() if t.strip()
                ]
                if tags and current_task:
                    current_task["tag"] = tags[0]

            elif metadata.startswith("status "):
                status = metadata[7:].strip()
                if current_task:
                    current_task["status"] = status

            elif metadata.startswith("reminder "):
                reminder = metadata[9:].strip()
                if current_task:
                    current_task["reminder"] = reminder

            elif metadata.startswith("id "):
                task_id = metadata[3:].strip()
                if current_task:
                    try:
                        current_task["id"] = int(task_id)
                    except ValueError:
                        pass

            elif metadata.startswith("priority "):
                priority = metadata[9:].strip()
                if current_task:
                    try:
                        current_task["priority"] = int(priority)
                    except ValueError:
                        pass

            elif metadata.startswith("size "):
                size = metadata[5:].strip().upper()
                if current_task:
                    # Normalize size value
                    if size in ("SMALL", "MEDIUM", "LARGE", "UNDEFINED"):
                        size_map = {
                            "SMALL": "S",
                            "MEDIUM": "M",
                            "LARGE": "L",
                            "UNDEFINED": "U",
                        }
                        current_task["size"] = size_map[size]
                    elif size in ("U", "S", "M", "L"):
                        current_task["size"] = size
                    # else: keep default 'U'

        # List items become individual notes
        elif line_stripped.startswith("-") or line_stripped.startswith("*"):
            in_pre_list = False
            note_text = line_stripped.lstrip("-*").strip()
            if note_text:
                current_notes.append(note_text)

        # Continuation of list items (indented lines after a list item)
        elif line.startswith("  ") and not in_pre_list and current_notes:
            # Append to the last note
            current_notes[-1] += "\n" + line_stripped

        # Regular content before any list (becomes notes[0])
        elif line_stripped and in_pre_list and current_task:
            pre_list_content.append(line_stripped)

    # Don't forget the last task
    if current_task:
        # Add pre-list content as first note if exists
        if pre_list_content:
            pre_list_note = "\n".join(pre_list_content).strip()
            if pre_list_note:
                current_notes.insert(0, pre_list_note)

        current_task["notes"] = current_notes if current_notes else []
        tasks.append(current_task)

    return tasks


@app.command
def import_tasks(
    filename: str,
    use: Optional[str] = None,
    default: Optional[str] = None,
):
    """Import tasks from a markdown or JSON file.

    Args:
        filename: Path to the file to import (.md or .json).
        use: Database name to use (optional).
        default: Default metadata to apply to all tasks (e.g., "tag=foo priority=5 reminder=3 days size=L").
                 Only applied to tasks that don't have the specific field set in the file.

    Examples:
        dolist import-tasks tasks.md        # Import from markdown
        dolist import-tasks export.json     # Import from JSON
        dolist import-tasks tasks.md --default "tag=work priority=3 size=M"  # With defaults
    """
    init_db(use)

    file_path = Path(filename)

    if not file_path.exists():
        console.print(f"[red]File not found: {filename}[/red]")
        return

    tasks_data = []

    # Parse based on file extension
    if file_path.suffix == ".md":
        console.print(f"[cyan]Parsing markdown file: {filename}[/cyan]")
        tasks_data = _parse_markdown_entry(file_path)

    elif file_path.suffix == ".json":
        console.print(f"[cyan]Parsing JSON file: {filename}[/cyan]")
        try:
            import json as json_module

            with open(file_path) as f:
                tasks_data = json_module.load(f)
        except json.JSONDecodeError as e:
            console.print(f"[red]Invalid JSON file: {e}[/red]")
            return
        except Exception as e:
            console.print(f"[red]Error reading JSON file: {e}[/red]")
            return

    else:
        console.print(f"[red]Unsupported file extension: {file_path.suffix}[/red]")
        console.print("[yellow]Supported extensions: .md, .json[/yellow]")
        return

    if not tasks_data:
        console.print("[yellow]No tasks found in file[/yellow]")
        return

    # Parse default metadata if provided
    default_metadata = _parse_default_metadata(default) if default else {}
    if default_metadata:
        console.print(f"[cyan]Applying default metadata: {default_metadata}[/cyan]")

    # Import tasks
    created_count = 0
    updated_count = 0

    for task_data in tasks_data:
        task_name = task_data.get("name")
        if not task_name:
            console.print("[yellow]Skipping task without name[/yellow]")
            continue

        # Apply default metadata (only for fields not explicitly set in task_data)
        # For markdown files, missing metadata means defaults should apply
        for key, default_value in default_metadata.items():
            # Only apply default if field is not set or is still at its default value
            if key == "tag" and task_data.get("tag") == "default":
                task_data["tag"] = default_value
            elif key == "status" and task_data.get("status") == "new":
                task_data["status"] = default_value
            elif key == "priority" and task_data.get("priority", 0) == 0:
                task_data["priority"] = default_value
            elif key == "size" and task_data.get("size", "U") == "U":
                task_data["size"] = default_value
            elif key == "reminder" and not task_data.get("reminder"):
                task_data["reminder"] = default_value
            elif key not in task_data or task_data[key] is None:
                task_data[key] = default_value

        # Check if this is an update (has 'id' field)
        task_id = task_data.get("id")

        if task_id:
            # Update existing task (including soft-deleted ones)
            result = db(tasks.id == task_id).select()
            if result:
                existing_task = result[0]
                # Parse reminder if provided
                reminder_timestamp = None
                reminder_repeat = None
                reminder_text = task_data.get("reminder")
                if reminder_text:
                    parsed_dt, error, repeat_interval = parse_reminder(reminder_text)
                    if not error:
                        reminder_timestamp = parsed_dt
                        reminder_repeat = repeat_interval

                # Update task fields and undelete if necessary
                existing_task.update_record(
                    name=task_name,
                    tag=task_data.get("tag", "default"),
                    status=task_data.get("status", "new"),
                    reminder=reminder_text,
                    reminder_timestamp=reminder_timestamp,
                    reminder_repeat=reminder_repeat,
                    notes=task_data.get("notes", []),
                    priority=task_data.get("priority", 0),
                    size=task_data.get("size", "U"),
                    deleted=False,  # Undelete the task when importing
                )
                db.commit()
                console.print(f"[green]✓ Updated task {task_id}: {task_name}[/green]")
                updated_count += 1
            else:
                console.print(f"[yellow]Task {task_id} not found, skipping[/yellow]")
        else:
            # Create new task
            reminder_text = task_data.get("reminder")
            reminder_timestamp = None
            reminder_repeat = None
            if reminder_text:
                parsed_dt, error, repeat_interval = parse_reminder(reminder_text)
                if not error:
                    reminder_timestamp = parsed_dt
                    reminder_repeat = repeat_interval

            new_task_id = tasks.insert(
                name=task_name,
                tag=task_data.get("tag", "default"),
                status=task_data.get("status", "new"),
                reminder=reminder_text,
                reminder_timestamp=reminder_timestamp,
                reminder_repeat=reminder_repeat,
                notes=task_data.get("notes", []),
                priority=task_data.get("priority", 0),
                size=task_data.get("size", "U"),
                created_on=datetime.datetime.now(),
            )
            db.commit()
            console.print(f"[green]✓ Created task {new_task_id}: {task_name}[/green]")
            created_count += 1

    # Summary
    console.print("\n[bold cyan]Import Summary:[/bold cyan]")
    if created_count > 0:
        console.print(f"  [green]Created: {created_count} task(s)[/green]")
    if updated_count > 0:
        console.print(f"  [green]Updated: {updated_count} task(s)[/green]")
    console.print(
        f"  [cyan]Total processed: {created_count + updated_count} task(s)[/cyan]"
    )


def main_entry():
    """Entry point for console script."""
    app()


if __name__ == "__main__":
    main_entry()
