import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DISCOVERED_ROOT = ROOT / ".agents" / "skills"
OPTIONAL_ROOT = ROOT / "optional-skills"

CORE_SKILLS = {
    "humanizer-zh",
    "wechat-content-pipeline",
    "wechat-public-event-archive",
    "wechat-tech-insight-writer",
    "wechat-viral-writer",
    "xiaohu-gen",
}
OPTIONAL_SKILLS = {
    "baoyu-cover-image",
    "wechat-html-cover",
    "wechat-inline-visuals",
}


def skill_names(root):
    return {
        path.name
        for path in root.iterdir()
        if path.is_dir() and (path / "SKILL.md").is_file()
    }


class SkillLayoutTests(unittest.TestCase):
    def test_default_catalog_contains_only_core_pipeline_skills(self):
        self.assertEqual(CORE_SKILLS, skill_names(DISCOVERED_ROOT))

    def test_standalone_extensions_stay_outside_default_catalog(self):
        self.assertEqual(OPTIONAL_SKILLS, skill_names(OPTIONAL_ROOT))
        for name in OPTIONAL_SKILLS:
            self.assertFalse((DISCOVERED_ROOT / name).exists())

    def test_superseded_archive_is_not_in_active_branch(self):
        self.assertFalse((ROOT / "archive").exists())

    def test_core_entrypoints_remain_compact(self):
        limits = {
            "wechat-content-pipeline": 160,
            "humanizer-zh": 100,
        }
        for name, limit in limits.items():
            lines = (DISCOVERED_ROOT / name / "SKILL.md").read_text(
                encoding="utf-8"
            ).splitlines()
            self.assertLessEqual(len(lines), limit, name)


if __name__ == "__main__":
    unittest.main()
