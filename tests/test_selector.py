"""Tests for the interactive machine selector.

Return-value contract (after removing the '← Back' option):
  - None → user wants to back out silently (ESC). Callers return to
           the previous screen with no warning.
  - [machines...] → run the update on the selected machines. (Never
           empty: callers should treat an unchecked-empty submit as
           a user mistake and warn — but the selector itself doesn't
           return [] anymore.)

Back-out happens only via ESC. The prompt's instruction line tells
the user how to back out, no '← Back' button is shown.
"""

from unittest.mock import patch

from claude_offline_updater.selector import select_machines

SAMPLE_RESULTS = [
    {"name": "localhost", "host": "127.0.0.1", "port": "-", "version": "2.1.167",
     "tags": ["local"], "is_local": True, "machine_id": ""},
    {"name": "public_kfj", "host": "172.30.6.226", "port": 2222, "version": "2.1.165",
     "tags": [], "is_local": False, "machine_id": "m1"},
    {"name": "data_dev", "host": "172.31.1.54", "port": 22, "version": "2.1.167",
     "tags": [], "is_local": False, "machine_id": "m2"},
]


class TestSelectMachinesBackBehavior:

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_esc_returns_none(self, mock_checkbox):
        """ESC at checkbox → None (silent back-out)."""
        mock_checkbox.return_value.ask.return_value = None
        assert select_machines(SAMPLE_RESULTS, "2.1.167") is None

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_machines_only_returns_them(self, mock_checkbox):
        """Submit with machines only → those machines."""
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        assert select_machines(SAMPLE_RESULTS, "2.1.167") == [SAMPLE_RESULTS[1]]

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_no_back_choice_in_choices(self, mock_checkbox):
        """The choices passed to questionary.checkbox should NOT include
        a '← Back' Choice. Only the real machines."""
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        select_machines(SAMPLE_RESULTS, "2.1.167")
        # Inspect the choices that the selector built
        choices = mock_checkbox.call_args.kwargs["choices"]
        titles = [c.title for c in choices]
        assert not any("返回" in t for t in titles), (
            f"Found back-like choice in titles: {titles}"
        )
        assert len(choices) == len(SAMPLE_RESULTS)


class TestSelectorPromptCopy:
    """The prompt copy must instruct the user to press ESC, not to
    check a '← Back' box."""

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_prompt_mentions_esc(self, mock_checkbox):
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        select_machines(SAMPLE_RESULTS, "2.1.167")
        message = mock_checkbox.call_args.args[0]
        # The new prompt should NOT mention checking a back box
        assert "勾选" not in message
        # And should mention ESC instead
        assert "ESC" in message
