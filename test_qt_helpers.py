import ast
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from types import SimpleNamespace

from novel_app.ai_service import SimpleAIService
from novel_app.database import Database
from novel_app.qt.helpers import (
    AI_PROBABILITY_META,
    DEFAULT_AI_PROBABILITY_META,
    compute_template_stats,
    count_text_characters,
    format_chapter_tree_title,
    format_chapter_tree_display_title,
    normalize_ai_color_config,
    normalize_ai_probability_pair,
    previous_chapter_ids_in_order,
    row_to_dict,
    set_ai_probability_meta,
)
from novel_app.structured_templates import (
    BOOK_OUTLINE_FORM_VERSION,
    BOOK_OUTLINE_VOLUME_PLAN_FIELDS,
    CHARACTER_PROFILE_FORM_VERSION,
    WORLD_FORM_VERSION,
    book_outline_form_defaults,
    book_outline_form_to_markdown,
    book_outline_markdown_to_form,
    character_profile_form_defaults,
    character_profile_form_to_markdown,
    character_profile_markdown_to_form,
    coerce_book_outline_markdown,
    coerce_character_markdown,
    coerce_world_markdown,
    merge_book_outline_supplement,
    merge_character_profile_form,
    merge_world_analysis_payload,
    merge_world_form,
    world_form_defaults,
    world_form_to_markdown,
    world_markdown_to_form,
)

try:
    from novel_app.qt_app import (
        AI_PURPOSES,
        DRAWER_TAB_SEQUENCE,
        NovelQtMainWindow,
        _find_plain_text_matches,
        _search_snippet,
    )
    from novel_app.qt.workers import FunctionWorker
except Exception:  # noqa: BLE001
    AI_PURPOSES = []
    DRAWER_TAB_SEQUENCE = ()
    FunctionWorker = None
    NovelQtMainWindow = None
    _find_plain_text_matches = None
    _search_snippet = None


