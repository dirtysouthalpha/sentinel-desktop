"""Tests for core/command_palette.py — command registration and fuzzy search."""

from core.command_palette import Command, CommandPalette


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
