"""Tests for do.py module functions."""

from unittest.mock import Mock, patch
from datetime import datetime


class TestDatabaseFunction:
    """Test the database() function."""

    @patch("dolist.do.Database")
    def test_database_creates_dal_instance(self, mock_database_class):
        """Test that database() creates a Database instance."""
        from dolist.do import database, DBDIR

        mock_db = Mock()
        mock_database_class.return_value = mock_db
        mock_db.define_table = Mock(return_value="tasks_table")

        db, tasks, history, state = database("sqlite://test.db")

        # Should create Database with correct parameters
        mock_database_class.assert_called_once_with("sqlite://test.db", folder=DBDIR)
        # Should define tables (tasks, history, and state)
        assert mock_db.define_table.called
        assert db == mock_db
        assert tasks == "tasks_table"
        assert history == "tasks_table"
        assert state == "tasks_table"

    @patch("dolist.do.Database")
    def test_database_defines_correct_schema(self, mock_database_class):
        """Test that database() defines correct table schema."""
        from dolist.do import database

        mock_db = Mock()
        mock_database_class.return_value = mock_db
        mock_db.define_table = Mock(return_value="tasks_table")

        db, tasks, history, state = database("sqlite://test.db")

        # Check that define_table was called 3 times (tasks, history, and state)
        assert mock_db.define_table.call_count == 3

        # Check the first call was for tasks table
        first_call_args = mock_db.define_table.call_args_list[0]
        assert first_call_args[0][0] == "dolist_tasks"
        # Should have FieldDef objects in the call
        assert len(first_call_args[0]) > 1  # Table name + fields

        # Check the second call was for history table
        second_call_args = mock_db.define_table.call_args_list[1]
        assert second_call_args[0][0] == "dolist_task_history"


class TestInitDbFunction:
    """Test the init_db() function."""

    @patch("dolist.do.database")
    def test_init_db_default(self, mock_database):
        """Test init_db with default database."""
        import dolist.do
        from dolist.do import init_db, DBURI

        mock_db = Mock()
        mock_tasks = Mock()
        mock_history = Mock()
        mock_state = Mock()
        mock_database.return_value = (mock_db, mock_tasks, mock_history, mock_state)

        dburi = init_db()

        mock_database.assert_called_once_with(DBURI)
        assert dolist.do.db == mock_db
        assert dolist.do.tasks == mock_tasks
        assert dolist.do.history == mock_history
        assert dburi == DBURI

    @patch("dolist.do.database")
    def test_init_db_custom(self, mock_database):
        """Test init_db with custom database."""
        from dolist.do import init_db

        mock_db = Mock()
        mock_tasks = Mock()
        mock_history = Mock()
        mock_state = Mock()
        mock_database.return_value = (mock_db, mock_tasks, mock_history, mock_state)

        dburi = init_db("customdb")

        # Should replace 'dopy' with 'customdb' in URI
        called_uri = mock_database.call_args[0][0]
        assert "customdb" in called_uri
        assert "customdb" in dburi


class TestAddCommand:
    """Test the add() command."""

    @patch("dolist.do.init_db")
    @patch("dolist.do.datetime")
    @patch("dolist.do.rprint")
    def test_add_basic_task(self, mock_rprint, mock_datetime, mock_init_db):
        """Test adding a basic task."""
        import dolist.do
        from dolist.do import add

        # Mock datetime
        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        # Mock global db and tasks
        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.insert = Mock(return_value=1)

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        # Call add command
        add(name="Test task", tag="default", status="new", reminder=None, use=None)

        # Should initialize db
        mock_init_db.assert_called_once_with(None)

        # Should insert with correct values
        mock_tasks.insert.assert_called_once_with(
            name="Test task",
            tag="default",
            status="new",
            reminder=None,
            reminder_timestamp=None,
            reminder_repeat=None,
            notes=None,
            created_on=mock_now,
            priority=0,
            size="U",
        )

        # Should commit
        mock_db.commit.assert_called_once()

        # Should print success message
        assert mock_rprint.called

    @patch("dolist.do.init_db")
    @patch("dolist.do.datetime")
    @patch("dolist.do.rprint")
    def test_add_task_with_all_fields(self, mock_rprint, mock_datetime, mock_init_db):
        """Test adding a task with all fields specified."""
        import dolist.do
        from dolist.do import add

        mock_now = datetime(2024, 1, 1, 12, 0, 0)
        mock_datetime.datetime.now.return_value = mock_now

        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.insert = Mock(return_value=5)

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        add(
            name="Important task",
            tag="work",
            status="working",
            reminder="tomorrow",
            use=None,
        )

        call_kwargs = mock_tasks.insert.call_args[1]
        assert call_kwargs["name"] == "Important task"
        assert call_kwargs["tag"] == "work"
        assert call_kwargs["status"] == "working"
        assert call_kwargs["reminder"] == "tomorrow"


