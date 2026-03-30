"""
Elite Ideas 提取器数据库字段对齐测试

运行方式：
  python3 test/test_elite_ideas_db_alignment.py
"""

import json
import os
import sys
import tempfile
import types
import unittest


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# 避免本地缺少 PyMuPDF(fitz) 时导入失败
if "fitz" not in sys.modules:
    sys.modules["fitz"] = types.ModuleType("fitz")

if "openai" not in sys.modules:
    openai_stub = types.ModuleType("openai")

    class _StubOpenAI:
        def __init__(self, *args, **kwargs):
            self.chat = types.SimpleNamespace(
                completions=types.SimpleNamespace(
                    create=lambda **kwargs: None
                )
            )

    openai_stub.OpenAI = _StubOpenAI
    sys.modules["openai"] = openai_stub


from skill import elite_ideas_extractor as extractor


class _FakeMessage:
    def __init__(self, content: str):
        self.content = content


class _FakeChoice:
    def __init__(self, content: str):
        self.message = _FakeMessage(content)


class _FakeResponse:
    def __init__(self, content: str):
        self.choices = [_FakeChoice(content)]


class _FakeCompletions:
    def __init__(self, content: str):
        self._content = content

    def create(self, **kwargs):
        return _FakeResponse(self._content)


class _FakeChat:
    def __init__(self, content: str):
        self.completions = _FakeCompletions(content)


class _FakeClient:
    def __init__(self, content: str):
        self.chat = _FakeChat(content)


class TestEliteIdeasDbAlignment(unittest.TestCase):
    def setUp(self):
        self._orig_client = extractor.client
        self._orig_extract_pdf_text = extractor.extract_pdf_text
        self._orig_extract_elite_ideas = extractor.extract_elite_ideas
        self._orig_build_db_aligned_payload = extractor.build_db_aligned_payload

    def tearDown(self):
        extractor.client = self._orig_client
        extractor.extract_pdf_text = self._orig_extract_pdf_text
        extractor.extract_elite_ideas = self._orig_extract_elite_ideas
        extractor.build_db_aligned_payload = self._orig_build_db_aligned_payload

    def test_build_db_aligned_payload_fields_and_truncation(self):
        long_text = "A" * 180
        fake_json = {
            "elite_idea_cards": [
                {
                    "origin_concept": long_text,
                    "meta_idea_name": long_text,
                    "meta_explanation": long_text,
                    "cases": [
                        {
                            "case_title": long_text,
                            "case_content": long_text,
                            "image_path": long_text,
                            "query_rewrite": "rewritten query"
                        }
                    ],
                    "external_resources": [
                        {
                            "title": long_text,
                            "url": "https://example.com/very/long/path",
                            "LLM_context": "context text",
                            "source": long_text
                        }
                    ]
                }
            ]
        }

        extractor.client = _FakeClient(json.dumps(fake_json, ensure_ascii=False))
        result = extractor.build_db_aligned_payload("dummy")

        self.assertEqual(set(result.keys()), {"elite_idea_cards", "elite_idea_cases", "external_resources"})
        self.assertEqual(len(result["elite_idea_cards"]), 1)
        self.assertEqual(len(result["elite_idea_cases"]), 1)
        self.assertEqual(len(result["external_resources"]), 1)

        card = result["elite_idea_cards"][0]
        self.assertEqual(set(card.keys()), {
            "daily_brief_id", "origin_concept", "meta_idea_name", "meta_explanation", "create_at", "card_index"
        })
        self.assertLessEqual(len(card["origin_concept"]), 100)
        self.assertLessEqual(len(card["meta_idea_name"]), 100)
        self.assertLessEqual(len(card["meta_explanation"]), 100)

        case = result["elite_idea_cases"][0]
        self.assertEqual(set(case.keys()), {
            "meta_id", "case_title", "case_content", "image_path", "query_rewrite", "card_index"
        })
        self.assertLessEqual(len(case["case_title"]), 100)
        self.assertLessEqual(len(case["case_content"]), 100)
        self.assertLessEqual(len(case["image_path"]), 100)

        resource = result["external_resources"][0]
        self.assertEqual(set(resource.keys()), {
            "card_id", "title", "url", "LLM_context", "source", "card_index"
        })
        self.assertLessEqual(len(resource["title"]), 100)
        self.assertLessEqual(len(resource["source"]), 100)

    def test_process_pdf_to_elite_ideas_output_contains_db_payload_and_files(self):
        extractor.extract_pdf_text = lambda pdf_path, max_pages=None: "mock pdf text"
        extractor.extract_elite_ideas = lambda text, max_tokens=4096, temperature=0.7: "mock elite ideas"

        expected_payload = {
            "elite_idea_cards": [
                {
                    "daily_brief_id": None,
                    "origin_concept": "概念",
                    "meta_idea_name": "元想法",
                    "meta_explanation": "解释",
                    "create_at": "2026-03-13 00:00:00",
                    "card_index": 0,
                }
            ],
            "elite_idea_cases": [],
            "external_resources": [],
        }
        extractor.build_db_aligned_payload = lambda content, max_tokens=2048: expected_payload

        with tempfile.TemporaryDirectory() as tmpdir:
            pdf_path = os.path.join(tmpdir, "dummy.pdf")
            with open(pdf_path, "wb") as f:
                f.write(b"%PDF-1.4\n%mock\n")

            result = extractor.process_pdf_to_elite_ideas(
                pdf_path=pdf_path,
                filename="dummy.pdf",
                save_to_file=True,
                output_dir=tmpdir,
            )

            self.assertTrue(result["success"])
            self.assertEqual(result["elite_ideas"], "mock elite ideas")
            self.assertEqual(result["db_aligned_payload"], expected_payload)
            self.assertIsNone(result["db_payload_error"])
            self.assertTrue(result["output_path"] and os.path.isfile(result["output_path"]))
            self.assertTrue(result["output_json_path"] and os.path.isfile(result["output_json_path"]))

            saved_json = json.loads(open(result["output_json_path"], "r", encoding="utf-8").read())
            self.assertEqual(saved_json, expected_payload)

    def test_process_pdf_to_elite_ideas_db_payload_failure_is_non_blocking(self):
        extractor.extract_pdf_text = lambda pdf_path, max_pages=None: "mock pdf text"
        extractor.extract_elite_ideas = lambda text, max_tokens=4096, temperature=0.7: "mock elite ideas"

        def _raise_error(content, max_tokens=2048):
            raise Exception("mock db payload fail")

        extractor.build_db_aligned_payload = _raise_error

        result = extractor.process_pdf_to_elite_ideas(
            pdf_path="dummy.pdf",
            filename="dummy.pdf",
            save_to_file=False,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["db_aligned_payload"], {
            "elite_idea_cards": [],
            "elite_idea_cases": [],
            "external_resources": [],
        })
        self.assertIsNotNone(result["db_payload_error"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
