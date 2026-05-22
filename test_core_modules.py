"""核心模块测试"""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from novel_app.core import (
    get_event_bus, subscribe, unsubscribe, publish,
    get_state_manager, register_state_property, get_state, set_state,
    get_service_locator, register_service, register_service_factory, get_service
)
from novel_app.theme import get_design_tokens
from novel_app.ai_service import DEFAULT_BASE_URL, SimpleAIService
from novel_app.secure_storage import DPAPI_PREFIX, protect_secret, unprotect_secret


class TestEventBus(unittest.TestCase):
    """事件总线测试"""

    def test_event_subscription(self):
        """测试事件订阅和发布"""
        event_bus = get_event_bus()
        received_events = []

        def callback(event_data):
            received_events.append(event_data)

        # 订阅事件
        subscribe("test_event", callback)

        # 发布事件
        test_data = "test data"
        publish("test_event", test_data)

        # 验证事件被正确接收
        self.assertEqual(len(received_events), 1)
        self.assertEqual(received_events[0], test_data)

        # 取消订阅
        unsubscribe("test_event", callback)

        # 再次发布事件
        publish("test_event", "another test")

        # 验证事件不再被接收
        self.assertEqual(len(received_events), 1)


class TestStateManager(unittest.TestCase):
    """状态管理器测试"""

    def test_state_management(self):
        """测试状态管理"""
        state_manager = get_state_manager()

        # 注册状态属性
        register_state_property("test_state", "initial value")

        # 获取状态值
        self.assertEqual(get_state("test_state"), "initial value")

        # 设置状态值
        new_value = "new value"
        set_state("test_state", new_value)
        self.assertEqual(get_state("test_state"), new_value)

        # 测试状态验证
        def validator(value):
            return isinstance(value, int)

        register_state_property("test_int", 0, validator)
        self.assertEqual(get_state("test_int"), 0)

        # 尝试设置无效值
        set_state("test_int", "not an int")
        self.assertEqual(get_state("test_int"), 0)

        # 设置有效值
        set_state("test_int", 42)
        self.assertEqual(get_state("test_int"), 42)


class TestServiceLocator(unittest.TestCase):
    """服务定位器测试"""

    def test_service_registration(self):
        """测试服务注册和获取"""
        service_locator = get_service_locator()

        # 定义测试服务
        class TestService:
            def __init__(self):
                self.value = "test service"

        # 注册服务
        test_service = TestService()
        register_service("test_service", test_service)

        # 获取服务
        retrieved_service = get_service("test_service")
        self.assertEqual(retrieved_service.value, "test service")

        # 测试服务工厂
        def service_factory():
            return TestService()

        register_service_factory("factory_service", service_factory)
        factory_service = get_service("factory_service")
        self.assertEqual(factory_service.value, "test service")


@unittest.skip("Removed legacy Tk component registry")
class TestComponentRegistry(unittest.TestCase):
    """组件注册表测试"""

    def test_component_registration(self):
        """测试组件注册"""
        registry = get_component_registry()

        # 定义测试组件
        from novel_app.components.base_component import BaseComponent
        class TestComponent(BaseComponent):
            def __init__(self, parent, theme):
                super().__init__(parent, theme)

        # 注册组件
        register_component("test_component", TestComponent)

        # 验证组件已注册
        self.assertTrue(registry.has("test_component"))


class TestDesignTokens(unittest.TestCase):
    """设计令牌测试"""

    def test_design_tokens(self):
        """测试设计令牌"""
        # 获取亮色主题令牌
        light_tokens = get_design_tokens("light")
        self.assertIsNotNone(light_tokens)

        # 获取暗色主题令牌
        dark_tokens = get_design_tokens("dark")
        self.assertIsNotNone(dark_tokens)

        # 验证令牌包含必要的属性
        self.assertIsNotNone(light_tokens.colors)
        self.assertIsNotNone(light_tokens.fonts)
        self.assertIsNotNone(light_tokens.spacing)
        self.assertIsNotNone(light_tokens.borders)
        self.assertIsNotNone(light_tokens.shadows)