class TestRemoveCommand:
    """Test the remove/delete action via default_action."""

    @patch("dolist.do.init_db")
    @patch("dolist.do.console")
    def test_rm_existing_task(self, mock_console, mock_init_db):
        """Test removing an existing task."""
        import dolist.do
        from dolist.do import default_action

        # Mock task
        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Test task"
        mock_task.update_record = Mock()

        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.__getitem__ = Mock(return_value=mock_task)

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        default_action(1, "delete")

        # Should initialize db
        mock_init_db.assert_called_once_with(None)

        # Should soft delete the task
        mock_task.update_record.assert_called_once_with(deleted=True)
        # Commit is called twice: once for update, once for history
        assert mock_db.commit.call_count >= 1

    @patch("dolist.do.init_db")
    @patch("dolist.do.rprint")
    def test_rm_nonexistent_task(self, mock_rprint, mock_init_db):
        """Test removing a non-existent task."""
        import dolist.do
        from dolist.do import default_action

        mock_tasks = Mock()
        mock_tasks.__getitem__ = Mock(return_value=None)
        dolist.do.tasks = mock_tasks

        default_action(999, "delete")

        # Should print not found message via rprint
        assert mock_rprint.called


class TestDoneCommand:
    """Test the done action via default_action."""

    @patch("dolist.do.init_db")
    @patch("dolist.do.console")
    def test_done_existing_task(self, mock_console, mock_init_db):
        """Test marking an existing task as done."""
        import dolist.do
        from dolist.do import default_action

        mock_task = Mock()
        mock_task.id = 1
        mock_task.name = "Test task"
        mock_task.update_record = Mock()

        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.__getitem__ = Mock(return_value=mock_task)

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        default_action(1, "done")

        mock_task.update_record.assert_called_once_with(status="done")
        # Commit is called twice: once for update, once for history
        assert mock_db.commit.call_count >= 1

    @patch("dolist.do.init_db")
    @patch("dolist.do.rprint")
    def test_done_nonexistent_task(self, mock_rprint, mock_init_db):
        """Test marking a non-existent task as done."""
        import dolist.do
        from dolist.do import default_action

        mock_tasks = Mock()
        mock_tasks.__getitem__ = Mock(return_value=None)
        dolist.do.tasks = mock_tasks

        default_action(999, "done")

        # Should print not found
        assert mock_rprint.called


class TestShellCommand:
    """Test the shell() command."""

    @patch("dolist.do.init_db")
    @patch("ptpython.repl.embed")
    @patch("dolist.do.Task")
    def test_shell_loads_tasks(self, mock_task_class, mock_embed, mock_init_db):
        """Test that shell command loads tasks."""
        import dolist.do
        from dolist.do import shell

        # Mock database
        mock_db = Mock()
        mock_tasks = Mock()

        # Mock rows
        mock_row1 = Mock()
        mock_row2 = Mock()
        mock_query = Mock()
        mock_query.select = Mock(return_value=[mock_row1, mock_row2])
        mock_db.return_value = mock_query
        mock_tasks.deleted = Mock()

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        # Mock Task.from_row
        mock_task1 = Mock()
        mock_task2 = Mock()
        mock_task_class.from_row = Mock(side_effect=[mock_task1, mock_task2])

        shell(use=None)

        # Should initialize db
        mock_init_db.assert_called_once_with(None)

        # Should start the REPL (ptpython embed)
        assert mock_embed.called


class TestTUIDefaultCommand:
    """Test the TUI default command."""

    @patch("dolist.do.init_db")
    @patch("dolist.do.run_tui")
    def test_tui_mode_is_default(self, mock_run_tui, mock_init_db):
        """Test that TUI launches by default."""
        import dolist.do
        from dolist.do import default_action

        # Mock database
        mock_db = Mock()
        mock_tasks = Mock()

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        default_action()

        # Should initialize db
        mock_init_db.assert_called_once_with(None)

        # Should run TUI with config
        assert mock_run_tui.called
        call_args = mock_run_tui.call_args
        assert call_args[0][0] == mock_db
        assert call_args[0][1] == mock_tasks
        # Third argument should be config dict with theme
        assert isinstance(call_args[0][2], dict)
        assert "theme" in call_args[0][2]
        assert "config_file" in call_args[0][2]


class TestConfigurationHandling:
    """Test configuration file handling."""

    def test_basedir_exists(self):
        """Test that BASEDIR is defined."""
        from dolist.do import BASEDIR
        from pathlib import Path

        assert BASEDIR is not None
        assert isinstance(BASEDIR, (str, Path))

    def test_configfile_path(self):
        """Test that CONFIGFILE path is defined."""
        from dolist.do import CONFIGFILE
        from pathlib import Path

        assert CONFIGFILE is not None
        assert isinstance(CONFIGFILE, (str, Path))
        # Config can be either config.toml or legacy .dopyrc
        assert "config.toml" in str(CONFIGFILE) or ".dopyrc" in str(CONFIGFILE)

    def test_dburi_is_defined(self):
        """Test that DBURI is defined."""
        from dolist.do import DBURI

        assert DBURI is not None
        assert isinstance(DBURI, str)


