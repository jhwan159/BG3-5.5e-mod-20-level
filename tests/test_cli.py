import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

from bg3tool.cli import (ToolError, build, inspect_lsx, load_project, main,
                         metadata, order_modules, validate)


ROOT = Path(__file__).resolve().parents[1]


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ("modproject.json",):
            shutil.copyfile(ROOT / name, self.root / name)
        shutil.copytree(ROOT / "modules", self.root / "modules")
        shutil.copytree(ROOT / "data", self.root / "data")
        self.project = load_project(self.root)
        self.modules = order_modules(self.project, self.project["profiles"]["prototype"])

    def source(self, name, relative, content):
        path = self.root / "modules" / name / "source" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def call(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main(["--project", str(self.root), *args])
        return code, out.getvalue(), err.getvalue()

    def test_dependency_closure(self):
        names = [m["name"] for m in self.modules]
        self.assertEqual(len(names), 5)
        self.assertLess(names.index("RulesCore"), names.index("Classes2024"))
        self.assertLess(names.index("Level20"), names.index("Spells2024"))
        self.assertNotIn("CampaignPatches", names)

    def test_cycle_and_missing_dependency_rejected(self):
        self.project["modules"][0]["dependencies"] = ["Level20"]
        with self.assertRaisesRegex(ToolError, "순환"):
            order_modules(self.project, ["RulesCore"])
        self.project["modules"][0]["dependencies"] = ["Missing"]
        with self.assertRaisesRegex(ToolError, "알 수 없는"):
            order_modules(self.project, ["RulesCore"])

    def test_duplicate_module_uuid_rejected(self):
        self.project["modules"][1]["uuid"] = self.project["modules"][0]["uuid"]
        (self.root / "modproject.json").write_text(json.dumps(self.project))
        with self.assertRaisesRegex(ToolError, "중복"):
            load_project(self.root)

    def test_metadata_dependencies_and_xml_escaping(self):
        self.project["author"] = 'A & B <team> "Q"'
        module = next(m for m in self.modules if m["name"] == "Spells2024")
        xml = ET.fromstring(metadata(self.project, module))
        self.assertEqual(xml.find(".//attribute[@id='Author']").get("value"), self.project["author"])
        deps = xml.findall(".//node[@id='ModuleShortDesc']/attribute[@id='UUID']")
        self.assertEqual(len(deps), 2)

    def test_build_reproducible_and_does_not_overwrite(self):
        relative = "Public/BG3_2024_RulesCore/Stats/Generated/Data/sample.txt"
        self.source("RulesCore", relative, "// development test\n")
        first = build(self.root, self.project, self.modules)
        second = build(self.root, self.project, self.modules)
        self.assertNotEqual(first, second)
        self.assertEqual((first / "build-report.json").read_bytes(), (second / "build-report.json").read_bytes())
        self.assertEqual((first / "RulesCore" / relative).read_text(), "// development test\n")
        self.assertFalse(list(first.rglob(".gitkeep")))
        self.assertEqual(len(list(first.rglob("meta.lsx"))), 5)

    def test_malformed_xml_fails_before_staging(self):
        self.source("RulesCore", "Public/broken.lsx", "<save>")
        code, _, err = self.call("build")
        self.assertEqual(code, 1)
        self.assertIn("오류", err)
        self.assertFalse((self.root / "build").exists())

    def test_case_insensitive_path_collision_rejected(self):
        self.source("RulesCore", "Public/same.txt", "a")
        self.source("Classes2024", "Public/Same.txt", "b")
        with self.assertRaisesRegex(ToolError, "충돌"):
            validate(self.root, self.project, self.modules)

    def test_source_meta_cannot_override_generated_metadata(self):
        self.source("RulesCore", "Mods/BG3_2024_RulesCore/meta.lsx", "<save/>")
        with self.assertRaisesRegex(ToolError, "meta.lsx"):
            validate(self.root, self.project, self.modules)

    def test_inspect_retains_child_and_parent_attributes(self):
        path = self.root / "sample.lsx"
        path.write_text('<save><node id="parent"><attribute id="Name" type="LSString" value="Fighter"/><children><node id="child"><attribute id="Level" type="int32" value="20"/></node></children></node></save>')
        result = inspect_lsx(path)
        self.assertEqual([n["node"] for n in result["nodes"]], ["child", "parent"])
        self.assertEqual(result["nodes"][0]["attributes"][0]["value"], "20")
        self.assertEqual(len(result["sha256"]), 64)

    def test_pack_dry_run_never_invokes_tool(self):
        with patch("bg3tool.cli.subprocess.run") as run:
            code, out, _ = self.call("pack", "--divine", "missing divine")
        self.assertEqual(code, 0)
        run.assert_not_called()
        self.assertIn('"create-package"', out)
        self.assertFalse((self.root / "dist").exists())

    def test_missing_pack_tool_fails_without_build(self):
        with patch("bg3tool.cli.shutil.which", return_value=None):
            code, _, err = self.call("pack", "--execute")
        self.assertEqual(code, 1)
        self.assertIn("Divine", err)
        self.assertFalse((self.root / "build").exists())

    def test_pack_requires_real_output_and_propagates_failure(self):
        with patch("bg3tool.cli.shutil.which", return_value="/tool"), patch("bg3tool.cli.subprocess.run"):
            code, _, err = self.call("pack", "--execute")
        self.assertEqual(code, 1)
        self.assertIn("생성하지 않았습니다", err)
        with patch("bg3tool.cli.shutil.which", return_value="/tool"), patch("bg3tool.cli.subprocess.run", side_effect=subprocess.CalledProcessError(2, ["divine"])) as run:
            code, out, _ = self.call("pack", "--execute")
        self.assertEqual(code, 1)
        self.assertEqual(run.call_count, 1)
        self.assertNotIn("PAK 생성 완료", out)

    def test_execute_uses_argument_array_and_packages_each_module(self):
        def fake_pack(command, check):
            self.assertTrue(check)
            self.assertEqual(command[0], "/path with spaces/divine")
            Path(command[-1]).write_bytes(b"test fixture only")
        with patch("bg3tool.cli.shutil.which", return_value="/tool"), patch("bg3tool.cli.subprocess.run", side_effect=fake_pack) as run:
            code, _, err = self.call("pack", "--divine", "/path with spaces/divine", "--execute")
        self.assertEqual(code, 0, err)
        self.assertEqual(run.call_count, 5)

    def test_unknown_profile_and_invalid_json_have_clear_errors(self):
        self.assertEqual(self.call("build", "--profile", "missing")[0], 1)
        (self.root / "modproject.json").write_text("{")
        self.assertEqual(self.call("doctor")[0], 1)


if __name__ == "__main__":
    unittest.main()