class TestAIServiceSafety(unittest.TestCase):
    """AI 服务安全配置测试"""

    def test_rejects_invalid_base_url(self):
        service = SimpleAIService()
        with self.assertRaises(ValueError):
            service.configure(api_key="k", base_url="file:///tmp/token", model="m")
        with self.assertRaises(ValueError):
            service.configure(api_key="k", base_url="https://api.example.com\nInjected: x", model="m")
        with self.assertRaises(ValueError):
            service.configure(api_key="k", base_url="http://api.example.com/v1", model="m")

    def test_normalizes_valid_base_url(self):
        service = SimpleAIService()
        service.configure(api_key="k", base_url="https://api.example.com/", model="m")
        self.assertEqual(service.base_url, "https://api.example.com")
        service.configure(api_key="k", base_url="http://localhost:11434/v1", model="m")
        self.assertEqual(service.base_url, "http://localhost:11434/v1")

    def test_env_fallback_keeps_service_usable(self):
        service = SimpleAIService(api_key=None, base_url=None, model=None)
        service.configure(api_key=None, base_url=None, model=None)
        self.assertEqual(service.base_url, DEFAULT_BASE_URL)

    def test_required_remote_calls_do_not_use_mock_without_api(self):
        service = SimpleAIService()
        with self.assertRaises(RuntimeError):
            service.detect_ai_probability("测试正文" * 100)
        with self.assertRaises(RuntimeError):
            list(service.stream_generate(mode="draft", book_title="书", chapter_title="章", outline="大纲", require_remote=True))
        with self.assertRaises(RuntimeError):
            service.analyze_document("正文" * 100, require_remote=True)
        with self.assertRaises(RuntimeError):
            service.analyze_book(book_title="书", book_outline="", chapters=[], require_remote=True)
        with self.assertRaises(RuntimeError):
            list(service.stream_chat([{"role": "user", "content": "hello"}], require_remote=True))
        with self.assertRaises(RuntimeError):
            service.multi_agent_review(
                book_title="书",
                chapter_title="章",
                outline="大纲",
                content="正文",
                truth_file="truth",
                require_remote=True,
            )
        with self.assertRaises(RuntimeError):
            service.multi_agent_generate_from_outline(
                book_title="book",
                chapter_title="chapter",
                outline="outline",
                current_content="",
                truth_file="truth",
                require_remote=True,
            )
        with self.assertRaises(RuntimeError):
            service.extract_character_relationships(
                book_title="book",
                characters=[{"name": "甲"}, {"name": "乙"}],
                chapters=[{"title": "章", "content": "甲和乙同行。"}],
                require_remote=True,
            )
        with self.assertRaises(RuntimeError):
            service.detect_chinese_typos("这是一段需要 AI 纠错的章节正文。", require_remote=True)

    def test_post_chat_completion_merges_extra_body_and_can_omit_temperature(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")
        captured: dict[str, object] = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return b'{"choices":[{"message":{"content":"ok"}}]}'

        def fake_urlopen(req, timeout=120):
            captured["payload"] = json.loads(req.data.decode("utf-8"))
            captured["timeout"] = timeout
            return FakeResponse()

        with patch("novel_app.ai_service.request.urlopen", fake_urlopen):
            service._post_chat_completion(
                [{"role": "user", "content": "hi"}],
                temperature=None,
                extra_body={"thinking": {"type": "enabled"}, "reasoning_effort": "high"},
            )

        payload = captured["payload"]
        self.assertIsInstance(payload, dict)
        self.assertNotIn("temperature", payload)
        self.assertEqual(payload["thinking"], {"type": "enabled"})
        self.assertEqual(payload["reasoning_effort"], "high")

    def test_three_level_book_analysis_methods_require_remote(self):
        service = SimpleAIService()
        with self.assertRaises(RuntimeError):
            service.analyze_book_level1(book_title="书", book_outline="", chunk_text="正文", chunk_index=1, total_chunks=1)
        with self.assertRaises(RuntimeError):
            service.analyze_book_level2(book_title="书", level1_results=[], group_index=1, total_groups=1)
        with self.assertRaises(RuntimeError):
            service.analyze_book_level3(
                book_title="书",
                book_outline="",
                level2_results=[],
                chapters=[],
            )

    def test_detect_ai_probability_parses_remote_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {"choices": [{"message": {"content": '{"probability": 77, "level": "high"}'}}]}

        service._post_chat_completion = fake_post_chat_completion
        self.assertEqual(service.detect_ai_probability("测试正文" * 100), (77, "high"))

    def test_remote_completion_without_choices_raises_clear_error(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {"choices": []}

        service._post_chat_completion = fake_post_chat_completion
        with self.assertRaisesRegex(RuntimeError, "AI 接口未返回 choices"):
            service.detect_ai_probability("测试正文" * 100)

    def test_detect_ai_probability_normalizes_inconsistent_result(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {"choices": [{"message": {"content": '{"probability": 0, "level": "high"}'}}]}

        service._post_chat_completion = fake_post_chat_completion
        self.assertEqual(service.detect_ai_probability("测试正文" * 100), (0, "none"))
        self.assertEqual(service.detect_ai_probability("太短"), (0, "none"))

    def test_json_object_payload_repairs_missing_commas(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")
        malformed = """
        ```json
        {
          "story_summary": "第一段"
          "logic_chain": [
            "原因一"
            "结果二"
          ],
          "chapter_updates": [
            {"chapter_id": 1, "outline": "开端"}
            {"chapter_id": 2, "outline": "推进"}
          ],
        }
        ```
        """

        payload = service._extract_json_object_payload(malformed)

        self.assertEqual(payload["story_summary"], "第一段")
        self.assertEqual(payload["logic_chain"], ["原因一", "结果二"])
        self.assertEqual(payload["chapter_updates"][1]["chapter_id"], 2)

    def test_detect_chinese_typos_uses_original_text_offsets(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '[{"wrong": "错字", "suggestion": "措辞", "confidence": 0.9}]'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        text = "\n  第一行错字结束"
        result = service.detect_chinese_typos(text, require_remote=True)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["start"], text.index("错字"))
        self.assertEqual(result[0]["end"], text.index("错字") + len("错字"))

    def test_detect_chinese_typos_required_remote_rejects_malformed_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {"choices": [{"message": {"content": "没有返回 JSON"}}]}

        service._post_chat_completion = fake_post_chat_completion
        with self.assertRaises(RuntimeError):
            service.detect_chinese_typos("这是一段需要 AI 纠错的章节正文。", require_remote=True)

    def test_stream_chat_parses_remote_chunks(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_stream_chat_completion(*args, **kwargs):
            yield {"choices": [{"delta": {"content": "hel"}}]}
            yield {"choices": [{"delta": {"content": "lo"}}]}
            yield {"choices": [{"delta": {}}]}

        service._stream_chat_completion = fake_stream_chat_completion
        self.assertEqual(
            "".join(service.stream_chat([{"role": "user", "content": "Say hello"}], require_remote=True)),
            "hello",
        )

    def test_stream_chat_ignores_empty_choice_chunks(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_stream_chat_completion(*args, **kwargs):
            yield {"choices": []}
            yield {"usage": {"total_tokens": 8}}
            yield {"choices": [{"delta": {"role": "assistant"}}]}
            yield {"choices": [{"delta": {"content": "好"}}]}

        service._stream_chat_completion = fake_stream_chat_completion
        self.assertEqual(
            "".join(service.stream_chat([{"role": "user", "content": "测试"}], require_remote=True)),
            "好",
        )

    def test_analyze_book_parses_remote_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"characters": [{"name": "甲", "role": "主角", "profile_text": "测试"}], "world_form": {"fields": {"科技水平": "蒸汽工业"}}, "world_entries": [{"category": "规则", "content": "死亡会留下可交易的记忆。"}], "chapter_updates": [{"chapter_id": 1, "outline": "新大纲", "ai_probability": 20, "ai_probability_level": "low", "events": ["开场"]}]}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.analyze_book(
            book_title="书",
            book_outline="大纲",
            chapters=[{"id": 1, "title": "第一章", "content": "正文"}],
            require_remote=True,
        )
        self.assertEqual(result["characters"][0]["name"], "甲")
        self.assertEqual(result["world_form"]["fields"]["科技水平"], "蒸汽工业")
        self.assertEqual(result["world_entries"][0]["content"], "死亡会留下可交易的记忆。")
        self.assertEqual(result["chapter_updates"][0]["ai_probability_level"], "low")

    def test_multi_agent_review_parses_remote_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": "ok", "overall_score": 90, "final_verdict": "approve", "findings": [{"agent": "plot", "severity": "high", "issue": "bad", "suggestion": "fix"}], "revised_content": "new content", "revised_outline": "new outline", "risk_notes": "none"}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.multi_agent_review(
            book_title="书",
            chapter_title="章",
            outline="大纲",
            content="old content",
            truth_file="truth",
            require_remote=True,
        )
        self.assertEqual(result["final_verdict"], "approve")
        self.assertEqual(result["revised_content"], "new content")
        self.assertEqual(result["findings"][0]["severity"], "high")

    def test_multi_agent_review_normalizes_template_comparison(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": "ok", "overall_score": 90, "final_verdict": "approve", "findings": [], "revised_content": "new content", "revised_outline": "new outline", "template_comparison": ["same rhythm", "less dialogue"], "risk_notes": ""}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.multi_agent_review(
            book_title="book",
            chapter_title="chapter",
            outline="outline",
            content="old content",
            truth_file="truth",
            template_content="template body",
            require_remote=True,
        )
        self.assertIn("same rhythm", result["template_comparison"])
        self.assertIn("less dialogue", result["template_comparison"])

    def test_multi_agent_review_rejects_empty_revised_content(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": "empty", "overall_score": 80, "final_verdict": "approve", "findings": [], "revised_content": "", "revised_outline": ""}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.multi_agent_review(
            book_title="book",
            chapter_title="chapter",
            outline="old outline",
            content="old content",
            truth_file="truth",
            require_remote=True,
        )
        self.assertEqual(result["final_verdict"], "reject")
        self.assertEqual(result["revised_content"], "old content")
        self.assertEqual(result["revised_outline"], "old outline")

    def test_multi_agent_review_rejects_abnormally_short_revision(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")
        original = "long paragraph " * 40

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": "short", "overall_score": 90, "final_verdict": "approve", "findings": [], "revised_content": "too short", "revised_outline": "new outline"}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.multi_agent_review(
            book_title="book",
            chapter_title="chapter",
            outline="old outline",
            content=original,
            truth_file="truth",
            require_remote=True,
        )
        self.assertEqual(result["final_verdict"], "reject")
        self.assertEqual(result["findings"][0]["agent"], "safety_gate")

    def test_multi_agent_generate_from_outline_parses_remote_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"summary": "generated", "overall_score": 88, "final_verdict": "approve", "findings": [{"agent": "writer", "severity": "low", "issue": "ok", "suggestion": "keep"}], "revised_content": "new chapter body", "revised_outline": "new outline", "risk_notes": "none"}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.multi_agent_generate_from_outline(
            book_title="book",
            chapter_title="chapter",
            outline="old outline",
            current_content="",
            truth_file="truth",
            require_remote=True,
        )
        self.assertEqual(result["final_verdict"], "approve")
        self.assertEqual(result["revised_content"], "new chapter body")
        self.assertEqual(result["revised_outline"], "new outline")

    def test_extract_character_relationships_parses_remote_json(self):
        service = SimpleAIService(api_key="sk-test", base_url="https://example.com/v1", model="model-test")

        def fake_post_chat_completion(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"relationships": [{"source_name": "甲", "target_name": "乙", "relationship_type": "同盟", "description": "共同作战"}, {"source_name": "甲", "target_name": "路人", "relationship_type": "关联"}]}'
                        }
                    }
                ]
            }

        service._post_chat_completion = fake_post_chat_completion
        result = service.extract_character_relationships(
            book_title="book",
            characters=[{"name": "甲"}, {"name": "乙"}],
            chapters=[{"title": "章", "content": "甲和乙共同作战。"}],
            require_remote=True,
        )
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_name"], "甲")
        self.assertEqual(result[0]["target_name"], "乙")
        self.assertEqual(result[0]["relationship_type"], "同盟")

    def test_extract_character_relationships_mock_uses_co_mentions(self):
        service = SimpleAIService()
        result = service.extract_character_relationships(
            book_title="book",
            characters=[{"name": "甲"}, {"name": "乙"}, {"name": "丙"}],
            chapters=[{"title": "章", "content": "甲和乙是盟友。\n\n丙独自离开。"}],
        )
        self.assertEqual(len(result), 1)
        self.assertEqual({result[0]["source_name"], result[0]["target_name"]}, {"甲", "乙"})
        self.assertEqual(result[0]["relationship_type"], "同盟")

    def test_analyze_book_mock_builds_book_outline(self):
        service = SimpleAIService()
        result = service.analyze_book(
            book_title="书",
            book_outline="",
            chapters=[{"id": 1, "title": "第一章", "content": "少年推开旧门。"}],
            require_remote=False,
        )
        self.assertIn("book_outline", result)
        self.assertIn("第一章", result["book_outline"])