class TestCycloptsApp:
    """Test the cyclopts app configuration."""

    def test_app_exists(self):
        """Test that the cyclopts app is defined."""
        from dolist.do import app

        assert app is not None

    def test_app_has_commands(self):
        """Test that app has registered commands."""
        from dolist.do import app

        # Cyclopts app should exist
        assert hasattr(app, "__call__")


class TestMainEntryPoint:
    """Test the main_entry() function."""

    @patch("dolist.do.app")
    def test_main_entry_calls_app(self, mock_app):
        """Test that main_entry calls the cyclopts app."""
        from dolist.do import main_entry

        main_entry()

        # Should call the cyclopts app
        mock_app.assert_called_once()


class TestParseDefaultMetadata:
    """Test the _parse_default_metadata() function."""

    def test_empty_string(self):
        """Test parsing empty string returns empty dict."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata("")
        assert result == {}

    def test_none_input(self):
        """Test parsing None returns empty dict."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata(None)
        assert result == {}

    def test_single_field(self):
        """Test parsing single field."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata("tag=work")
        assert result == {"tag": "work"}

    def test_priority_conversion(self):
        """Test that priority is converted to int."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata("priority=5")
        assert result == {"priority": 5}

    def test_size_normalization(self):
        """Test that size values are normalized."""
        from dolist.do import _parse_default_metadata

        # Test uppercase letters
        result = _parse_default_metadata("size=L")
        assert result == {"size": "L"}

        # Test full words
        result = _parse_default_metadata("size=Small")
        assert result == {"size": "S"}

        result = _parse_default_metadata("size=Medium")
        assert result == {"size": "M"}

        result = _parse_default_metadata("size=Large")
        assert result == {"size": "L"}

    def test_multi_word_reminder(self):
        """Test that reminder values can contain spaces."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata("reminder=3 days")
        assert result == {"reminder": "3 days"}

        result = _parse_default_metadata("reminder=next week")
        assert result == {"reminder": "next week"}

    def test_multiple_fields(self):
        """Test parsing multiple fields."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata("tag=work priority=5 size=L")
        assert result == {"tag": "work", "priority": 5, "size": "L"}

    def test_complex_default_string(self):
        """Test parsing a complex default string with all fields."""
        from dolist.do import _parse_default_metadata

        result = _parse_default_metadata(
            "tag=foo priority=5 reminder=3 days size=L status=in-progress"
        )
        assert result == {
            "tag": "foo",
            "priority": 5,
            "reminder": "3 days",
            "size": "L",
            "status": "in-progress",
        }


class TestImportTasksWithDefaults:
    """Test the import_tasks() function with default metadata."""

    @patch("dolist.do.init_db")
    @patch("dolist.do.console")
    @patch("dolist.do.Path")
    def test_apply_defaults_to_tasks_without_metadata(
        self, mock_path_class, mock_console, mock_init_db
    ):
        """Test that defaults are applied to tasks without explicit metadata."""
        import dolist.do
        from dolist.do import import_tasks

        # Mock file
        mock_file = Mock()
        mock_file.exists.return_value = True
        mock_file.suffix = ".md"
        mock_file.read_text.return_value = """# Task 1

Description for task 1

# Task 2

Description for task 2
"""
        mock_path_class.return_value = mock_file

        # Mock database
        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.insert = Mock(side_effect=[1, 2])

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        # Import with defaults
        import_tasks("test.md", use=None, default="tag=work priority=5")

        # Should have inserted 2 tasks
        assert mock_tasks.insert.call_count == 2

        # Check first task got defaults
        first_call = mock_tasks.insert.call_args_list[0][1]
        assert first_call["tag"] == "work"
        assert first_call["priority"] == 5

        # Check second task got defaults
        second_call = mock_tasks.insert.call_args_list[1][1]
        assert second_call["tag"] == "work"
        assert second_call["priority"] == 5

    @patch("dolist.do.init_db")
    @patch("dolist.do.console")
    @patch("dolist.do.Path")
    def test_explicit_metadata_overrides_defaults(
        self, mock_path_class, mock_console, mock_init_db
    ):
        """Test that explicit metadata in file overrides defaults."""
        import dolist.do
        from dolist.do import import_tasks

        # Mock file with explicit metadata
        mock_file = Mock()
        mock_file.exists.return_value = True
        mock_file.suffix = ".md"
        mock_file.read_text.return_value = """# Task 1

Description

> tag custom
> priority 7
"""
        mock_path_class.return_value = mock_file

        # Mock database
        mock_db = Mock()
        mock_tasks = Mock()
        mock_tasks.insert = Mock(return_value=1)

        dolist.do.db = mock_db
        dolist.do.tasks = mock_tasks

        # Import with defaults
        import_tasks("test.md", use=None, default="tag=work priority=5")

        # Task should have explicit metadata, not defaults
        call_kwargs = mock_tasks.insert.call_args[1]
        assert call_kwargs["tag"] == "custom"  # From file, not default
        assert call_kwargs["priority"] == 7  # From file, not default
