"""Tests for core/command_palette.py — command registration and fuzzy search."""

from unittest.mock import MagicMock

from core.command_palette import Command, CommandPalette, create_default_palette


class TestCommand:
    def test_exact_match(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("new chat") == 1.0

    def test_starts_with(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("new") == 0.95

    def test_contains(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("chat") == 0.85

    def test_keyword_match(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None, keywords=["clear", "reset"])
        assert cmd.matches("clea") == 0.75

    def test_fuzzy_match(self):
        cmd = Command("Export Log", "Ctrl+E", "Chat", lambda: None)
        score = cmd.matches("exprt")
        assert score > 0.0
        assert score < 0.75

    def test_no_match(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("zzzzzzz") == 0.0

    def test_empty_query(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("") == 0.5

    def test_case_insensitive(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        assert cmd.matches("NEW CHAT") == 1.0

    def test_default_keywords_empty_list(self):
        cmd = Command("Test", "", "Cat", lambda: None)
        assert cmd.keywords == []

    def test_none_keywords_becomes_empty_list(self):
        cmd = Command("Test", "", "Cat", lambda: None, keywords=None)
        assert cmd.keywords == []

    def test_whitespace_query_trims_and_matches(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        # "  new chat  " stripped becomes "new chat" -> exact match
        assert cmd.matches("  new chat  ") == 1.0

    def test_whitespace_only_query_is_falsy(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None)
        # "   " is truthy string but after strip is "", so matches returns 0.5
        # Wait: the check is `if not query:` not `if not query.strip()`
        # So "   " is truthy, it goes to q = query.lower().strip() = ""
        # Then q == n is False, startswith "" is True -> 0.95
        assert cmd.matches("   ") == 0.95

    def test_fuzzy_ratio_below_threshold_returns_zero(self):
        # A very dissimilar string should have ratio <= 0.5
        cmd = Command("Completely Different", "", "Cat", lambda: None)
        assert cmd.matches("xyz123abc") == 0.0

    def test_keyword_exact_match(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None, keywords=["clear"])
        assert cmd.matches("clear") == 0.75

    def test_keyword_case_insensitive(self):
        cmd = Command("New Chat", "Ctrl+N", "Chat", lambda: None, keywords=["Reset"])
        assert cmd.matches("reset") == 0.75

    def test_multiple_keywords_first_match_wins(self):
        cmd = Command("Cmd", "", "Cat", lambda: None, keywords=["alpha", "beta"])
        # "alp" matches "alpha" -> 0.75
        assert cmd.matches("alp") == 0.75

    def test_fuzzy_match_returns_scaled_ratio(self):
        # "exprt" vs "export log" — ratio > 0.5, scaled by 0.7
        cmd = Command("Export Log", "Ctrl+E", "Chat", lambda: None)
        score = cmd.matches("exprt log")
        assert 0.35 < score < 0.75


class TestCommandPalette:
    def test_register_and_search(self):
        p = CommandPalette()
        p.register("New Chat", "Ctrl+N", "Chat", lambda: "new")
        p.register("Export Log", "Ctrl+E", "Chat", lambda: "export")
        results = p.search("new")
        assert len(results) == 1
        assert results[0][0].name == "New Chat"
        assert results[0][1] > 0.5

    def test_search_returns_sorted_by_score(self):
        p = CommandPalette()
        p.register("New Chat", "Ctrl+N", "Chat", lambda: None)
        p.register("Export Chat", "Ctrl+E", "Chat", lambda: None)
        p.register("Clear Chat", "Ctrl+L", "Chat", lambda: None)
        results = p.search("chat")
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_search_respects_limit(self):
        p = CommandPalette()
        for i in range(20):
            p.register(f"Cmd {i}", "", "Test", lambda: None)
        results = p.search("cmd", limit=5)
        assert len(results) <= 5

    def test_search_no_results(self):
        p = CommandPalette()
        p.register("New Chat", "Ctrl+N", "Chat", lambda: None)
        results = p.search("zzzzz")
        assert results == []

    def test_get_all(self):
        p = CommandPalette()
        p.register("B Command", "", "Zebra", lambda: None)
        p.register("A Command", "", "Apple", lambda: None)
        all_cmds = p.get_all()
        assert all_cmds[0].category == "Apple"
        assert all_cmds[1].category == "Zebra"

    def test_get_categories(self):
        p = CommandPalette()
        p.register("New Chat", "", "Chat", lambda: None)
        p.register("Screenshot", "", "Desktop", lambda: None)
        cats = p.get_categories()
        assert cats == ["Chat", "Desktop"]

    def test_by_shortcut(self):
        p = CommandPalette()
        p.register("New Chat", "Ctrl+N", "Chat", lambda: None)
        cmd = p.by_shortcut("ctrl+n")
        assert cmd is not None
        assert cmd.name == "New Chat"

    def test_by_shortcut_not_found(self):
        p = CommandPalette()
        assert p.by_shortcut("Ctrl+Z") is None

    def test_handler_callable(self):
        results = []

        def handler():
            results.append("called")

        p = CommandPalette()
        p.register("Test", "", "Test", handler)
        _ = p.by_shortcut("")
        # Find the registered command
        cmds = p.get_all()
        cmds[0].handler()
        assert results == ["called"]

    def test_search_empty_palette(self):
        p = CommandPalette()
        results = p.search("anything")
        assert results == []

    def test_search_empty_query(self):
        p = CommandPalette()
        p.register("Test Cmd", "", "Cat", lambda: None)
        results = p.search("")
        # Empty query gives score 0.5 for every command, which is > 0.1 threshold
        assert len(results) == 1
        assert results[0][1] == 0.5

    def test_search_filters_low_scores(self):
        p = CommandPalette()
        p.register("Test Command", "", "Cat", lambda: None)
        # "zzzzz" gives score 0.0, which is below 0.1 threshold
        results = p.search("zzzzz")
        assert results == []

    def test_register_duplicate_names(self):
        p = CommandPalette()
        p.register("Dup", "Ctrl+D", "Cat", lambda: "first")
        p.register("Dup", "Ctrl+E", "Cat", lambda: "second")
        all_cmds = p.get_all()
        assert len(all_cmds) == 2

    def test_get_all_sorted_by_name_within_category(self):
        p = CommandPalette()
        p.register("Zebra", "", "Animal", lambda: None)
        p.register("Apple", "", "Animal", lambda: None)
        p.register("Mango", "", "Fruit", lambda: None)
        p.register("Banana", "", "Fruit", lambda: None)
        all_cmds = p.get_all()
        # Category Animal first, then Fruit
        assert all_cmds[0].name == "Apple"
        assert all_cmds[1].name == "Zebra"
        assert all_cmds[2].name == "Banana"
        assert all_cmds[3].name == "Mango"

    def test_get_categories_returns_sorted_unique(self):
        p = CommandPalette()
        p.register("A", "", "Zebra", lambda: None)
        p.register("B", "", "Apple", lambda: None)
        p.register("C", "", "Zebra", lambda: None)
        cats = p.get_categories()
        assert cats == ["Apple", "Zebra"]

    def test_get_categories_empty_palette(self):
        p = CommandPalette()
        assert p.get_categories() == []

    def test_by_shortcut_case_insensitive(self):
        p = CommandPalette()
        p.register("Test", "Ctrl+A", "Cat", lambda: None)
        assert p.by_shortcut("CTRL+A") is not None
        assert p.by_shortcut("ctrl+a").name == "Test"

    def test_search_default_limit_is_ten(self):
        p = CommandPalette()
        for i in range(15):
            p.register(f"Command {i}", "", "Cat", lambda: None)
        results = p.search("command")
        assert len(results) == 10

    def test_search_with_limit_zero(self):
        p = CommandPalette()
        p.register("Test", "", "Cat", lambda: None)
        results = p.search("test", limit=0)
        assert results == []


class TestCreateDefaultPalette:
    def test_creates_palette_with_commands(self):
        mock_app = MagicMock()
        palette = create_default_palette(mock_app)
        assert isinstance(palette, CommandPalette)
        all_cmds = palette.get_all()
        assert len(all_cmds) > 0

    def test_default_palette_has_chat_commands(self):
        mock_app = MagicMock()
        palette = create_default_palette(mock_app)
        cats = palette.get_categories()
        assert "Chat" in cats

    def test_default_palette_has_agent_commands(self):
        mock_app = MagicMock()
        palette = create_default_palette(mock_app)
        cats = palette.get_categories()
        assert "Agent" in cats

    def test_default_palette_shortcut_lookup(self):
        mock_app = MagicMock()
        palette = create_default_palette(mock_app)
        # "Ctrl+N" is the shortcut for New Chat
        cmd = palette.by_shortcut("ctrl+n")
        assert cmd is not None
        assert cmd.name == "New Chat"

    def test_default_palette_search_returns_results(self):
        mock_app = MagicMock()
        palette = create_default_palette(mock_app)
        results = palette.search("theme")
        assert len(results) > 0
