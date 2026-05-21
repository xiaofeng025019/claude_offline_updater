

from claude_offline_updater.i18n import LANGS, get_lang, set_lang, t


class TestTranslation:
    def test_returns_english_by_default(self):
        set_lang("en")
        result = t("app_title")
        assert result == "Claude Code Offline Updater"

    def test_returns_chinese_after_set_lang_zh(self):
        set_lang("zh")
        result = t("app_title")
        assert result == "Claude Code 离线更新工具"

    def test_returns_key_for_unknown_key(self):
        set_lang("en")
        result = t("nonexistent_key_xyz")
        assert result == "nonexistent_key_xyz"

    def test_kwargs_formatting(self):
        set_lang("en")
        import claude_offline_updater.i18n as i18n_mod
        original = i18n_mod._T.copy()
        i18n_mod._T["test_fmt"] = {"zh": "保留 {kept} 个", "en": "Kept {kept} items"}
        try:
            result = t("test_fmt", kept=3)
            assert "3" in result
            assert "Kept" in result
        finally:
            i18n_mod._T = original

    def test_set_lang_invalid_no_change(self):
        set_lang("en")
        set_lang("fr")
        assert get_lang() == "en"

    def test_get_lang_returns_current(self):
        set_lang("en")
        assert get_lang() == "en"
        set_lang("zh")
        assert get_lang() == "zh"


class TestLangs:
    def test_langs_tuple(self):
        assert isinstance(LANGS, tuple)
        assert "zh" in LANGS
        assert "en" in LANGS

    def test_langs_contains_valid_languages(self):
        for lang in LANGS:
            set_lang(lang)
            assert get_lang() == lang