class QtHelperTests(unittest.TestCase):
    def test_row_to_dict_handles_empty_row(self) -> None:
        self.assertEqual(row_to_dict(None), {})
        self.assertEqual(row_to_dict({"id": 1, "title": "书"}), {"id": 1, "title": "书"})

    def test_ai_probability_normalizes_thresholds(self) -> None:
        self.assertEqual(normalize_ai_probability_pair("none", 0), (0, "none"))
        self.assertEqual(normalize_ai_probability_pair("low", 18), (18, "low"))
        self.assertEqual(normalize_ai_probability_pair("medium", 42), (42, "medium"))
        self.assertEqual(normalize_ai_probability_pair("high", 68), (68, "high"))
        self.assertEqual(normalize_ai_probability_pair("certain", 92), (100, "certain"))

    def test_ai_probability_ignores_inconsistent_or_unknown_level(self) -> None:
        self.assertEqual(normalize_ai_probability_pair("high", 0), (0, "none"))
        self.assertEqual(normalize_ai_probability_pair("unknown", 77), (77, "high"))
        self.assertEqual(normalize_ai_probability_pair("low", 150), (100, "certain"))
        self.assertEqual(normalize_ai_probability_pair("medium", -5), (0, "none"))
        self.assertIn("tree", AI_PROBABILITY_META["high"])

    def test_ai_color_config_merges_user_overrides(self) -> None:
        merged = normalize_ai_color_config(
            {
                "high": {"fg": "112233", "bg": "#445566", "tree": "bad"},
                "ghost": {"fg": "#FFFFFF"},
            }
        )
        self.assertEqual(merged["high"]["fg"], "#112233")
        self.assertEqual(merged["high"]["bg"], "#445566")
        self.assertEqual(merged["high"]["tree"], DEFAULT_AI_PROBABILITY_META["high"]["tree"])
        self.assertNotIn("ghost", merged)

    def test_set_ai_probability_meta_updates_shared_mapping(self) -> None:
        try:
            set_ai_probability_meta({"low": {"tree": "#123456"}})
            self.assertEqual(AI_PROBABILITY_META["low"]["tree"], "#123456")
        finally:
            set_ai_probability_meta({})

    @unittest.skipIf(NovelQtMainWindow is None, "Qt app unavailable")
    def test_level2_results_are_compacted_before_level3(self) -> None:
        long_text = "关键事实" + ("很长的重复解释" * 500)
        level2_results = []
        for index in range(12):
            level2_results.append(
                {
                    "level": 2,
                    "group_index": index + 1,
                    "story_summary": long_text,
                    "logic_chain": [long_text for _ in range(12)],
                    "consolidated_facts": [
                        {
                            "claim": long_text,
                            "chapter_ids": [index + 1],
                            "chunk_ids": [f"chunk-{index + 1:04d}"],
                            "evidence_quotes": [long_text],
                            "confidence": "high",
                        }
                        for _ in range(20)
                    ],
                    "chapter_updates": [
                        {
                            "chapter_id": index + 1,
                            "outline": long_text,
                            "events": [long_text for _ in range(5)],
                            "evidence_refs": [f"chunk-{index + 1:04d}"],
                        }
                    ],
                }
            )

        compacted = NovelQtMainWindow._compact_book_analysis_level2_for_level3(level2_results, max_chars=12000)
        compacted_text = json.dumps(compacted, ensure_ascii=False)

        self.assertLessEqual(len(compacted_text), 12500)
        self.assertIn("chunk-0001", compacted_text)
        self.assertIn("evidence_quotes", compacted_text)
        self.assertLess(len(compacted_text), len(json.dumps(level2_results, ensure_ascii=False)) // 4)

    @unittest.skipIf(NovelQtMainWindow is None, "Qt app unavailable")
    def test_level1_results_are_compacted_before_level2(self) -> None:
        long_text = "一级解读" + ("重复证据与解释" * 600)
        level1_results = []
        for index in range(9):
            level1_results.append(
                {
                    "level": 1,
                    "chunk_index": index + 1,
                    "chunk_id": f"chunk-{index + 1:04d}",
                    "chapter_ids": [index + 1],
                    "faithful_digest": long_text,
                    "key_events": [long_text for _ in range(20)],
                    "source_facts": [
                        {
                            "fact_id": f"f{index}-{fact}",
                            "chapter_id": index + 1,
                            "chunk_id": f"chunk-{index + 1:04d}",
                            "claim": long_text,
                            "evidence_quote": long_text,
                        }
                        for fact in range(40)
                    ],
                }
            )

        compacted = NovelQtMainWindow._compact_book_analysis_level1_for_level2(level1_results, max_chars=30000)
        compacted_text = json.dumps(compacted, ensure_ascii=False)

        self.assertLessEqual(len(compacted_text), 32000)
        self.assertIn("chunk-0001", compacted_text)
        self.assertIn("evidence_quote", compacted_text)
        self.assertLess(len(compacted_text), len(json.dumps(level1_results, ensure_ascii=False)) // 5)

    def test_format_chapter_tree_title_preserves_known_titles(self) -> None:
        self.assertEqual(format_chapter_tree_title(1, "第一章 风起"), "第一章 风起")
        self.assertEqual(format_chapter_tree_title(2, "序章"), "序章")
        self.assertEqual(format_chapter_tree_title(3, "番外 旧梦"), "番外 旧梦")
        self.assertEqual(format_chapter_tree_title(4, "| 4 | 雨夜"), "| 4 | 雨夜")

    def test_format_chapter_tree_title_adds_sort_order_for_plain_title(self) -> None:
        self.assertEqual(format_chapter_tree_title(5, "抵达港口"), "第5章 抵达港口")
        self.assertEqual(format_chapter_tree_title("三", "  新线索  "), "第三章 新线索")

    def test_template_stats_and_display_title(self) -> None:
        content = 'alpha beta\n“spoken line”\nmore text'
        stats = compute_template_stats(content)
        self.assertEqual(stats["word_count"], count_text_characters(content))
        self.assertGreater(stats["dialogue_density"], 0)
        self.assertIn("123字", format_chapter_tree_display_title(2, "Plain", word_count=123))
        self.assertTrue(format_chapter_tree_display_title(2, "Plain", is_template=True).startswith("⭐"))

    def test_previous_chapter_ids_keep_library_order_across_volumes(self) -> None:
        rows = [
            {"id": 1, "sort_order": 1, "volume_id": 10},
            {"id": 2, "sort_order": 2, "volume_id": 10},
            {"id": 3, "sort_order": 1, "volume_id": 20},
            {"id": 4, "sort_order": 2, "volume_id": 20},
        ]
        self.assertEqual(previous_chapter_ids_in_order(rows, 4, limit=3), [1, 2, 3])
        self.assertEqual(previous_chapter_ids_in_order(rows, 4, limit=2), [2, 3])
        self.assertEqual(previous_chapter_ids_in_order(rows, 4, limit=0), [])

    @unittest.skipUnless(DRAWER_TAB_SEQUENCE, "PyQt6 is not available")
    def test_drawer_tab_sequence_uses_named_review_tab(self) -> None:
        self.assertEqual(len(DRAWER_TAB_SEQUENCE), len(set(DRAWER_TAB_SEQUENCE)))
        self.assertIn("tasks", DRAWER_TAB_SEQUENCE)
        self.assertIn("review", DRAWER_TAB_SEQUENCE)
        self.assertNotIn("star", DRAWER_TAB_SEQUENCE)
        self.assertLess(DRAWER_TAB_SEQUENCE.index("review"), DRAWER_TAB_SEQUENCE.index("tasks"))
        controller_source = (Path(__file__).resolve().parent / "novel_app" / "qt" / "drawer" / "controller.py").read_text(encoding="utf-8")
        qt_source = (Path(__file__).resolve().parent / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        self.assertNotIn('add_tab("star"', controller_source)
        self.assertNotIn('_open_drawer("star")', qt_source)


    @unittest.skipUnless(DRAWER_TAB_SEQUENCE, "PyQt6 is not available")
    def test_drawer_compatibility_methods_remain_on_main_window(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        for name in (
            "_build_drawer_tabs",
            "_open_drawer",
            "_refresh_drawer",
            "_refresh_visible_drawer_tab",
            "_sync_overview_tab_visibility",
            "_sync_shortcuts_tab_visibility",
            "_sync_outline_tab_for_level",
        ):
            self.assertIn(name, methods)
        self.assertIn("drawer_controller = DrawerController(self)", source)

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_qt_app_reexports_moved_form_and_dialog_classes(self) -> None:
        from novel_app import qt_app
        from novel_app.qt.character_dialog import CharacterDetailDialog as MovedCharacterDetailDialog
        from novel_app.qt.forms import (
            BookOutlineFormWidget as MovedBookOutlineFormWidget,
            CharacterProfileFormWidget as MovedCharacterProfileFormWidget,
            WorldFormWidget as MovedWorldFormWidget,
        )

        self.assertIs(qt_app.BookOutlineFormWidget, MovedBookOutlineFormWidget)
        self.assertIs(qt_app.CharacterProfileFormWidget, MovedCharacterProfileFormWidget)
        self.assertIs(qt_app.WorldFormWidget, MovedWorldFormWidget)
        self.assertIs(qt_app.CharacterDetailDialog, MovedCharacterDetailDialog)

    @unittest.skipUnless(DRAWER_TAB_SEQUENCE, "PyQt6 is not available")
    def test_drawer_controller_open_routes_known_tabs(self) -> None:
        from novel_app.qt.drawer import DrawerController

        class FakeTabs:
            def __init__(self) -> None:
                self.current_index = 0

            def setCurrentIndex(self, index: int) -> None:
                self.current_index = index

        class FakeDrawer:
            def __init__(self) -> None:
                self.visible = False
                self.minimum_width = 0
                self.fixed_width = 0

            def setMinimumWidth(self, width: int) -> None:
                self.minimum_width = width

            def setVisible(self, visible: bool) -> None:
                self.visible = visible

            def setFixedWidth(self, width: int) -> None:
                self.fixed_width = width

        class FakeWindow(SimpleNamespace):
            def width(self) -> int:
                return 1200

        window = FakeWindow(
            state=SimpleNamespace(selected_book_id=1, current_node_kind="book", drawer_kind=""),
            drawer_tab_indexes={"outline": 0, "review": 1, "tasks": 2},
            drawer_tabs=FakeTabs(),
            qt_drawer_width=420,
            drawer=FakeDrawer(),
        )
        controller = DrawerController(window)
        controller.update_title = lambda: None
        controller.refresh = lambda: None

        controller.open("review")
        self.assertEqual(window.drawer_tabs.current_index, 1)
        controller.open("tasks")
        self.assertEqual(window.drawer_tabs.current_index, 2)
        controller.open("star")
        self.assertEqual(window.drawer_tabs.current_index, 0)
        controller.open("details")
        self.assertEqual(window.drawer_tabs.current_index, 0)

    @unittest.skipUnless(AI_PURPOSES, "PyQt6 is not available")
    def test_ai_purposes_include_dedicated_correction_profile(self) -> None:
        purpose_map = dict(AI_PURPOSES)
        self.assertIn("correction", purpose_map)
        self.assertEqual(purpose_map["correction"], "AI纠错")
        self.assertIn("chat", purpose_map)

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_legacy_ai_settings_backfill_chat_profile(self) -> None:
        with TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "ai_settings.json"
            config_path.write_text(
                '{"remote_enabled": true, "api_key": "sk-test", "base_url": "https://example.com/v1", "model": "model-test"}',
                encoding="utf-8",
            )
            window = NovelQtMainWindow.__new__(NovelQtMainWindow)
            window.ai_config_path = config_path
            window.ai_service = SimpleAIService()

            window._load_ai_settings()

            profiles = window.ai_settings["profiles"]
            self.assertTrue(profiles["chat"]["remote_enabled"])
            self.assertEqual(profiles["chat"]["model"], "model-test")
            self.assertIsNotNone(window._ai_service_for_purpose("chat"))
            stored = config_path.read_text(encoding="utf-8")
            self.assertIn('"version"', stored)
            self.assertIn('"prompt_settings_version"', stored)
            self.assertIn('"chat"', stored)

    def test_legacy_local_typo_module_is_removed_from_runtime(self) -> None:
        project_root = Path(__file__).resolve().parent
        self.assertFalse((project_root / "novel_app" / ("spell" "_check.py")).exists())
        source = (project_root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        self.assertNotIn("novel_app." + "spell" + "_check", source)
        self.assertNotIn("from " + "spell" + "_check", source)

    def test_launcher_places_user_data_next_to_exe(self) -> None:
        project_root = Path(__file__).resolve().parent
        source = (project_root / "packaging" / "Launcher.cs").read_text(encoding="utf-8")
        self.assertIn('Path.Combine(exeDir, "data")', source)
        self.assertIn('startInfo.EnvironmentVariables["SIMPLE_AI_NOVEL_DATA_DIR"] = dataDir', source)
        self.assertIn("SIMPLE_AI_NOVEL_LEGACY_DATA_DIRS", source)

    def test_window_title_uses_lingshu_v13(self) -> None:
        project_root = Path(__file__).resolve().parent
        qt_source = (project_root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        main_source = (project_root / "main.py").read_text(encoding="utf-8")
        self.assertIn('APP_DISPLAY_NAME = "灵枢v1.3"', qt_source)
        self.assertIn("self.setWindowTitle(APP_DISPLAY_NAME)", qt_source)
        self.assertIn("base_title = APP_DISPLAY_NAME", qt_source)
        self.assertIn('app.setApplicationName("灵枢v1.3")', main_source)
        self.assertNotIn("Simple AI Novel App - PyQt6 Workbench", qt_source)

    def test_launcher_has_native_splash_before_python_start(self) -> None:
        project_root = Path(__file__).resolve().parent
        source = (project_root / "packaging" / "Launcher.cs").read_text(encoding="utf-8")
        self.assertIn("LauncherSplash", source)
        self.assertIn('splash = new LauncherSplash(LauncherConfig.AppName)', source)
        self.assertIn('startInfo.EnvironmentVariables["SIMPLE_AI_NOVEL_NATIVE_SPLASH"] = "1"', source)
        self.assertIn("WaitForChildWindow(child, splash)", source)
        self.assertIn("PaintLightSplash", source)
        self.assertIn("Color.FromArgb(246, 249, 255)", source)
        self.assertLess(source.index("splash.Show()"), source.index("Process.Start(startInfo)"))

    def test_startup_splash_uses_elegant_light_layout(self) -> None:
        project_root = Path(__file__).resolve().parent
        qt_source = (project_root / "novel_app" / "qt" / "startup.py").read_text(encoding="utf-8")
        launcher_source = (project_root / "packaging" / "Launcher.cs").read_text(encoding="utf-8")

        self.assertIn("self.setFixedSize(620, 380)", qt_source)
        self.assertIn("APP_SUBTITLE", qt_source)
        self.assertIn("STARTUP_IMAGE", qt_source)
        self.assertIn("QPixmap", qt_source)
        self.assertIn("_paint_anime_splash", qt_source)
        self.assertIn("_draw_teal_flame", qt_source)
        self.assertIn("QPainterPath", qt_source)
        self.assertNotIn('"Truth"', qt_source)
        self.assertNotIn('"RAG"', qt_source)
        self.assertIn("Width = 620;", launcher_source)
        self.assertIn("Height = 380;", launcher_source)
        self.assertIn("PaintElegantLightSplash(g)", launcher_source)
        self.assertIn("LoadSplashImage()", launcher_source)
        self.assertIn("PaintAnimeSplash(g)", launcher_source)
        self.assertIn("startup_anime.jpg", launcher_source)
        self.assertIn("DrawTealFlame(g", launcher_source)
        build_source = (project_root / "packaging" / "build_first_exe_fast.ps1").read_text(encoding="utf-8")
        self.assertIn("StartupSplashImage", build_source)
        self.assertIn("startup_anime.jpg", build_source)

    def test_startup_splash_is_shown_before_database_initialization(self) -> None:
        project_root = Path(__file__).resolve().parent
        main_source = (project_root / "main.py").read_text(encoding="utf-8")
        self.assertIn("StartupSplash", main_source)
        self.assertIn("splash.show_stage", main_source)
        self.assertLess(main_source.index("splash.show_stage"), main_source.index("database = Database()"))
        self.assertIn('SIMPLE_AI_NOVEL_NATIVE_SPLASH") != "1"', main_source)

        qt_source = (project_root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        self.assertIn("startup_splash", qt_source)
        self.assertIn("startup_splash.finish(window)", qt_source)

    def test_ai_settings_source_backfills_chat_from_legacy_writing_profile(self) -> None:
        project_root = Path(__file__).resolve().parent
        source = (project_root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        self.assertIn("AI_SETTINGS_VERSION", source)
        self.assertIn("profiles[purpose] = dict(writing_profile)", source)
        self.assertIn("profiles[purpose] = (", source)

    def test_settings_menu_exposes_prompt_configuration(self) -> None:
        project_root = Path(__file__).resolve().parent
        qt_source = (project_root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        dialogs_source = (project_root / "novel_app" / "qt" / "dialogs.py").read_text(encoding="utf-8")

        self.assertIn("PROMPT_SETTING_ENTRIES", qt_source)
        self.assertIn("PROMPT_SETTINGS_VERSION", qt_source)
        self.assertIn("prompt_settings_version", qt_source)
        self.assertIn("DEEPSEEK_CHAT_SYSTEM_PROMPT", qt_source)
        self.assertIn("Agent 与提示词配置", qt_source)
        self.assertIn("_open_prompt_settings", qt_source)
        self.assertIn("_save_prompt_settings", qt_source)
        self.assertIn("prompt_overrides", qt_source)
        self.assertIn("PromptSettingsDialog", dialogs_source)
        self.assertIn("恢复当前默认", dialogs_source)
        self.assertIn("全部恢复默认", dialogs_source)

    def test_prompt_defaults_use_deepseek_style_sections(self) -> None:
        project_root = Path(__file__).resolve().parent
        source = (project_root / "novel_app" / "prompt_settings.py").read_text(encoding="utf-8")

        self.assertIn('PROMPT_SETTINGS_VERSION = "prompt_settings_v2_deepseek_style"', source)
        self.assertIn("#### 定位", source)
        self.assertIn("#### 能力", source)
        self.assertIn("#### 输出", source)
        self.assertIn('"scene_plan"', source)
        self.assertIn('"findings"', source)
        self.assertIn('"revised_content"', source)

    def test_agent_graph_uses_custom_prompt_overrides(self) -> None:
        project_root = Path(__file__).resolve().parent
        graph_source = (project_root / "novel_app" / "agents" / "graph.py").read_text(encoding="utf-8")
        planner_source = (project_root / "novel_app" / "agents" / "planner.py").read_text(encoding="utf-8")
        writer_source = (project_root / "novel_app" / "agents" / "writer.py").read_text(encoding="utf-8")
        service_source = (project_root / "novel_app" / "ai_service.py").read_text(encoding="utf-8")

        self.assertIn("prompt_overrides", graph_source)
        self.assertIn("agent._prompt_overrides", graph_source)
        self.assertIn("prompt_value(self._prompt_overrides", planner_source)
        self.assertIn("render_prompt(", planner_source)
        self.assertIn("prompt_value(self._prompt_overrides", writer_source)
        self.assertIn("set_prompt_overrides", service_source)
        self.assertIn("prompt_overrides=self.get_prompt_overrides()", service_source)

    def test_ai_correction_discards_stale_editor_content(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_auto_correct_chapter"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("detect_chinese_typos(content, require_remote=True)", segment)
        self.assertIn("self.content_editor.toPlainText() != content", segment)
        self.assertIn("本次 AI 纠错结果已丢弃", segment)

    def test_chat_context_uses_builtin_truth_and_rag(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_chat_context_prompt"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("BUILTIN_CHAT_SYSTEM_PROMPT", source)
        self.assertIn("latest_user_message", segment)
        self.assertIn("【Truth File：必须优先遵守】", segment)
        self.assertIn("_build_truth_context(book_id, chapter_id, max_chars=9000)", segment)
        self.assertIn("_build_chat_rag_query", segment)
        self.assertIn("_index_book_design_for_rag(book_id)", segment)
        self.assertIn("_build_rag_context(book_id, rag_query, top_k=6)", segment)
        self.assertIn("【RAG 检索结果：与当前问题相关】", segment)
        self.assertIn("self.chapter_outline_editor.toPlainText().strip()", segment)
        self.assertIn("self.content_editor.toPlainText().strip()", segment)

    def test_chat_dialog_passes_latest_user_message_to_context_builder(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt" / "chat_dialog.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertIn(
            "Callable[[dict[str, Any] | None, dict[str, Any] | None, str], str]",
            source,
        )
        self.assertIn("self.context_builder(self.ai_character, self.self_character, text)", source)

    @unittest.skipUnless(_find_plain_text_matches and _search_snippet, "PyQt6 is not available")
    def test_search_helpers_support_case_and_whole_word_options(self) -> None:
        assert _find_plain_text_matches is not None
        assert _search_snippet is not None
        text = "Alpha beta alphabet Alpha"
        self.assertEqual(_find_plain_text_matches(text, "alpha"), [(0, 5), (11, 16), (20, 25)])
        self.assertEqual(_find_plain_text_matches(text, "Alpha", case_sensitive=True), [(0, 5), (20, 25)])
        self.assertEqual(_find_plain_text_matches(text, "alpha", whole_word=True), [(0, 5), (20, 25)])
        self.assertIn("Alpha beta", _search_snippet(text, 0, 5))

    def test_create_chapter_after_current_has_no_removed_mapping_helper_call(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        tree = ast.parse(source_path.read_text(encoding="utf-8"))
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_create_chapter_after_current"
        ]
        self.assertEqual(len(methods), 1)
        called_attributes = {
            node.attr
            for node in ast.walk(methods[0])
            if isinstance(node, ast.Attribute)
        }
        self.assertNotIn("_save_chapter_book_title_mapping", called_attributes)

    def test_library_tree_reload_preserves_expanded_nodes(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in {
                "_load_library_tree",
                "_collect_expanded_tree_keys",
                "_restore_expanded_tree_keys",
            }
        }

        self.assertIn("preserve_expansion", methods["_load_library_tree"])
        self.assertIn("_collect_expanded_tree_keys()", methods["_load_library_tree"])
        self.assertIn("collapseAll()", methods["_load_library_tree"])
        self.assertIn("_restore_expanded_tree_keys(expanded_keys)", methods["_load_library_tree"])
        self.assertIn("_expand_to_key(target)", methods["_load_library_tree"])
        self.assertIn("isExpanded(index)", methods["_collect_expanded_tree_keys"])
        self.assertIn("setExpanded(index, True)", methods["_restore_expanded_tree_keys"])

    def test_delete_chapter_reloads_parent_container_not_whole_book(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_delete_chapter"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""

        self.assertIn('volume_id = chapter["volume_id"]', segment)
        self.assertIn('("group", None, book_id)', segment)
        self.assertIn('("volume", int(volume_id), None)', segment)
        self.assertIn("self._load_library_tree(key)", segment)
        self.assertIn("self._activate_tree_key(key)", segment)
        self.assertNotIn('key = ("book", book_id, None)', segment)

    def test_structured_markdown_areas_use_toggle_stack_not_side_by_side_preview(self) -> None:
        root = Path(__file__).resolve().parent
        qt_source = (root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        pages_source = (root / "novel_app" / "qt" / "drawer" / "pages.py").read_text(encoding="utf-8")
        characters_source = (root / "novel_app" / "qt" / "drawer" / "characters.py").read_text(encoding="utf-8")
        world_source = (root / "novel_app" / "qt" / "drawer" / "world.py").read_text(encoding="utf-8")
        source = qt_source + "\n" + pages_source + "\n" + characters_source + "\n" + world_source
        self.assertIn("outline_markdown_toggle_btn", source)
        self.assertIn("character_markdown_toggle_btn", source)
        self.assertIn("world_markdown_toggle_btn", source)
        self.assertIn("outline_markdown_stack = QStackedWidget()", source)
        self.assertIn("character_markdown_stack = QStackedWidget()", source)
        self.assertIn("world_markdown_stack = QStackedWidget()", source)
        self.assertNotIn("outline_splitter.addWidget(self.outline_markdown_preview)", source)
        self.assertNotIn("profile_splitter.addWidget(self.character_profile_preview)", source)
        self.assertNotIn("world_content_splitter.addWidget(self.world_content_preview)", source)

    def test_structured_markdown_areas_offer_checkbox_toggle(self) -> None:
        root = Path(__file__).resolve().parent
        qt_source = (root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        pages_source = (root / "novel_app" / "qt" / "drawer" / "pages.py").read_text(encoding="utf-8")
        forms_source = (root / "novel_app" / "qt" / "forms.py").read_text(encoding="utf-8")
        source = qt_source + "\n" + pages_source + "\n" + forms_source
        self.assertIn("BookOutlineFormWidget", source)
        self.assertIn("CharacterProfileFormWidget", source)
        self.assertIn("WorldFormWidget", source)
        self.assertIn("outline_checkbox_btn", source)
        self.assertNotIn("character_checkbox_btn", source)
        self.assertNotIn("world_checkbox_btn", source)
        self.assertIn("_toggle_markdown_checkbox", source)
        self.assertIn("_toggle_markdown_checkbox_line", source)

    def test_world_tab_uses_single_form_not_entry_picker(self) -> None:
        root = Path(__file__).resolve().parent
        qt_source = (root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        pages_source = (root / "novel_app" / "qt" / "drawer" / "pages.py").read_text(encoding="utf-8")
        source = (root / "novel_app" / "qt" / "drawer" / "world.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_world_tab"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("WorldFormWidget", segment)
        self.assertIn("world_markdown_stack.addWidget(window.world_form)", segment)
        self.assertNotIn("world_list", segment)
        self.assertNotIn("world_search", segment)
        self.assertNotIn("world_name", segment)
        self.assertNotIn("world_category", segment)
        qt_tree = ast.parse(qt_source)
        wrappers = [
            node
            for node in ast.walk(qt_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_world_tab"
        ]
        self.assertEqual(len(wrappers), 1)
        self.assertIn("drawer_pages.build_world_tab(self)", ast.get_source_segment(qt_source, wrappers[0]) or "")
        pages_tree = ast.parse(pages_source)
        page_wrappers = [
            node
            for node in ast.walk(pages_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_world_tab"
        ]
        self.assertEqual(len(page_wrappers), 1)
        self.assertIn("world.build_world_tab(window)", ast.get_source_segment(pages_source, page_wrappers[0]) or "")

    def test_character_tab_uses_list_and_detail_dialog(self) -> None:
        root = Path(__file__).resolve().parent
        qt_source = (root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        pages_source = (root / "novel_app" / "qt" / "drawer" / "pages.py").read_text(encoding="utf-8")
        source = (root / "novel_app" / "qt" / "drawer" / "characters.py").read_text(encoding="utf-8")
        dialog_source = (root / "novel_app" / "qt" / "character_dialog.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_characters_tab"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("characters_list = QListWidget()", segment)
        self.assertIn("_open_character_from_list_item", segment)
        self.assertIn("_ensure_character_detail_dialog", segment)
        self.assertIn("class CharacterDetailDialog", dialog_source)
        self.assertIn("_confirm_character_edit_navigation", dialog_source)
        self.assertIn("item.setData(ID_ROLE, character_id)", source)
        self.assertIn("QListWidgetItem(f\"{name} \u00b7 {role}\")", source)
        self.assertIn("_open_character_detail_dialog", source)
        self.assertIn("select_character_from_picker", source)
        self.assertIn("_select_character_from_picker", qt_source)
        self.assertNotIn("character_picker_btn", segment)
        self.assertNotIn("character_picker_label", segment)
        self.assertNotIn("character_list_toggle", source)
        qt_tree = ast.parse(qt_source)
        wrappers = [
            node
            for node in ast.walk(qt_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_build_characters_tab"
        ]
        self.assertEqual(len(wrappers), 1)
        self.assertIn("drawer_pages.build_characters_tab(self)", ast.get_source_segment(qt_source, wrappers[0]) or "")
        pages_tree = ast.parse(pages_source)
        page_wrappers = [
            node
            for node in ast.walk(pages_tree)
            if isinstance(node, ast.FunctionDef) and node.name == "build_characters_tab"
        ]
        self.assertEqual(len(page_wrappers), 1)
        self.assertIn("characters.build_characters_tab(window)", ast.get_source_segment(pages_source, page_wrappers[0]) or "")

    def test_review_drawer_logic_lives_in_review_module(self) -> None:
        root = Path(__file__).resolve().parent
        pages_source = (root / "novel_app" / "qt" / "drawer" / "pages.py").read_text(encoding="utf-8")
        review_source = (root / "novel_app" / "qt" / "drawer" / "review.py").read_text(encoding="utf-8")
        pages_tree = ast.parse(pages_source)
        review_tree = ast.parse(review_source)
        pages_methods = {
            node.name: ast.get_source_segment(pages_source, node) or ""
            for node in ast.walk(pages_tree)
            if isinstance(node, ast.FunctionDef)
        }
        review_methods = {
            node.name: ast.get_source_segment(review_source, node) or ""
            for node in ast.walk(review_tree)
            if isinstance(node, ast.FunctionDef)
        }
        for name in (
            "build_review_tab",
            "refresh_review_tab",
            "on_review_run_selected",
            "render_review_run_detail",
            "selected_review_run",
            "view_selected_review_snapshot",
            "restore_selected_review_snapshot",
            "copy_selected_review_truth_file",
        ):
            self.assertIn(name, review_methods)
            self.assertIn(name, pages_methods)
            self.assertIn(f"review.{name}", pages_methods[name])
        self.assertIn("window.review_runs_list = QListWidget()", review_methods["build_review_tab"])
        self.assertNotIn("window.review_runs_list = QListWidget()", pages_source)

    def test_remaining_drawer_pages_live_in_page_modules(self) -> None:
        root = Path(__file__).resolve().parent
        drawer_root = root / "novel_app" / "qt" / "drawer"
        pages_source = (drawer_root / "pages.py").read_text(encoding="utf-8")
        pages_tree = ast.parse(pages_source)
        pages_methods = {
            node.name: ast.get_source_segment(pages_source, node) or ""
            for node in ast.walk(pages_tree)
            if isinstance(node, ast.FunctionDef)
        }
        wrappers = {
            "build_outline_tab": "outline.build_outline_tab",
            "build_overview_tab": "overview.build_overview_tab",
            "build_shortcuts_tab": "shortcuts.build_shortcuts_tab",
            "build_skills_tab": "skills.build_skills_tab",
            "build_task_tab": "tasks.build_task_tab",
            "refresh_overview": "overview.refresh_overview",
            "refresh_skills": "skills.refresh_skills",
            "on_enabled_skill_selected": "skills.on_enabled_skill_selected",
        }
        for method_name, target in wrappers.items():
            self.assertIn(method_name, pages_methods)
            self.assertIn(target, pages_methods[method_name])

        module_markers = {
            "outline.py": "window.chapter_outline_editor = QPlainTextEdit()",
            "overview.py": "window.sourcebook_preview = QPlainTextEdit()",
            "shortcuts.py": "window.shortcuts_list = QListWidget()",
            "skills.py": "window.enabled_skills_list = QListWidget()",
            "tasks.py": "window.task_summary_panel = QFrame()",
        }
        for filename, marker in module_markers.items():
            source = (drawer_root / filename).read_text(encoding="utf-8")
            self.assertIn(marker, source)
            self.assertNotIn(marker, pages_source)

    def test_book_outline_form_round_trips_to_markdown(self) -> None:
        data = book_outline_form_defaults("示例书")
        data["fields"]["length_long"]["checked"] = True
        data["fields"]["main_genre"]["value"] = "玄幻"
        data = merge_book_outline_supplement(data, "示例书", "导入的大纲补充", supplement_title="导入补充")

        markdown = book_outline_form_to_markdown(data, "示例书")
        parsed = book_outline_markdown_to_form(markdown, "示例书")

        self.assertEqual(parsed["version"], BOOK_OUTLINE_FORM_VERSION)
        self.assertTrue(parsed["fields"]["length_long"]["checked"])
        self.assertEqual(parsed["fields"]["main_genre"]["value"], "玄幻")
        self.assertEqual(parsed["supplements"][0]["title"], "导入补充")
        self.assertIn("导入的大纲补充", parsed["supplements"][0]["content"])
        self.assertIn("- [x] 长篇（60 万-200 万字）", markdown)
        self.assertIn("## 1.8 爽点与虐点设计", markdown)

    def test_book_outline_form_renders_volume_plan_sections(self) -> None:
        volumes = [
            {"id": 10, "title": "风起", "sort_order": 1},
            {"id": 20, "title": "潮落", "sort_order": 2},
        ]
        data = book_outline_form_defaults("示例书", volumes)
        data["volume_plans"][0]["fields"]["core_events"]["value"] = "主角离开故乡"
        data["volume_plans"][1]["fields"]["stage_goal"]["value"] = "夺回王城"

        markdown = book_outline_form_to_markdown(data, "示例书", volumes)
        parsed = book_outline_markdown_to_form(markdown, "示例书", volumes)

        self.assertIn("### 第1卷规划：风起", markdown)
        self.assertIn("### 第2卷规划：潮落", markdown)
        self.assertIn("- 核心事件：主角离开故乡", markdown)
        self.assertIn("- 阶段目标：夺回王城", markdown)
        self.assertEqual({item["id"] for item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS}, {
            "core_events",
            "stage_goal",
            "character_appearances",
            "main_conflict",
            "key_turning",
            "ending_hook",
        })
        self.assertEqual(parsed["volume_plans"][0]["volume_id"], "10")
        self.assertEqual(parsed["volume_plans"][0]["fields"]["core_events"]["value"], "主角离开故乡")
        self.assertEqual(parsed["volume_plans"][1]["fields"]["stage_goal"]["value"], "夺回王城")

    def test_world_form_round_trips_to_markdown(self) -> None:
        data = world_form_defaults()
        data["fields"]["shape_fictional"]["checked"] = True
        data["fields"]["supernatural_level"]["value"] = "高魔"
        data["fields"]["world_rules_table"]["value"] = "世界名称：雾海\n世界核心禁忌：不可直视旧神"
        markdown = world_form_to_markdown(data)
        parsed = world_markdown_to_form(markdown)

        self.assertEqual(parsed["version"], WORLD_FORM_VERSION)
        self.assertTrue(parsed["fields"]["shape_fictional"]["checked"])
        self.assertEqual(parsed["fields"]["supernatural_level"]["value"], "高魔")
        self.assertIn("不可直视旧神", parsed["fields"]["world_rules_table"]["value"])
        self.assertIn("## 2.6 世界危机与冲突", markdown)
        self.assertIn("- [x] 架空世界", markdown)

    def test_world_form_merge_only_fills_empty_fields(self) -> None:
        base = world_form_defaults()
        base["fields"]["supernatural_level"]["value"] = "低魔"
        incoming = world_form_defaults()
        incoming["fields"]["shape_otherworld"]["checked"] = True
        incoming["fields"]["supernatural_level"]["value"] = "高魔"
        incoming["fields"]["tech_level"]["value"] = "蒸汽"

        merged = merge_world_form(base, incoming)

        self.assertTrue(merged["fields"]["shape_otherworld"]["checked"])
        self.assertEqual(merged["fields"]["supernatural_level"]["value"], "低魔")
        self.assertEqual(merged["fields"]["tech_level"]["value"], "蒸汽")

    def test_world_form_merge_accepts_ai_label_and_scalar_fields(self) -> None:
        incoming = {
            "fields": {
                "架空世界": True,
                "科技水平": "蒸汽工业",
                "世界规则填报表": "世界名称：雾海\n世界核心禁忌：不可直视旧神",
            }
        }

        merged = merge_world_form(world_form_defaults(), incoming)

        self.assertTrue(merged["fields"]["shape_fictional"]["checked"])
        self.assertEqual(merged["fields"]["tech_level"]["value"], "蒸汽工业")
        self.assertIn("不可直视旧神", merged["fields"]["world_rules_table"]["value"])

    def test_world_analysis_payload_preserves_nameless_world_entries(self) -> None:
        merged = merge_world_analysis_payload(
            world_form_defaults(),
            world_entries=[
                {"category": "规则", "content": "死亡会留下可交易的记忆。"},
                {"description": "王都建立在旧神遗骨上。"},
            ],
            world_text="世界通用货币：银叶。",
        )
        markdown = world_form_to_markdown(merged)

        self.assertIn("死亡会留下可交易的记忆", markdown)
        self.assertIn("王都建立在旧神遗骨上", markdown)
        self.assertIn("世界通用货币：银叶", markdown)

    def test_legacy_book_outline_markdown_is_preserved_as_supplement(self) -> None:
        parsed = book_outline_markdown_to_form("旧版书籍大纲", "旧书")
        markdown = book_outline_form_to_markdown(parsed, "旧书")
        self.assertIn("# 书籍大纲模板", markdown)
        self.assertIn("旧版内容", markdown)
        self.assertIn("旧版书籍大纲", markdown)

    def test_structured_templates_keep_full_base_template_for_partial_markdown(self) -> None:
        book = coerce_book_outline_markdown("## AI摘要\n主线已经明确。", "示例书")
        self.assertIn("# 书籍大纲模板", book)
        self.assertIn("## 1.2 篇幅与结构", book)
        self.assertIn("- [ ] 长篇（60 万-200 万字）", book)
        self.assertIn("## AI/用户补充", book)
        self.assertIn("## AI摘要", book)

        world = coerce_world_markdown("# 王都\n政治中心", "王都", "地点")
        self.assertIn("# 世界观设定模板", world)
        self.assertIn("## 2.1 世界基础形态", world)
        self.assertIn("- [ ] 架空世界", world)

        character = coerce_character_markdown("## 已有人物信息\n很可靠。", "阿宁", "主角")
        self.assertIn("# 主角设定模板", character)
        self.assertIn("## 3.1 基础身份", character)
        self.assertIn("- [ ] 普通人", character)

    def test_blank_character_template_switches_role_without_nested_template(self) -> None:
        original = coerce_character_markdown("", "林一", "")

        updated = coerce_character_markdown(original, "林一", "男主", "林一", "")

        self.assertIn("# 主角设定模板", updated)
        self.assertIn("- 身份/职业：男主", updated)
        self.assertNotIn("# 配角设定模板", updated)
        self.assertNotIn("## AI/用户补充", updated)

    def test_character_profile_form_round_trips_to_markdown(self) -> None:
        data = character_profile_form_defaults("林一", "男主")
        data["fields"]["identity_common"]["checked"] = True
        data["fields"]["personality_main"]["value"] = "冷静、热血"
        data["fields"]["desire_fear_table"]["value"] = "公开目标：守住王城"

        markdown = character_profile_form_to_markdown(data, "林一", "男主")
        parsed = character_profile_markdown_to_form(markdown, "林一", "男主")

        self.assertEqual(parsed["version"], CHARACTER_PROFILE_FORM_VERSION)
        self.assertEqual(parsed["schema"], "protagonist")
        self.assertTrue(parsed["fields"]["identity_common"]["checked"])
        self.assertEqual(parsed["fields"]["personality_main"]["value"], "冷静、热血")
        self.assertIn("公开目标：守住王城", parsed["fields"]["desire_fear_table"]["value"])
        self.assertIn("# 主角设定模板", markdown)
        self.assertIn("- [x] 普通人", markdown)

    def test_character_profile_form_merge_only_fills_empty_fields(self) -> None:
        base = character_profile_form_defaults("阿宁", "导师")
        base["fields"]["personality_main"]["value"] = "可靠"
        incoming = character_profile_form_defaults("阿宁", "导师")
        incoming["fields"]["function_mentor"]["checked"] = True
        incoming["fields"]["personality_main"]["value"] = "腹黑"
        incoming["fields"]["ability_type"]["value"] = "剑术"

        merged = merge_character_profile_form(base, incoming, "阿宁", "导师")

        self.assertEqual(merged["schema"], "supporting")
        self.assertTrue(merged["fields"]["function_mentor"]["checked"])
        self.assertEqual(merged["fields"]["personality_main"]["value"], "可靠")
        self.assertEqual(merged["fields"]["ability_type"]["value"], "剑术")

    @unittest.skipIf(NovelQtMainWindow is None, "Qt app unavailable")
    def test_level1_groups_for_level2_respect_char_budget(self) -> None:
        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        level1_results = [
            {
                "level": 1,
                "chunk_id": f"chunk-{index + 1:04d}",
                "faithful_digest": "digest " + ("x" * 1800),
                "source_facts": [
                    {
                        "fact_id": f"f{index}-{fact}",
                        "chunk_id": f"chunk-{index + 1:04d}",
                        "claim": "claim " + ("y" * 600),
                        "evidence_quote": "quote " + ("z" * 600),
                    }
                    for fact in range(4)
                ],
            }
            for index in range(6)
        ]

        compacted = NovelQtMainWindow._compact_book_analysis_level1_for_level2(level1_results)
        groups = window._group_book_analysis_level1_results(compacted, group_size=3, max_group_chars=6500)

        self.assertGreater(len(groups), 1)
        self.assertTrue(all(len(json.dumps(group, ensure_ascii=False)) <= 7000 for group in groups))

    def test_book_analysis_uses_api_retries_not_local_fallback(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_analyze_book_in_batches"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("ai_request_retries", segment)
        self.assertIn("require_remote=True", segment)
        self.assertIn("RuntimeError", segment)
        self.assertNotIn("local_service", segment)
        self.assertNotIn("require_remote=False", segment)
        self.assertNotIn("本地结构兜底", segment)

    def test_smart_import_uses_agent_structure_not_local_precheck(self) -> None:
        root = Path(__file__).resolve().parent
        qt_source = (root / "novel_app" / "qt_app.py").read_text(encoding="utf-8")
        ai_source = (root / "novel_app" / "ai_service.py").read_text(encoding="utf-8")
        agent_source = (root / "novel_app" / "agents" / "chapter_structure.py").read_text(encoding="utf-8")
        self.assertIn("detect_chapter_structure(raw_text, require_remote=True)", qt_source)
        self.assertIn("use_local_headings=False", qt_source)
        self.assertNotIn("_guess_smart_import_type", qt_source)
        self.assertNotIn("_fallback_smart_import_type", qt_source)
        self.assertNotIn("本地结构预检", qt_source)
        self.assertIn("ChapterStructureAgent", ai_source)
        self.assertIn("line_number", agent_source)

    def test_book_analysis_uses_three_level_pyramid_pipeline(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_analyze_book_in_batches"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("analyze_book_level1", segment)
        self.assertIn("analyze_book_level2", segment)
        self.assertIn("analyze_book_level3_draft", segment)
        self.assertIn("analyze_book_level3_finalize", segment)
        self.assertIn("_build_book_analysis_source_context", segment)
        self.assertIn("source_requests", segment)
        self.assertIn("book_analysis_concurrency", segment)
        self.assertIn("max_chars=20000", segment)
        self.assertIn("three_level_pyramid_v2_source_review", segment)
        self.assertNotIn("ai_service.analyze_book(", segment)

    def test_book_analysis_text_chunks_are_pure_char_slices(self) -> None:
        if NovelQtMainWindow is None:
            self.skipTest("Qt app not importable")
        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        content = "甲" * 25050
        chunks = window._build_book_analysis_text_chunks(
            [{"id": 1, "title": "第一章", "outline": "大纲", "content": content}],
            max_chars=20000,
        )
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 20000 for chunk in chunks))
        self.assertIn(content, "".join(chunks))

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_source_context_returns_keyword_snippets(self) -> None:
        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        chapters = [
            {"id": 1, "title": "开端", "outline": "", "content": "少年离村。"},
            {"id": 2, "title": "星门", "outline": "", "content": "星门在雨夜开启，族人因此失踪。"},
        ]
        chunks = window._build_book_analysis_source_chunks(chapters, max_chars=20000)
        context = window._build_book_analysis_source_context(
            [{"request_id": "r1", "chapter_id": 2, "keywords": ["星门"]}],
            chunks,
        )

        self.assertTrue(context["snippets"])
        self.assertIn("星门", context["snippets"][0]["text"])
        self.assertEqual(context["snippets"][0]["request_id"], "r1")

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_source_context_respects_caps_without_empty_result(self) -> None:
        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        long_text = "星门" + ("甲" * 1000) + "族人" + ("乙" * 1000)
        chunks = window._build_book_analysis_source_chunks(
            [{"id": 1, "title": "长章", "outline": "", "content": long_text}],
            max_chars=20000,
        )
        context = window._build_book_analysis_source_context(
            [
                {"request_id": "r1", "keywords": ["星门"]},
                {"request_id": "r2", "keywords": ["族人"]},
            ],
            chunks,
            snippets_per_request=2,
            snippet_chars=120,
            max_total_chars=180,
        )

        self.assertTrue(context["snippets"])
        self.assertLessEqual(context["total_chars"], 180)

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_level3_source_requests_trigger_finalize(self) -> None:
        class FakeService:
            def __init__(self) -> None:
                self.finalize_context = None

            def clone(self):
                return self

            def analyze_book_level1(self, **kwargs):
                return {
                    "level": 1,
                    "chunk_id": kwargs.get("chunk_id"),
                    "chapter_ids": kwargs.get("chapter_ids"),
                    "source_facts": [
                        {
                            "fact_id": "f1",
                            "chapter_id": 1,
                            "chunk_id": kwargs.get("chunk_id"),
                            "claim": "星门开启",
                            "evidence_quote": "星门在雨夜开启",
                        }
                    ],
                }

            def analyze_book_level2(self, **kwargs):
                return {"level": 2, "consolidated_facts": kwargs.get("level1_results", [])}

            def analyze_book_level3_draft(self, **kwargs):
                return {
                    "source_requests": [
                        {"request_id": "r1", "chapter_id": 1, "keywords": ["星门"], "target_field": "main_genre"}
                    ],
                    "analysis_unresolved": [],
                }

            def analyze_book_level3_finalize(self, **kwargs):
                self.finalize_context = kwargs.get("source_context")
                return {
                    "book_outline_form": {
                        "fields": {
                            "main_genre": {"value": "奇幻", "evidence_refs": ["f1"], "source_quotes": ["星门在雨夜开启"]}
                        }
                    },
                    "analysis_unresolved": [],
                }

        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        window.ai_request_retries = 0
        window.book_analysis_concurrency = 1
        window.book_analysis_fast_extra_body = "{}"
        window.book_analysis_final_extra_body = "{}"
        service = FakeService()
        payload = window._analyze_book_in_batches(
            ai_service=service,
            book_title="测试书",
            book_outline="",
            chapters=[{"id": 1, "title": "第一章", "outline": "", "content": "星门在雨夜开启，族人因此失踪。"}],
            characters=[],
            world_entries=[],
            log=lambda _message: None,
            cancel_event=None,
        )

        self.assertIsNotNone(service.finalize_context)
        self.assertIn("星门", service.finalize_context["snippets"][0]["text"])
        self.assertEqual(payload["_meta"]["source_request_count"], 1)
        self.assertIn("main_genre", payload["book_outline_form"]["fields"])

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_level3_without_source_requests_skips_finalize(self) -> None:
        class FakeService:
            def clone(self):
                return self

            def analyze_book_level1(self, **kwargs):
                return {"level": 1, "chunk_id": kwargs.get("chunk_id"), "source_facts": []}

            def analyze_book_level2(self, **kwargs):
                return {"level": 2, "consolidated_facts": []}

            def analyze_book_level3_draft(self, **kwargs):
                return {
                    "book_outline_form": {
                        "fields": {
                            "main_genre": {"value": "悬疑", "source_quotes": ["密室门从内侧锁住"]}
                        }
                    }
                }

            def analyze_book_level3_finalize(self, **kwargs):
                raise AssertionError("finalize should not run without source_requests")

        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        window.ai_request_retries = 0
        window.book_analysis_concurrency = 1
        window.book_analysis_fast_extra_body = "{}"
        window.book_analysis_final_extra_body = "{}"
        payload = window._analyze_book_in_batches(
            ai_service=FakeService(),
            book_title="测试书",
            book_outline="",
            chapters=[{"id": 1, "title": "第一章", "outline": "", "content": "密室门从内侧锁住。"}],
            characters=[],
            world_entries=[],
            log=lambda _message: None,
            cancel_event=None,
        )

        self.assertEqual(payload["_meta"]["source_request_count"], 0)
        self.assertEqual(payload["book_outline_form"]["fields"]["main_genre"]["value"], "悬疑")

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_evidence_gate_removes_unsupported_fields(self) -> None:
        window = NovelQtMainWindow.__new__(NovelQtMainWindow)
        filtered = window._filter_untrusted_book_analysis_payload(
            {
                "_requires_evidence": True,
                "book_outline_form": {
                    "fields": {
                        "main_genre": {"value": "玄幻"},
                        "sub_genre_1": {"value": "悬疑", "evidence_refs": ["f1"]},
                    }
                },
            }
        )

        fields = filtered["book_outline_form"]["fields"]
        self.assertNotIn("main_genre", fields)
        self.assertEqual(fields["sub_genre_1"]["value"], "悬疑")
        self.assertGreater(filtered["_meta"]["evidence_gate_dropped"], 0)

    def test_book_analysis_result_writeback_overwrites_forms_and_events(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_apply_book_analysis_result"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("normalize_book_outline_form(outline_data", segment)
        self.assertIn("normalize_world_form(world_data)", segment)
        self.assertIn("_filter_untrusted_book_analysis_payload", segment)
        self.assertIn("_overlay_sparse_analysis_form", segment)
        self.assertIn("_analysis_character_items(payload)", segment)
        self.assertIn("_analysis_character_profile_form(item, role)", segment)
        self.assertIn("character_profile_markdown_to_form(profile, name, role)", segment)
        self.assertIn("normalize_character_profile_form(profile_data", segment)
        self.assertIn("delete_chapter_event", segment)
        self.assertNotIn("merge_character_analysis_payload", segment)

    @unittest.skipUnless(NovelQtMainWindow, "PyQt6 is not available")
    def test_book_analysis_character_payload_populates_profile_forms(self) -> None:
        with TemporaryDirectory() as tmp:
            database = Database(Path(tmp) / "novels.db")
            try:
                database.initialize()
                book_id = database.create_book("分析测试书")

                main_profile = character_profile_form_defaults("林一", "主角")
                main_profile["fields"]["identity_common"]["checked"] = True
                main_profile["fields"]["personality_main"]["value"] = "冷静、敏锐"
                main_markdown = character_profile_form_to_markdown(main_profile, "林一", "主角")

                support_profile = character_profile_form_defaults("阿宁", "导师")
                support_profile["fields"]["function_mentor"]["checked"] = True
                support_profile["fields"]["ability_type"]["value"] = "剑术"

                window = NovelQtMainWindow.__new__(NovelQtMainWindow)
                window.database = database
                window.state = SimpleNamespace(
                    selected_book_id=book_id,
                    selected_book_title="分析测试书",
                    editor_scope_kind="",
                    selected_chapter_id=None,
                )
                window.current_tree_key = None
                window.selected_character_id = None
                window._book_outline_volume_specs = lambda _book_id: []
                window._sync_truth_files = lambda _book_id: None
                window._index_book_design_for_rag = lambda _book_id: None
                window._load_library_tree = lambda _key: None
                window._refresh_drawer = lambda: None
                window._refresh_structured_markdown_views_after_analysis = lambda _book_id: None
                window._append_task_log = lambda _message: None
                window._switch_drawer_tab = lambda _tab: None
                window._update_word_count = lambda: None

                window._apply_book_analysis_result(
                    book_id,
                    {
                        "character_cards": [
                            {"name": "林一", "role": "主角", "profile_text": main_markdown},
                            {
                                "name": "阿宁",
                                "role": "导师",
                                "profile_data_json": json.dumps(support_profile, ensure_ascii=False),
                            },
                        ]
                    },
                )

                characters = {str(item["name"]): dict(item) for item in database.list_characters(book_id)}
                self.assertIn("林一", characters)
                self.assertIn("阿宁", characters)

                main_form = database.get_character_profile_form(int(characters["林一"]["id"]))
                self.assertTrue(main_form["fields"]["identity_common"]["checked"])
                self.assertEqual(main_form["fields"]["personality_main"]["value"], "冷静、敏锐")

                support_form = database.get_character_profile_form(int(characters["阿宁"]["id"]))
                self.assertTrue(support_form["fields"]["function_mentor"]["checked"])
                self.assertEqual(support_form["fields"]["ability_type"]["value"], "剑术")
            finally:
                database.close()

    def test_ai_settings_include_book_analysis_extra_body_controls(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        self.assertIn("DEFAULT_BOOK_ANALYSIS_FAST_EXTRA_BODY_JSON", source)
        self.assertIn("DEFAULT_BOOK_ANALYSIS_FINAL_EXTRA_BODY_JSON", source)
        self.assertIn("book_analysis_fast_extra_body", source)
        self.assertIn("book_analysis_final_extra_body", source)

    def test_book_analysis_world_payload_is_merged_into_form(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_merge_book_analysis_payload"
        ]
        self.assertEqual(len(methods), 1)
        segment = ast.get_source_segment(source, methods[0]) or ""
        self.assertIn("merge_world_analysis_payload", segment)
        self.assertIn("_analysis_world_form(payload)", segment)
        self.assertIn("_analysis_world_text", segment)
        self.assertNotIn('merge_named_list("world_entries"', segment)

        apply_methods = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "_apply_book_analysis_result"
        ]
        self.assertEqual(len(apply_methods), 1)
        apply_segment = ast.get_source_segment(source, apply_methods[0]) or ""
        self.assertIn("world_form = self._analysis_world_form(payload)", apply_segment)
        self.assertIn("world_markdown_to_form", apply_segment)

    def test_character_and_world_refresh_preserve_dirty_side_forms(self) -> None:
        source_path = Path(__file__).resolve().parent / "novel_app" / "qt_app.py"
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        methods = {
            node.name: ast.get_source_segment(source, node) or ""
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name in {"_load_world_form_for_book", "_smart_import_character", "_smart_import_world"}
        }

        self.assertIn("_world_form_dirty", methods["_load_world_form_for_book"])
        self.assertIn("_world_form_book_id", methods["_load_world_form_for_book"])
        self.assertIn("_confirm_character_edit_navigation", methods["_smart_import_character"])
        self.assertIn("self.selected_character_id = char_id", methods["_smart_import_character"])
        self.assertIn("_sync_truth_files", methods["_smart_import_character"])
        self.assertIn("self.world_form.to_data()", methods["_smart_import_world"])
        self.assertIn("_world_form_book_id", methods["_smart_import_world"])

    @unittest.skipUnless(FunctionWorker, "PyQt6 is not available")
    def test_function_worker_can_deliver_cancelled_payload(self) -> None:
        cancel_event = Event()
        done_payloads = []
        cancelled_messages = []

        def callback(event: Event) -> dict[str, bool]:
            event.set()
            return {"cancelled": True}

        worker = FunctionWorker(
            callback,
            pass_cancel=True,
            cancel_event=cancel_event,
            deliver_result_on_cancel=True,
        )
        worker.done.connect(done_payloads.append)
        worker.cancelled.connect(cancelled_messages.append)
        worker.run()

        self.assertEqual(done_payloads, [{"cancelled": True}])
        self.assertEqual(cancelled_messages, [])


if __name__ == "__main__":
    unittest.main()
