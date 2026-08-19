import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".agents/skills/wechat-content-pipeline/scripts/pipeline_job.py"
SPEC = importlib.util.spec_from_file_location("pipeline_job", SCRIPT)
pipeline_job = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pipeline_job)


class PipelineJobTests(unittest.TestCase):
    def init_job(self, tmp, topic="AI进入真实工作流程", force_new=False, **overrides):
        root = Path(tmp)
        (root / "config").mkdir(exist_ok=True)
        (root / "references").mkdir(exist_ok=True)
        profile = {
            "audience": "职场读者",
            "input_mode": overrides.get("input_mode", "open"),
            "topic_discovery": {
                "enabled": overrides.get("topic_discovery_enabled", True),
                "max_age_hours": 48,
                "categories": ["人工智能", "就业变化"],
            },
            "theme_strategy": "random",
            "illustrations": {
                "enabled": overrides.get("illustrations_enabled", True),
                "skill": "baoyu-article-illustrator",
                "backend": overrides.get("illustration_backend", "image_generate"),
                "max_images": overrides.get("max_images", 3),
            },
            "cover": {
                "enabled": True,
                "backend": overrides.get("cover_backend", "image_generate"),
                "aspect": overrides.get("cover_aspect", "16:9"),
                "subject_focus": True,
            },
            "publishing": {"target": "draft"},
        }
        (root / "config/wechat-content-profiles.json").write_text(json.dumps({
            "version": 5, "profiles": {"a": profile},
        }, ensure_ascii=False), encoding="utf-8")
        (root / "references/theme-index.md").write_text(
            "# 主题索引\n\n## 已注册主题\n\n"
            "| 墨绿 | `references/theme-moyu-green.md` |\n\n"
            "## 新主题登记流程\n",
            encoding="utf-8",
        )
        argv = ["init", "--project-root", str(root), "--account", "a"]
        if topic is not None:
            argv.extend(("--topic", topic))
        if force_new:
            argv.append("--force-new")
        if overrides.get("lane"):
            argv.extend(("--lane", overrides["lane"]))
        if overrides.get("humanize") is True:
            argv.append("--humanize")
        if overrides.get("humanize") is False:
            argv.append("--no-humanize")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            pipeline_job.cmd_init(pipeline_job.build_parser().parse_args(argv))
        # stdout 是纯 JSON（和其他子命令一致），job_path 从 job_contract 里读。
        # 不要退回「取第一行」——那依赖 stdout 混入非 JSON 文本。
        contract = json.loads(output.getvalue())["job_contract"]
        return Path(contract["paths"]["job_path"])

    def stage(self, job_path, name, status, details=()):
        if name in ("humanize", "illustrations") and status == "completed":
            self.stage(job_path, name, "running")
        argv = ["stage", "--job", str(job_path), "--name", name, "--status", status]
        for detail in details:
            argv.extend(("--detail", detail))
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_stage(pipeline_job.build_parser().parse_args(argv))

    def complete_gate_stages(self, job_path, illustration_status="completed"):
        for name in ("write", "humanize", "format"):
            self.stage(job_path, name, "completed")
        self.stage(job_path, "illustrations", illustration_status)
        self.stage(job_path, "cover", "completed")

    def record_hotspot(self, job_path, published_at=None, category="人工智能", focus="机器人进入产线"):
        published_at = published_at or datetime.now(timezone.utc).isoformat()
        args = pipeline_job.build_parser().parse_args([
            "topic", "--job", str(job_path), "--value", "机器人进入汽车工厂",
            "--source", "auto-hotspot", "--category", category,
            "--published-at", published_at, "--event-focus", focus,
            "--hook", "产线先省的是搬运，不是安全签字",
            "--tension", "效率提升 vs 停线与安全责任",
            "--reader-stakes", "产线与维护人员要重新划分谁能停机、谁背锅",
        ])
        with contextlib.redirect_stdout(io.StringIO()):
            pipeline_job.cmd_topic(args)

    def test_init_creates_schema_five_run_id_and_simplified_contract(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.init_job(tmp)
            first_job = pipeline_job.load_job(first)
            second = self.init_job(tmp, topic="第二篇")
            second_job = pipeline_job.load_job(second)
        self.assertEqual(5, second_job["schema_version"])
        self.assertNotEqual(first_job["run_id"], second_job["run_id"])
        self.assertNotIn("fact-check", second_job["stages"])
        self.assertNotIn("validate", second_job["stages"])
        self.assertNotIn("sources", second_job["artifacts"])
        self.assertNotIn("preview", second_job["artifacts"])
        self.assertEqual("inline-visuals.json", second_job["artifacts"]["inline_visuals"])

    def test_init_prints_job_contract_with_absolute_paths_next_command_and_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "config").mkdir(exist_ok=True)
            (root / "references").mkdir(exist_ok=True)
            profile = {
                "audience": "职场读者",
                "input_mode": "open",
                "writer_instructions": "示例声口说明：第一人称强情感",
                "voice": {"tone": "strong-emotion-subjective", "allowed_emotions": ["烦", "发紧"]},
                "topic_discovery": {
                    "enabled": True, "max_age_hours": 48, "categories": ["人工智能"],
                },
                "theme_strategy": "random",
                "illustrations": {
                    "enabled": True, "skill": "baoyu-article-illustrator",
                    "backend": "image_generate", "max_images": 3,
                },
                "cover": {"enabled": True, "backend": "image_generate", "aspect": "16:9"},
                "publishing": {"target": "draft"},
            }
            (root / "config/wechat-content-profiles.json").write_text(json.dumps({
                "version": 5, "profiles": {"a": profile},
            }, ensure_ascii=False), encoding="utf-8")
            (root / "references/theme-index.md").write_text(
                "# 主题索引\n\n## 已注册主题\n\n"
                "| 墨绿 | `references/theme-moyu-green.md` |\n\n"
                "## 新主题登记流程\n",
                encoding="utf-8",
            )
            argv = [
                "init", "--project-root", str(root), "--account", "a",
                "--topic", "AI进入真实工作流程",
            ]
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_init(pipeline_job.build_parser().parse_args(argv))
            # stdout 必须是完整合法 JSON —— 这条断言本身就是对「stdout 不混
            # 非 JSON 文本」的回归保护。
            raw = output.getvalue()
            contract = json.loads(raw)["job_contract"]
            job_path = Path(contract["paths"]["job_path"])
        for key in ("work_dir", "job_path", "article_path", "digest_path", "imgs_dir", "cover_path"):
            self.assertTrue(os.path.isabs(contract["paths"][key]), key)
        self.assertEqual(str(job_path), contract["paths"]["job_path"])
        self.assertEqual("a", contract["account"])
        self.assertEqual("AI进入真实工作流程", contract["topic"])
        self.assertEqual(len(pipeline_job.STAGES), len(contract["stages"]))
        self.assertIn("next_command", contract)
        self.assertIn("pipeline_job.py", contract["next_command"])
        # init 只写下 topic 字符串，event_focus 仍为空，所以下一步必须是 topic 而不是 shape
        # （早期实现只看 job["topic"] 有没有值，导致整个 topic 步骤被跳过、event_focus 永远为空）。
        self.assertIn("topic", contract["next_command"])
        self.assertIn("--source provided", contract["next_command"])
        # brief 还没落盘时，next_command 要先提醒写 user-brief.md——这是链上没有命令的一步。
        self.assertIn("user-brief.md", contract["next_command"])
        self.assertFalse(contract["workspace_reset"]["rebuilt_existing_workspace"])
        self.assertEqual("职场读者", contract["account_profile"]["audience"])
        self.assertIn("tone", contract["account_profile"]["voice"])
        blob = raw.lower()
        for banned in ("secret", "appid", "app_id", "access_token", "apikey", "api_key", "password"):
            self.assertNotIn(banned, blob)

    def test_profiles_user_brief_only_disables_auto_discovery(self):
        config = json.loads((ROOT / "config/wechat-content-profiles.json").read_text(encoding="utf-8"))
        self.assertEqual(6, config["version"])
        for profile in config["profiles"].values():
            self.assertEqual("user_brief_only", profile.get("input_mode"))
            discovery = profile["topic_discovery"]
            self.assertIs(False, discovery.get("enabled"))
            self.assertEqual(48, discovery["max_age_hours"])
            self.assertNotIn("window_hours", discovery)
            self.assertNotIn("fallback_hours", discovery)
            self.assertEqual("adaptive", profile["cover"]["backend"])
            self.assertEqual("2.35:1", profile["cover"]["aspect"])

    def test_auto_hotspot_rejected_when_user_brief_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(
                tmp, topic=None, input_mode="user_brief_only", topic_discovery_enabled=False,
            )
            with self.assertRaisesRegex(pipeline_job.JobError, "关闭自动选题"):
                self.record_hotspot(job_path)

    def test_init_preserves_workspace_safety_and_force_new(self):
        with tempfile.TemporaryDirectory() as tmp:
            current = Path(tmp) / "work/a/current"
            current.mkdir(parents=True)
            marker = current / "article.md"
            marker.write_text("unfinished", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_job.JobError, "缺少 job.json"):
                self.init_job(tmp)
            self.assertTrue(marker.is_file())
            replacement = self.init_job(tmp, force_new=True)
            self.assertTrue(replacement.is_file())
            self.assertFalse(marker.exists())

    def test_init_refuses_running_or_uncertain_workspace_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.stage(job_path, "draft", "running", ("run_id=attempt", "outcome=pending"))
            with self.assertRaisesRegex(pipeline_job.JobError, "未解决"):
                self.init_job(tmp, topic="新选题")

    def test_init_rejects_symlink_workdir_escape(self):
        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as outside:
            (Path(tmp) / "work").mkdir()
            os.symlink(outside, Path(tmp) / "work/a")
            (Path(outside) / "current").mkdir()
            marker = Path(outside) / "current/keep.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaisesRegex(pipeline_job.JobError, "路径不安全"):
                self.init_job(tmp)
            self.assertTrue(marker.is_file())

    def test_init_rejects_invalid_profile_backends_and_image_count(self):
        cases = (
            ({"illustration_backend": "other"}, "Baoyu"),
            ({"cover_backend": "html"}, "封面 backend"),
            ({"cover_backend": "other"}, "封面 backend"),
            ({"max_images": 4}, "Baoyu"),
        )
        for kwargs, message in cases:
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                with self.assertRaisesRegex(pipeline_job.JobError, message):
                    self.init_job(tmp, **kwargs)

    def test_init_accepts_no_inline_images_and_offline_cover_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(
                tmp, illustrations_enabled=False, cover_backend="offline_render",
            )
            job = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual(
                job["image_policy"],
                {
                    "inline_enabled": False,
                    "inline_max_images": 3,
                    "cover_backend": "offline_render",
                },
            )

    def test_init_accepts_adaptive_cover_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(
                tmp, illustrations_enabled=False, cover_backend="adaptive",
                cover_aspect="2.35:1",
            )
            job = json.loads(job_path.read_text(encoding="utf-8"))
            self.assertEqual("adaptive", job["image_policy"]["cover_backend"])
            self.assertEqual(
                "inline-visuals.json", job["artifacts"]["inline_visuals"]
            )

    def test_auto_hotspot_accepts_category_timestamp_and_focus(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            self.record_hotspot(job_path)
            job = pipeline_job.load_job(job_path)
            history = json.loads((Path(tmp) / "work/a/topic-history.json").read_text(encoding="utf-8"))
        self.assertEqual("completed", job["stages"]["discover"]["status"])
        self.assertEqual("机器人进入产线", history["topics"][-1]["event_focus"])
        self.assertEqual(2, history["version"])
        self.assertNotIn("evidence_urls", history["topics"][-1])

    def test_auto_hotspot_rejects_old_future_and_wrong_category(self):
        values = (
            ((datetime.now(timezone.utc) - timedelta(hours=49)).isoformat(), "人工智能", "48 小时"),
            ((datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(), "人工智能", "48 小时"),
            (datetime.now(timezone.utc).isoformat(), "医疗", "账号类别"),
        )
        for published, category, message in values:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as tmp:
                job_path = self.init_job(tmp, topic=None)
                with self.assertRaisesRegex(pipeline_job.JobError, message):
                    self.record_hotspot(job_path, published, category)

    def test_auto_hotspot_requires_story_kernel(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            args = pipeline_job.build_parser().parse_args([
                "topic", "--job", str(job_path), "--value", "某公司发布新模型",
                "--source", "auto-hotspot", "--category", "人工智能",
                "--published-at", datetime.now(timezone.utc).isoformat(),
                "--event-focus", "某公司发布新模型",
            ])
            with self.assertRaisesRegex(pipeline_job.JobError, "hook"):
                pipeline_job.cmd_topic(args)

    def test_history_returns_last_seven_days_without_mechanical_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            history_path = Path(tmp) / "work/a/topic-history.json"
            history_path.write_text(json.dumps({
                "version": 2, "account": "a", "topics": [
                    {"topic": "旧", "event_focus": "旧事件", "selected_at": (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()},
                    {"topic": "近", "event_focus": "机器人进入产线", "selected_at": datetime.now(timezone.utc).isoformat()},
                ],
            }, ensure_ascii=False), encoding="utf-8")
            output = io.StringIO()
            args = pipeline_job.build_parser().parse_args(["history", "--job", str(job_path)])
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_history(args)
            payload = json.loads(output.getvalue())
            entries = payload["entries"]
            self.assertIn("next_command", payload)
            self.record_hotspot(job_path, focus="机器人走进汽车制造现场")
        self.assertEqual(["机器人进入产线"], [entry["event_focus"] for entry in entries])

    def test_history_rotation_and_shape_enforces_structure_pool(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            now = datetime.now(timezone.utc)
            history_path = Path(tmp) / "work/a/topic-history.json"
            history_path.write_text(json.dumps({
                "version": 2, "account": "a", "topics": [
                    {
                        "topic": f"t{i}",
                        "event_focus": f"e{i}",
                        "selected_at": (now - timedelta(hours=i)).isoformat(),
                        "structure_id": "felt_essay" if i < 2 else "conflict",
                        "opening_type": "emotion_sting" if i == 0 else "contrast",
                        "ending_type": "unresolved" if i == 0 else "duty_point",
                        "tension_type": "efficiency_vs_duty" if i < 2 else "demo_vs_deploy",
                    }
                    for i in range(3)
                ],
            }, ensure_ascii=False), encoding="utf-8")
            self.record_hotspot(job_path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pipeline_job.cmd_history(pipeline_job.build_parser().parse_args([
                    "history", "--job", str(job_path), "--rotation",
                ]))
            payload = json.loads(out.getvalue())
            self.assertIn("rotation", payload)
            self.assertIn("felt_essay", payload["rotation"]["blocked_structures"])
            # blocked opening from last 5
            self.assertIn("emotion_sting", payload["rotation"]["blocked_openings"])
            with self.assertRaisesRegex(pipeline_job.JobError, "structure_id=felt_essay"):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path),
                    "--structure-id", "felt_essay",
                    "--opening-type", "scene",
                    "--ending-type", "hook_return",
                ]))
            with self.assertRaisesRegex(pipeline_job.JobError, "opening_type=emotion_sting"):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path),
                    "--structure-id", "myth_bust",
                    "--opening-type", "emotion_sting",
                    "--ending-type", "hook_return",
                ]))
            ok = io.StringIO()
            with contextlib.redirect_stdout(ok):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path),
                    "--structure-id", "myth_bust",
                    "--opening-type", "scene",
                    "--ending-type", "hook_return",
                    "--felt-sense", "讽刺",
                    "--tension-type", "hype_vs_adoption",
                    "--heading-count", "3",
                    "--body-band", "mid",
                ]))
            shape = json.loads(ok.getvalue())
            job = pipeline_job.load_job(job_path)
            history = json.loads(history_path.read_text(encoding="utf-8"))
        self.assertEqual("myth_bust", shape["structure_id"])
        self.assertEqual("myth_bust", job["article_shape"]["structure_id"])
        self.assertEqual("myth_bust", history["topics"][-1]["structure_id"])

    def test_shape_auto_generates_valid_shape_and_respects_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            now = datetime.now(timezone.utc)
            history_path = Path(tmp) / "work/a/topic-history.json"
            # 近 5 篇把 5 种 ending 全部用满：手工选型必死锁，--auto 必须仍能给出合法 shape
            endings = ["duty_point", "unresolved", "actionable_question", "hook_return", "brief_approval"]
            openings = ["emotion_sting", "contrast", "myth", "scene", "judgment_first"]
            history_path.write_text(json.dumps({
                "version": 2, "account": "a", "topics": [
                    {
                        "topic": f"t{i}", "event_focus": f"e{i}",
                        "selected_at": (now - timedelta(hours=i + 1)).isoformat(),
                        "structure_id": "conflict" if i < 2 else "felt_essay",
                        "opening_type": openings[i],
                        "ending_type": endings[i],
                        "tension_type": "demo_vs_deploy",
                        "heading_count": 4, "body_band": "mid",
                    }
                    for i in range(5)
                ],
            }, ensure_ascii=False), encoding="utf-8")
            self.record_hotspot(job_path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path), "--auto",
                ]))
            shape = json.loads(out.getvalue())
            # 同 run_id 重跑结果确定（覆盖历史条目后再跑一次仍一致）
            out2 = io.StringIO()
            with contextlib.redirect_stdout(out2):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path), "--auto",
                ]))
            shape_again = json.loads(out2.getvalue())
            # 显式字段覆盖自动选择
            out3 = io.StringIO()
            with contextlib.redirect_stdout(out3):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path), "--auto",
                    "--structure-id", "tech_explain",
                ]))
            overridden = json.loads(out3.getvalue())
        self.assertIn(shape["structure_id"], pipeline_job.STRUCTURE_IDS)
        self.assertIn(shape["opening_type"], pipeline_job.OPENING_TYPES)
        self.assertIn(shape["ending_type"], pipeline_job.ENDING_TYPES)
        self.assertIn(shape["tension_type"], pipeline_job.TENSION_TYPES)
        self.assertIn(shape["body_band"], pipeline_job.BODY_BANDS)
        self.assertTrue(2 <= shape["heading_count"] <= 5)
        self.assertEqual(shape, shape_again)
        self.assertEqual("tech_explain", overridden["structure_id"])

    def test_shape_manual_missing_required_fields_gives_actionable_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic=None)
            self.record_hotspot(job_path)
            with self.assertRaisesRegex(pipeline_job.JobError, "structure_id"):
                pipeline_job.cmd_shape(pipeline_job.build_parser().parse_args([
                    "shape", "--job", str(job_path),
                ]))

    def test_stage_requires_running_before_humanize_or_illustrations_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            for name in ("humanize", "illustrations"):
                args = pipeline_job.build_parser().parse_args([
                    "stage", "--job", str(job_path), "--name", name, "--status", "completed",
                ])
                with self.subTest(name=name), self.assertRaisesRegex(pipeline_job.JobError, "先标记 running"):
                    pipeline_job.cmd_stage(args)

    def test_stage_records_duration_and_theme_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            self.stage(job_path, "write", "running")
            running = pipeline_job.load_job(job_path)["stages"]["write"]
            self.stage(job_path, "write", "completed")
            completed = pipeline_job.load_job(job_path)["stages"]["write"]
            args = pipeline_job.build_parser().parse_args(["choose-theme", "--job", str(job_path)])
            first, second = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(first):
                pipeline_job.cmd_choose_theme(args)
            with contextlib.redirect_stdout(second):
                pipeline_job.cmd_choose_theme(args)
        self.assertEqual(running["started_at"], completed["started_at"])
        self.assertGreaterEqual(completed["duration_ms"], 0)
        # 主题的单一真相源是 render_article.py 的 THEMES，不再扫 references/theme-*.md 文件名。
        self.assertIn(first.getvalue().strip(), pipeline_job.registered_themes())
        # 由 run_id 派生：重复调用必然同一套（恢复时不换皮），跨 run_id 才轮换。
        self.assertEqual(first.getvalue(), second.getvalue())

    def test_choose_theme_is_derived_from_run_id_not_theme_index(self):
        themes = pipeline_job.registered_themes()
        self.assertEqual(sorted(themes), sorted(set(themes)))
        self.assertGreaterEqual(len(themes), 2)
        picks = set()
        for _ in range(24):
            # 每轮独立工作区：init 每次生成新的随机 run_id，主题据此派生。
            with tempfile.TemporaryDirectory() as tmp:
                job_path = self.init_job(tmp)
                args = pipeline_job.build_parser().parse_args(
                    ["choose-theme", "--job", str(job_path)]
                )
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    pipeline_job.cmd_choose_theme(args)
                picks.add(out.getvalue().strip())
        self.assertTrue(picks <= set(themes), picks)
        # 24 个不同 run_id 不该全落在同一套主题上，否则「跨文章轮换」就失效了。
        self.assertGreater(len(picks), 1, picks)

    def test_choose_theme_limits_formal_report_to_sober_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, topic="某案公开事实复盘")
            (job_path.parent / "source-dossier.json").write_text("{}", encoding="utf-8")
            args = pipeline_job.build_parser().parse_args(
                ["choose-theme", "--job", str(job_path)]
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                pipeline_job.cmd_choose_theme(args)
            self.assertIn(
                output.getvalue().strip(),
                {"solemn-gray", "news-wire", "formal-brief"},
            )

    def test_gate_accepts_zero_images_and_rejects_pending_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            self.complete_gate_stages(job_path, "skipped")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with contextlib.redirect_stdout(io.StringIO()):
                pipeline_job.cmd_gate(gate)

        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section><p>正文</p></section>", encoding="utf-8")
            for name in ("write", "humanize", "format"):
                self.stage(job_path, name, "completed")
            self.stage(job_path, "cover", "completed")
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with self.assertRaisesRegex(pipeline_job.JobError, "illustrations"):
                pipeline_job.cmd_gate(gate)

    def test_gate_keeps_placeholder_and_cover_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            (job_path.parent / "article.html").write_text("<section>{{作者名}}</section>", encoding="utf-8")
            self.complete_gate_stages(job_path)
            gate = pipeline_job.build_parser().parse_args(["gate", "--job", str(job_path)])
            with self.assertRaisesRegex(pipeline_job.JobError, "占位"):
                pipeline_job.cmd_gate(gate)
            (job_path.parent / "article.html").write_text("<section>正文</section>", encoding="utf-8")
            self.stage(job_path, "cover", "skipped", ("default_thumb_media_id=false",))
            with self.assertRaisesRegex(pipeline_job.JobError, "封面"):
                pipeline_job.cmd_gate(gate)

    def test_old_schema_migrates_to_stable_legacy_run_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp)
            raw = json.loads(job_path.read_text(encoding="utf-8"))
            raw["schema_version"] = 4
            raw.pop("run_id")
            raw["stages"]["fact-check"] = pipeline_job.stage_record("completed")
            raw["artifacts"]["sources"] = "sources.md"
            job_path.write_text(json.dumps(raw), encoding="utf-8")
            first = pipeline_job.load_job(job_path)
            second = pipeline_job.load_job(job_path)
        self.assertEqual(5, first["schema_version"])
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertNotIn("fact-check", first["stages"])
        self.assertNotIn("sources", first["artifacts"])

    def test_manuscript_lane_defaults_humanize_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_path = self.init_job(tmp, lane="manuscript")
            job = pipeline_job.load_job(job_path)
        self.assertEqual("manuscript", job["lane"])
        self.assertFalse(job["switches"]["humanize"])

    def test_brief_lane_rejects_disabled_humanize(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(pipeline_job.JobError, "去 AI 味不能关"):
                self.init_job(tmp, lane="brief", humanize=False)


if __name__ == "__main__":
    unittest.main()
