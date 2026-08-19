import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-public-event-archive/scripts/archive_state.py"


class PublicEventArchiveTests(unittest.TestCase):
    def make_project(self, enabled=True):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "config").mkdir()
        config = {
            "version": 1,
            "enabled": enabled,
            "account": "b",
            "output_target": "draft",
            "state": {
                "path": "state/public-event-archive.sqlite3",
                "reservation_ttl_hours": 24,
            },
            "selection": {
                "min_source_count": 2,
                "require_authority_source": True,
                "require_official_media_report": True,
                "person_crime_requires_effective_judgment": True,
                "event_requires_official_conclusion": True,
                "categories": ["major_fraud", "public_safety"],
                "score_weights": {
                    "social_impact": 25,
                    "source_authority": 25,
                    "fact_completeness": 20,
                    "public_interest": 15,
                    "timeline_completeness": 10,
                    "portfolio_diversity": 5,
                },
            },
            "source_policy": {
                "authority_domains": ["court.gov.cn", "gov.cn"],
                "official_media_domains": ["news.cn", "cctv.com"],
            },
            "theme_allowlist": ["solemn-gray", "news-wire", "formal-brief"],
        }
        (root / "config/public-event-archive.json").write_text(
            json.dumps(config, ensure_ascii=False), encoding="utf-8"
        )
        return temp, root

    def run_cli(self, root, *args, expect=0):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args, "--project-root", str(root)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(expect, result.returncode, result.stderr)
        stream = result.stdout if expect == 0 else result.stderr
        return json.loads(stream)

    def reserve(self, root, key="person:示例:2020-01-01"):
        return self.run_cli(
            root,
            "reserve",
            "--key", key,
            "--subject", "示例",
            "--category", "major_fraud",
            "--source-url", "https://www.court.gov.cn/example",
            "--source-url", "https://www.news.cn/example",
        )

    def write_dossier(self, root, **overrides):
        dossier = {
            "schema_version": 1,
            "case_key": "person:示例:2020-01-01",
            "subject": "示例",
            "category": "major_fraud",
            "conclusion": {
                "type": "effective_judgment",
                "status": "effective",
                "authority": "示例人民法院",
                "date": "2020-01-01",
            },
            "claims": [
                {"id": "C1", "text": "生效裁判认定的事实", "source_ids": ["S1", "S2"]}
            ],
            "sources": [
                {
                    "id": "S1", "publisher": "示例人民法院",
                    "url": "https://www.court.gov.cn/example",
                    "published_at": "2020-01-01", "source_type": "authority",
                },
                {
                    "id": "S2", "publisher": "新华社",
                    "url": "https://www.news.cn/example",
                    "published_at": "2020-01-02", "source_type": "official_media",
                },
            ],
            "privacy_flags": [],
            "open_questions": [],
            "verified_at": "2026-01-01T00:00:00+00:00",
        }
        dossier.update(overrides)
        path = root / "dossier.json"
        path.write_text(json.dumps(dossier, ensure_ascii=False), encoding="utf-8")
        return path

    def test_disabled_switch_stops_before_reservation(self):
        temp, root = self.make_project(enabled=False)
        self.addCleanup(temp.cleanup)
        check = self.run_cli(root, "check")
        self.assertFalse(check["allowed"])
        reservation = self.reserve(root)
        self.assertFalse(reservation["reserved"])
        self.assertEqual("disabled_by_config", reservation["reason"])

    def test_reserve_complete_and_deduplicate(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        reservation = self.reserve(root)
        self.assertTrue(reservation["reserved"])
        duplicate = self.reserve(root)
        self.assertFalse(duplicate["reserved"])
        self.assertEqual("already_reserved", duplicate["reason"])
        completed = self.run_cli(
            root,
            "complete",
            "--key", reservation["case_key"],
            "--reservation-id", reservation["reservation_id"],
            "--run-id", "run-1",
            "--draft-id", "media-1",
        )
        self.assertTrue(completed["completed"])
        after = self.reserve(root)
        self.assertFalse(after["reserved"])
        self.assertEqual("already_completed", after["reason"])

    def test_release_allows_retry_and_reject_blocks_retry(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        first = self.reserve(root)
        self.run_cli(
            root,
            "release",
            "--key", first["case_key"],
            "--reservation-id", first["reservation_id"],
            "--reason", "发布前校验失败",
        )
        second = self.reserve(root)
        self.assertTrue(second["reserved"])
        self.run_cli(
            root,
            "reject",
            "--key", second["case_key"],
            "--reservation-id", second["reservation_id"],
            "--reason", "缺少生效裁判",
        )
        after = self.reserve(root)
        self.assertFalse(after["reserved"])
        self.assertEqual("previously_rejected", after["reason"])

    def test_requires_two_distinct_sources(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        error = self.run_cli(
            root,
            "reserve",
            "--key", "event:示例:2020-01-01",
            "--subject", "示例事件",
            "--category", "public_safety",
            "--source-url", "https://www.gov.cn/example",
            expect=2,
        )
        self.assertIn("至少需要 2 条", error["error"])

    def test_uncertain_blocks_reclaim_until_manual_resolution(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        reservation = self.reserve(root)
        self.run_cli(
            root,
            "uncertain",
            "--key", reservation["case_key"],
            "--reservation-id", reservation["reservation_id"],
            "--reason", "等待人工核对草稿箱",
        )
        duplicate = self.reserve(root)
        self.assertFalse(duplicate["reserved"])
        self.assertEqual("draft_outcome_uncertain", duplicate["reason"])
        completed = self.run_cli(
            root,
            "complete",
            "--key", reservation["case_key"],
            "--reservation-id", reservation["reservation_id"],
            "--run-id", "run-uncertain",
            "--draft-id", "media-uncertain",
        )
        self.assertTrue(completed["completed"])

    def test_requires_authority_and_official_media_source_types(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        error = self.run_cli(
            root,
            "reserve",
            "--key", "event:示例:2020-01-01",
            "--subject", "示例事件",
            "--category", "public_safety",
            "--source-url", "https://www.gov.cn/example-one",
            "--source-url", "https://www.court.gov.cn/example-two",
            expect=2,
        )
        self.assertIn("中国官方媒体", error["error"])

    def test_validates_effective_person_dossier(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        reservation = self.reserve(root)
        path = self.write_dossier(root)
        result = self.run_cli(
            root,
            "validate-dossier",
            "--file", str(path),
            "--reservation-id", reservation["reservation_id"],
        )
        self.assertTrue(result["valid"])
        self.assertEqual(2, result["source_count"])

    def test_rejects_person_dossier_without_effective_judgment(self):
        temp, root = self.make_project()
        self.addCleanup(temp.cleanup)
        reservation = self.reserve(root)
        path = self.write_dossier(
            root,
            conclusion={
                "type": "investigation",
                "status": "pending",
                "authority": "某机关",
                "date": "2020-01-01",
            },
        )
        error = self.run_cli(
            root,
            "validate-dossier",
            "--file", str(path),
            "--reservation-id", reservation["reservation_id"],
            expect=2,
        )
        self.assertIn("effective_judgment", error["error"])


if __name__ == "__main__":
    unittest.main()
