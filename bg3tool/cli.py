"""Dependency-free source validation, staging, inspection and Divine integration."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
import xml.etree.ElementTree as ET


class ToolError(Exception):
    pass


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_project(root):
    project = read_json(root / "modproject.json")
    if project.get("schema_version") != 1:
        raise ToolError("지원하지 않는 프로젝트 스키마")
    modules = project.get("modules")
    if not isinstance(modules, list) or not modules:
        raise ToolError("modules는 비어 있지 않은 배열이어야 합니다")
    names, ids = set(), set()
    for module in modules:
        name = module["name"]
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", name):
            raise ToolError(f"잘못된 모듈 이름: {name}")
        ident = str(uuid.UUID(module["uuid"]))
        if name in names or ident in ids:
            raise ToolError("중복 모듈 이름 또는 UUID")
        names.add(name)
        ids.add(ident)
        if not isinstance(module.get("dependencies"), list):
            raise ToolError(f"{name}: dependencies 배열 필요")
    version = project.get("version64")
    if type(version) is not int or not 0 <= version < 2**63:
        raise ToolError("version64는 0 이상 Int64 범위 정수여야 합니다")
    order_modules(project, names)
    return project


def order_modules(project, requested):
    modules = {m["name"]: m for m in project["modules"]}
    result, active, done = [], set(), set()

    def visit(name):
        if name not in modules:
            raise ToolError(f"알 수 없는 모듈: {name}")
        if name in active:
            raise ToolError(f"순환 의존성: {name}")
        if name in done:
            return
        active.add(name)
        for dependency in modules[name]["dependencies"]:
            visit(dependency)
        active.remove(name)
        done.add(name)
        result.append(modules[name])

    for name in sorted(requested):
        visit(name)
    return result


def source_files(root, module):
    base = root / "modules" / module["name"] / "source"
    if not base.is_dir():
        raise ToolError(f"소스 디렉터리 없음: {base}")
    if base.is_symlink() or not base.resolve().is_relative_to(root.resolve()):
        raise ToolError(f"소스 경로가 프로젝트 밖을 가리킵니다: {base}")
    for path in sorted(base.rglob("*")):
        if path.is_symlink():
            raise ToolError(f"소스 심볼릭 링크는 지원하지 않습니다: {path}")
        if not path.is_file() or path.name == ".gitkeep":
            continue
        relative = path.relative_to(base)
        if relative.parts[0] not in {"Mods", "Public", "Localization"}:
            raise ToolError(f"지원하지 않는 패키지 경로: {relative}")
        if relative.as_posix().casefold() == f"Mods/{module['folder']}/meta.lsx".casefold():
            raise ToolError("meta.lsx는 manifest에서 생성합니다. 소스에서 제거하세요")
        yield path, relative


def validate(root, project, modules):
    owned, count = {}, 0
    for module in modules:
        if module["folder"] != "BG3_2024_" + module["name"]:
            raise ToolError(f"{module['name']}: 잘못된 폴더 이름")
        for path, relative in source_files(root, module):
            key = relative.as_posix().casefold()
            if key in owned:
                raise ToolError(f"패키지 경로 충돌: {relative} ({owned[key]}, {module['name']})")
            owned[key] = module["name"]
            if path.suffix.lower() in {".lsx", ".xml"}:
                ET.parse(path)
            elif path.suffix.lower() == ".json":
                read_json(path)
            count += 1
    return count


def metadata(project, module):
    root = ET.Element("save")
    ET.SubElement(root, "version", major="4", minor="0", revision="9", build="0")
    region = ET.SubElement(root, "region", id="Config")
    children = ET.SubElement(ET.SubElement(region, "node", id="root"), "children")
    dependencies = ET.SubElement(children, "node", id="Dependencies")
    lookup = {m["name"]: m for m in project["modules"]}

    def attributes(node, values):
        for key, kind, value in values:
            ET.SubElement(node, "attribute", id=key, type=kind, value=str(value))

    if module["dependencies"]:
        dep_children = ET.SubElement(dependencies, "children")
        for name in module["dependencies"]:
            dep = lookup[name]
            attributes(ET.SubElement(dep_children, "node", id="ModuleShortDesc"), [
                ("Folder", "LSString", dep["folder"]), ("Name", "LSString", dep["name"]),
                ("UUID", "FixedString", dep["uuid"]), ("Version64", "int64", project["version64"]),
                ("MD5", "LSString", ""),
            ])
    attributes(ET.SubElement(children, "node", id="ModuleInfo"), [
        ("Author", "LSString", project["author"]),
        ("Description", "LSString", module["description"] + " [Development scaffold; gameplay not implemented]"),
        ("Folder", "LSString", module["folder"]), ("Name", "LSString", "BG3 2024 " + module["name"]),
        ("UUID", "FixedString", module["uuid"]), ("Version64", "int64", project["version64"]),
        ("Type", "FixedString", "Add-on"), ("MD5", "LSString", ""),
    ])
    ET.indent(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def build(root, project, modules):
    validate(root, project, modules)
    build_root = root / "build"
    build_root.mkdir(exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix="stage-", dir=build_root))
    report = {"status": "scaffold_not_game_verified", "modules": [], "files": {}}
    try:
        for module in modules:
            stage = destination / module["name"]
            meta = stage / "Mods" / module["folder"] / "meta.lsx"
            meta.parent.mkdir(parents=True)
            meta.write_bytes(metadata(project, module))
            for path, relative in source_files(root, module):
                target = stage / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
            report["modules"].append(module["name"])
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                report["files"][path.relative_to(destination).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        write_json(destination / "build-report.json", report)
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def inspect_lsx(path):
    """Export actual attribute IDs and values without guessing BG3 schemas."""
    result = []
    for _, element in ET.iterparse(path, events=("end",)):
        if element.tag == "node":
            attributes = [{"id": a.get("id"), "type": a.get("type"), "value": a.get("value")}
                          for a in element.findall("attribute")]
            if attributes:
                result.append({"node": element.get("id"), "attributes": attributes})
            element.clear()
    return {"file": str(path.resolve()), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "nodes": result}


def parser():
    p = argparse.ArgumentParser(description="BG3 2024 Level20 모드 개발 CLI")
    p.add_argument("--project", type=Path, default=Path.cwd(), help="프로젝트 루트")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="환경 및 미확인 게임 빌드 표시")
    commands.add_parser("status", help="모듈과 첫 구현 작업 상태")
    for name in ("validate", "build", "pack"):
        sub = commands.add_parser(name)
        sub.add_argument("--profile", default="prototype")
        if name == "pack":
            sub.add_argument("--divine", default=os.environ.get("BG3_DIVINE", "divine"))
            sub.add_argument("--execute", action="store_true", help="실제 PAK 생성; 기본은 명령 미리보기")
    inspect = commands.add_parser("inspect", help="추출·변환된 원본 LSX의 속성을 JSON으로 출력")
    inspect.add_argument("file", type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print(json.dumps(inspect_lsx(args.file), ensure_ascii=False, indent=2))
            return 0
        root = args.project.resolve()
        project = load_project(root)
        if args.command == "doctor":
            print(json.dumps({"python": sys.version.split()[0], "platform": sys.platform,
                              "project": str(root), "game_build": project["game_build"],
                              "divine": shutil.which(os.environ.get("BG3_DIVINE", "divine")),
                              "game_verified": False}, ensure_ascii=False, indent=2))
            return 0
        if args.command == "status":
            for module in order_modules(project, [m["name"] for m in project["modules"]]):
                print(f"{module['name']}: scaffold | 의존: {', '.join(module['dependencies']) or '-'}")
            for task in read_json(root / "data" / "milestones.json")["tasks"]:
                print(f"[{task['status']}] {task['id']}: {task['title']}")
            return 0
        if args.profile not in project["profiles"]:
            raise ToolError(f"알 수 없는 프로필: {args.profile}")
        modules = order_modules(project, project["profiles"][args.profile])
        count = validate(root, project, modules)
        if args.command == "validate":
            print(f"구조 검사 통과: {len(modules)}개 모듈, {count}개 소스 파일. 게임 동작은 미검증.")
            return 0
        if args.command == "pack" and args.execute and not shutil.which(args.divine):
            raise ToolError("Divine 실행 파일을 찾을 수 없습니다. --divine 또는 BG3_DIVINE을 지정하세요")
        stage = build(root, project, modules)
        print(f"빌드: {stage}")
        if args.command == "pack":
            output = root / "dist" / stage.name
            for module in modules:
                target = output / (module["folder"] + ".pak")
                command = [args.divine, "-g", "bg3", "-a", "create-package", "-s",
                           str(stage / module["name"]), "-d", str(target)]
                print(json.dumps(command, ensure_ascii=False))
                if args.execute:
                    output.mkdir(parents=True, exist_ok=True)
                    subprocess.run(command, check=True)
                    if not target.is_file() or target.stat().st_size == 0:
                        raise ToolError(f"Divine이 PAK 파일을 생성하지 않았습니다: {target}")
            print("PAK 생성 완료 (게임 미검증)" if args.execute else "명령 미리보기만 완료. 실제 생성은 --execute 사용.")
        return 0
    except (ToolError, OSError, ValueError, KeyError, TypeError, ET.ParseError, subprocess.CalledProcessError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