class TestSecureStorage(unittest.TestCase):
    """本地密钥保护测试"""

    def test_secret_roundtrip(self):
        secret = "sk-test-local-secret"
        protected = protect_secret(secret)
        self.assertEqual(unprotect_secret(protected), secret)
        if os.name == "nt":
            self.assertTrue(protected.startswith(DPAPI_PREFIX))
            self.assertNotEqual(protected, secret)


class TestPackagingScripts(unittest.TestCase):
    """打包脚本关键逻辑测试"""

    def test_build_script_uses_base_python_and_source_pip(self):
        source = Path("packaging/build_first_exe_fast.ps1").read_text(encoding="utf-8-sig")
        self.assertIn("function Resolve-PythonRuntimeRoot", source)
        self.assertIn("sys.base_prefix or sys.prefix", source)
        self.assertIn("$RequirementsHash", source)
        self.assertIn("Test-RuntimeCacheMatches", source)
        self.assertIn("& $PythonExe -m pip install", source)
        self.assertNotIn("$PayloadPip install", source)

    def test_launcher_reuses_extracted_runtime_until_payload_changes(self):
        source = Path("packaging/Launcher.cs").read_text(encoding="utf-8")
        self.assertIn("EnsureInstallDir", source)
        self.assertIn("BuildPayloadStamp", source)
        self.assertIn("NeedsExtract", source)
        ensure_method = source.split("private static string EnsureInstallDir", 1)[1].split("private static string BuildPayloadStamp", 1)[0]
        self.assertNotIn("DeleteDir(dir)", ensure_method)


if __name__ == "__main__":
    unittest.main()
