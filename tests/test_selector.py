"""Tests for the interactive machine selector.

The selector has a UX requirement: the user must be able to back out
of the selection. We test that this works regardless of which path
the user took (explicit "← 返回" check, ESC, or no selection)."""

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
    """User must always be able to back out of the selection."""

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_esc_returns_empty(self, mock_checkbox):
        """ESC keypress (returns None) → returns []."""
        mock_checkbox.return_value.ask.return_value = None
        result = select_machines(SAMPLE_RESULTS, "2.1.167")
        assert result == []

    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_empty_selection_returns_empty(self, mock_checkbox):
        """User unchecks everything → returns [] (no machines to update)."""
        mock_checkbox.return_value.ask.return_value = []
        result = select_machines(SAMPLE_RESULTS, "2.1.167")
        assert result == []

    @patch("claude_offline_updater.selector.questionary.confirm")
    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_user_confirms_proceed_returns_selection(
        self, mock_checkbox, mock_confirm,
    ):
        """After picking machines, user confirms proceed → returns selection."""
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        mock_confirm.return_value.ask.return_value = True
        result = select_machines(SAMPLE_RESULTS, "2.1.167")
        assert result == [SAMPLE_RESULTS[1]]

    @patch("claude_offline_updater.selector.questionary.confirm")
    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_user_says_no_at_confirm_returns_empty(
        self, mock_checkbox, mock_confirm,
    ):
        """User picks machines then says 'no' at confirm → returns [].

        This is the critical fix: even if the user navigates the checkbox
        and submits with a non-empty selection, the confirm step gives
        them a final chance to back out.
        """
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        mock_confirm.return_value.ask.return_value = False
        result = select_machines(SAMPLE_RESULTS, "2.1.167")
        assert result == []

    @patch("claude_offline_updater.selector.questionary.confirm")
    @patch("claude_offline_updater.selector.questionary.checkbox")
    def test_esc_at_confirm_returns_empty(
        self, mock_checkbox, mock_confirm,
    ):
        """ESC at the confirm step → returns []. User can bail even after picking machines."""
        mock_checkbox.return_value.ask.return_value = [SAMPLE_RESULTS[1]]
        mock_confirm.return_value.ask.return_value = None  # ESC
        result = select_machines(SAMPLE_RESULTS, "2.1.167")
        assert result == []
