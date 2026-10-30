#!/usr/bin/env python3
"""
Unit tests for THelp reporting renderer.
Covers validation, escaping, URL sanitization, atomic writes, CSP, hash navigation, and edge cases.
"""

import json
import tempfile
import unittest
from pathlib import Path

from reporting import render_report, write_report


class TestReporting(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "date": "2026-10-29",
            "period_label": "28 октября 18:00 – 29 октября 09:00",
            "generated_at": "2026-10-29 09:15:00",
            "title": "Утренний выпуск: обновление инфраструктуры",
            "subtitle": "Сводка ключевых инцидентов и запросов за прошедшую ночь",
            "stats": [
                {"label": "Новых задач", "value": "12"},
                {"label": "Критических", "value": "1"},
                {"label": "Активных чатов", "value": "8"},
            ],
            "highlights": [
                {
                    "title": "Перезапуск базы данных в кластере alpha",
                    "summary": "Плановый регламент завершён без деградации времени отклика.",
                    "category": "Инфраструктура",
                    "urgency": "medium",
                    "when": "04:30",
                    "where": "Чат #devops-ops",
                    "evidence": ["src_1"],
                },
                {
                    "title": "Запрос доступа к API партнёра",
                    "summary": "Ожидается подтверждение ключа.",
                    "category": "Интеграции",
                    "urgency": "low",
                    "when": "08:10",
                    "where": "Чат #partners",
                    "evidence": ["src_2"],
                },
            ],
            "actions": [
                {
                    "text": "Проверить лог репликации alpha",
                    "when": "до 11:00",
                    "where": "Grafana / K8s",
                    "priority": "high",
                    "state": "Назначено",
                    "evidence": ["src_1"],
                }
            ],
            "sections": [
                {
                    "title": "Дежурство и алерты",
                    "body": "Ночь прошла штатно.\n\nЗафиксировано два предупреждения дискового пространства.",
                }
            ],
            "chats": [
                {
                    "title": "Дежурная группа",
                    "count": 45,
                    "summary": "Обсуждение утреннего деплоя и расписания дежурств.",
                }
            ],
            "sources": [
                {
                    "key": "src_1",
                    "chat_id": 1001234567,
                    "message_id": 8901,
                    "title": "Сообщение дежурного инженера",
                    "time": "04:32",
                    "quote": "Кластер alpha перезапущен, сессии восстановлены.",
                    "url": "https://t.me/c/1001234567/8901",
                },
                {
                    "key": "src_2",
                    "chat_id": 1009876543,
                    "message_id": 4321,
                    "title": "Запрос в партнёрском канале",
                    "time": "08:10",
                    "quote": "Пришлите новый IP для белого списка.",
                    "url": "https://t.me/c/1009876543/4321",
                },
            ],
            "coverage": {
                "complete": True,
                "limitation": "Все 8 подключённых чатов обработаны без пропусков.",
            },
        }

    def test_valid_render_contains_expected_structure(self):
        output = render_report(self.valid_data)
        self.assertIn("<!DOCTYPE html>", output)
        self.assertIn('lang="ru"', output)
        self.assertIn("29 октября 2026 г.", output)
        self.assertIn("Утренний выпуск: обновление инфраструктуры", output)
        self.assertIn("Перезапуск базы данных в кластере alpha", output)
        self.assertIn("Проверить лог репликации alpha", output)
        self.assertIn("https://t.me/c/1001234567/8901", output)
        self.assertIn("Покрытие источников: Полное", output)
        # Ensure semantic regions and accessibility features
        self.assertIn('class="skip-link"', output)
        self.assertIn('id="main-content"', output)
        self.assertIn('name="viewport"', output)

    def test_csp_meta_present(self):
        output = render_report(self.valid_data)
        self.assertIn('http-equiv="Content-Security-Policy"', output)
        self.assertIn("default-src 'none'", output)
        self.assertIn("form-action 'none'", output)
        self.assertIn("object-src 'none'", output)

    def test_source_chat_and_message_id_rendered(self):
        output = render_report(self.valid_data)
        self.assertIn("Чат ID: <code>1001234567</code>", output)
        self.assertIn("Сообщение ID: <code>8901</code>", output)
        self.assertIn("Чат ID: <code>1009876543</code>", output)
        self.assertIn("Сообщение ID: <code>4321</code>", output)

    def test_placeholder_injection_literal(self):
        data = dict(self.valid_data)
        data["title"] = "Отчёт с плейсхолдером __SOURCES_BLOCK__ внутри"
        data["subtitle"] = "Подзаголовок с __TITLE__ и __ACTIONS_BLOCK__"
        output = render_report(data)
        self.assertIn("Отчёт с плейсхолдером __SOURCES_BLOCK__ внутри", output)
        self.assertIn("Подзаголовок с __TITLE__ и __ACTIONS_BLOCK__", output)

    def test_hash_navigation_script(self):
        output = render_report(self.valid_data)
        self.assertIn("revealDetailedAndTarget", output)
        self.assertIn("hashchange", output)
        self.assertIn("scrollIntoView", output)

    def test_script_tag_escaping_in_user_strings(self):
        attack_payload = '<script>alert("XSS")</script>'
        data = dict(self.valid_data)
        data["title"] = f"Report {attack_payload}"
        data["subtitle"] = f"Sub {attack_payload}"
        data["highlights"][0]["title"] = f"H1 {attack_payload}"
        data["highlights"][0]["summary"] = f"Summary {attack_payload}"
        data["actions"][0]["text"] = f"Action {attack_payload}"
        data["sections"][0]["body"] = f"Body paragraph 1 {attack_payload}\n\nBody paragraph 2"

        output = render_report(data)
        self.assertNotIn("<script>alert", output)
        self.assertIn("&lt;script&gt;alert(&quot;XSS&quot;)&lt;/script&gt;", output)

    def test_attribute_escaping(self):
        attribute_injection = '"><script>alert(1)</script><div class="'
        data = dict(self.valid_data)
        data["period_label"] = attribute_injection
        output = render_report(data)
        self.assertNotIn("<script>alert(1)</script>", output)
        self.assertIn("&quot;&gt;&lt;script&gt;alert(1)&lt;/script&gt;", output)

    def test_url_scheme_injection_rejected(self):
        malicious_urls = [
            'javascript:alert("XSS")',
            "data:text/html,<script>alert(1)</script>",
            "http://t.me/c/100/200",  # must be https
            "https://t.me/other/100/200",
            "https://evil.com/t.me/c/100/200",
            "https://t.me/c/abc/def",
        ]
        for bad_url in malicious_urls:
            data = dict(self.valid_data)
            data["sources"] = [
                {
                    "key": "src_1",
                    "chat_id": 1,
                    "message_id": 1,
                    "title": "Title",
                    "time": "10:00",
                    "quote": "Quote",
                    "url": bad_url,
                }
            ]
            data["highlights"] = [
                {
                    "title": "H",
                    "summary": "S",
                    "category": "C",
                    "urgency": "low",
                    "when": "now",
                    "where": "here",
                    "evidence": ["src_1"],
                }
            ]
            data["actions"] = []
            output = render_report(data)
            # URL must not be rendered as an active anchor href
            self.assertNotIn(f'href="{bad_url}"', output)

    def test_unknown_evidence_reference_rejected(self):
        data = dict(self.valid_data)
        data["highlights"][0]["evidence"] = ["non_existent_key"]
        with self.assertRaises(ValueError) as ctx:
            render_report(data)
        self.assertIn("unknown source key", str(ctx.exception))

        data = dict(self.valid_data)
        data["actions"][0]["evidence"] = ["ghost_key"]
        with self.assertRaises(ValueError) as ctx:
            render_report(data)
        self.assertIn("unknown source key", str(ctx.exception))

    def test_duplicate_source_keys_rejected(self):
        data = dict(self.valid_data)
        data["sources"] = [
            {
                "key": "dup_key",
                "chat_id": 1,
                "message_id": 1,
                "title": "Source 1",
                "time": "10:00",
                "quote": "Q1",
                "url": None,
            },
            {
                "key": "dup_key",
                "chat_id": 2,
                "message_id": 2,
                "title": "Source 2",
                "time": "10:05",
                "quote": "Q2",
                "url": None,
            },
        ]
        with self.assertRaises(ValueError) as ctx:
            render_report(data)
        self.assertIn("Duplicate source key", str(ctx.exception))

    def test_negative_chat_count_rejected(self):
        data = dict(self.valid_data)
        data["chats"] = [{"title": "Chat", "count": -5, "summary": "Negative"}]
        with self.assertRaises(ValueError) as ctx:
            render_report(data)
        self.assertIn("non-negative integer", str(ctx.exception))

    def test_invalid_date_format_rejected(self):
        data = dict(self.valid_data)
        data["date"] = "29-10-2026"
        with self.assertRaises(ValueError):
            render_report(data)

        data["date"] = "not-a-date"
        with self.assertRaises(ValueError):
            render_report(data)

    def test_missing_title_rejected(self):
        data = dict(self.valid_data)
        data["title"] = "   "
        with self.assertRaises(ValueError):
            render_report(data)

    def test_empty_arrays_and_optional_fields(self):
        minimal_data = {
            "date": "2026-10-29",
            "period_label": "",
            "generated_at": "",
            "title": "Минимальный отчёт",
            "subtitle": "",
            "stats": [],
            "highlights": [],
            "actions": [],
            "sections": [],
            "chats": [],
            "sources": [],
            "coverage": {"complete": False, "limitation": "Нет данных"},
        }
        output = render_report(minimal_data)
        self.assertIn("Минимальный отчёт", output)
        self.assertIn("Покрытие источников: Ограниченное", output)
        self.assertIn("Нет данных", output)

    def test_long_content_and_unbroken_strings(self):
        data = dict(self.valid_data)
        long_word = "A" * 120
        data["title"] = f"Заголовок_{long_word}"
        long_paragraph = "Это очень длинный абзац текста. " * 100
        data["sections"] = [{"title": f"Раздел_{long_word}", "body": f"{long_paragraph}\n\n{long_paragraph}"}]
        output = render_report(data)
        self.assertIn(long_word, output)
        self.assertIn("overflow-wrap: anywhere", output)

    def test_atomic_file_creation(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            dest_file = Path(tmp_dir) / "subfolder" / "daily_report.html"
            result_path = write_report(self.valid_data, dest_file)
            self.assertEqual(result_path, dest_file.resolve())
            self.assertTrue(dest_file.is_file())

            content = dest_file.read_text(encoding="utf-8")
            self.assertIn("Утренний выпуск: обновление инфраструктуры", content)

            # Check atomic replace of existing file
            data2 = dict(self.valid_data)
            data2["title"] = "Вторая ревизия отчёта"
            write_report(data2, dest_file)
            content2 = dest_file.read_text(encoding="utf-8")
            self.assertIn("Вторая ревизия отчёта", content2)
            self.assertNotIn("Утренний выпуск: обновление инфраструктуры", content2)


if __name__ == "__main__":
    unittest.main()
