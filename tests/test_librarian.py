import io
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
import librarian as lb  # noqa: E402

EN = lb.DOC_STRINGS["en"]
KO = lb.DOC_STRINGS["ko"]

SOURCES = {
    "src/auth/auth.py": (
        "import os\n"
        "\n"
        "class Session:\n"
        "    def refresh(self):\n"
        "        def inner():\n"
        "            pass\n"
        "\n"
        "@decorator\n"
        "def login(user):\n"
        "    return user\n"
    ),
    "src/api/svc.ts": (
        "export class Svc {\n"
        "  run(): void {}\n"
        "}\n"
        "export const handler = () => 1;\n"
        "describe('x', () => { it('y', () => {}); });\n"
    ),
    "web/main.go": "package web\n\ntype S struct{}\n\nfunc (s *S) Do() {}\n\nfunc Top() {}\n",
    "native/lib.cpp": "namespace ns {\nclass C { public: void m(); };\nvoid C::m() {}\n}\nint *make() { return 0; }\n",
    "native/lib.rs": "struct P;\nimpl P {\n    fn new() -> P { P }\n}\nfn main() {}\n",
    "native/J.java": "class J {\n  J() {}\n  void run() {}\n}\n",
    "native/K.cs": "namespace N {\n class K {\n  public void M() {}\n }\n}\n",
    "assets/logo.txt": "not code\n",
}


def git(root, *args):
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    for rel, text in SOURCES.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    git(tmp_path, "init", "-q")
    return tmp_path


def run(root, *argv):
    lb.main(["--root", str(root), *argv])


def init(root, language=None):
    extra = ["--language", language] if language else []
    run(root, "init", *extra)
    run(root, "scaffold")


def root_doc(project):
    return (project / "CLAUDE.md").read_text(encoding="utf-8")


def commit_all(project):
    git(project, "add", "-A")
    git(project, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "c")


def index_rows(doc: Path):
    text = doc.read_text(encoding="utf-8")
    block = text[text.index(lb.INDEX_START):text.index(lb.INDEX_END)]
    rows = []
    for line in block.splitlines()[3:]:
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rows.append(tuple(cells))
    return rows


def hook(event, payload):
    stdin, stdout = sys.stdin, sys.stdout
    sys.stdin = io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode("utf-8")), encoding="utf-8")
    sys.stdout = io.StringIO()
    try:
        lb.main(["hook", event])
        return sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = stdin, stdout


def additional_context(hook_output, event_name):
    """The additionalContext text of the JSON a hook printed."""
    parsed = json.loads(hook_output)["hookSpecificOutput"]
    assert parsed["hookEventName"] == event_name
    return parsed["additionalContext"]


def hooks_json_entry(event):
    hooks = json.loads((REPO_ROOT / "hooks/hooks.json").read_text(encoding="utf-8"))
    return hooks["hooks"][event][0]["hooks"][0]


def run_hook_command(event, payload):
    """Run the command hooks.json registers for `event` in a shell, the way Claude Code does,
    with the payload on stdin and the payload's cwd as the working directory."""
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)}
    return subprocess.run(hooks_json_entry(event)["command"], shell=True, cwd=payload["cwd"],
                          env=env, input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, timeout=60)


# ---------------------------------------------------------------- extraction


@pytest.mark.parametrize("rel,expected", [
    ("src/auth/auth.py", [("Session", 3, 6), ("Session.refresh", 4, 6), ("login", 9, 10)]),
    ("src/api/svc.ts", [("Svc", 1, 3), ("Svc.run", 2, 2), ("handler", 4, 4)]),
    ("web/main.go", [("S", 3, 3), ("S.Do", 5, 5), ("Top", 7, 7)]),
    ("native/lib.cpp", [("C", 2, 2), ("C::m", 3, 3), ("make", 5, 5)]),
    ("native/lib.rs", [("P", 1, 1), ("P", 2, 4), ("P.new", 3, 3), ("main", 5, 5)]),
    ("native/J.java", [("J", 1, 4), ("J.J", 2, 2), ("J.run", 3, 3)]),
    ("native/K.cs", [("K", 2, 4), ("K.M", 3, 3)]),
])
def test_extract_symbols(project, rel, expected):
    assert lb.extract_symbols(project / rel) == expected


# ---------------------------------------------------------------- scaffold / index


def test_scaffold_creates_hierarchy(project):
    init(project)
    for d in [".", "src", "src/auth", "src/api", "web", "native", "assets"]:
        assert (project / d / "CLAUDE.md").is_file(), d
    root = root_doc(project)
    assert root.startswith(f"# {project.name}\n\n{EN['role']}\n")  # no rules or skill pointer
    assert "| src/ |" in root and "| web/ |" in root
    assert lb.INDEX_START not in root  # the root has no code files
    sub = (project / "src/auth/CLAUDE.md").read_text(encoding="utf-8")
    assert sub.startswith("# Parent: ../CLAUDE.md")
    assert index_rows(project / "src/auth/CLAUDE.md") == [
        ("auth.py", "Session", "3", "6"), ("auth.py", "Session.refresh", "4", "6"),
        ("auth.py", "login", "9", "10")]
    assert lb.INDEX_START not in (project / "assets/CLAUDE.md").read_text(encoding="utf-8")


def test_scaffold_does_not_overwrite(project):
    (project / "src").mkdir(exist_ok=True)
    (project / "src/CLAUDE.md").write_text("user document\n", encoding="utf-8")
    init(project)
    assert (project / "src/CLAUDE.md").read_text(encoding="utf-8") == "user document\n"


def test_index_preserves_human_text(project):
    init(project)
    doc = project / "src/auth/CLAUDE.md"
    text = doc.read_text(encoding="utf-8").replace(EN["placeholder"], "Auth module.\n\n- detail")
    text += "\n## Notes\n\nsection written by a human\n"
    doc.write_text(text, encoding="utf-8")
    src = project / "src/auth/auth.py"
    src.write_text("# header\n\n" + src.read_text(encoding="utf-8"), encoding="utf-8")
    run(project, "index", str(project / "src/auth"))
    out = doc.read_text(encoding="utf-8")
    assert "Auth module.\n\n- detail" in out and "section written by a human" in out
    assert ("auth.py", "Session", "5", "8") in index_rows(doc)
    run(project, "index", str(project / "src/auth"))
    assert doc.read_text(encoding="utf-8") == out  # idempotent


def test_exclude_and_gitignore(project):
    (project / ".gitignore").write_text("gen/\n", encoding="utf-8")
    (project / "gen").mkdir()
    (project / "gen/x.py").write_text("def f(): pass\n", encoding="utf-8")
    (project / "node_modules/p").mkdir(parents=True)
    (project / "node_modules/p/i.js").write_text("function f(){}\n", encoding="utf-8")
    (project / "tmpx").mkdir()
    (project / "tmpx/t.py").write_text("def f(): pass\n", encoding="utf-8")
    run(project, "init", "--exclude", "tmpx")
    run(project, "scaffold")
    for d in ["gen", "node_modules", "tmpx"]:
        assert not (project / d / "CLAUDE.md").exists(), d


# ---------------------------------------------------------------- hooks


def prepend_blank_lines_to_auth_source_and_fire_post_edit_hook(project, file_path=None):
    """Shift auth.py down by two lines the way an edit would, then run the post-edit hook.
    file_path is what the hook receives (default: the absolute path); returns the hook output."""
    src = project / "src/auth/auth.py"
    src.write_text("\n\n" + src.read_text(encoding="utf-8"), encoding="utf-8")
    return hook("post-edit", {"cwd": str(project), "tool_name": "Edit",
                              "tool_input": {"file_path": file_path or str(src)}})


def test_hook_post_edit_claude(project):
    init(project)
    out = prepend_blank_lines_to_auth_source_and_fire_post_edit_hook(project)
    assert out == ""
    assert ("auth.py", "Session", "5", "8") in index_rows(project / "src/auth/CLAUDE.md")


def test_hook_post_edit_new_folder_creates_documents(project):
    init(project)
    (project / "src/db").mkdir()
    conn = project / "src/db/conn.py"
    conn.write_text("def connect():\n    pass\n", encoding="utf-8")
    out = hook("post-edit", {"cwd": str(project), "tool_name": "Write",
                             "tool_input": {"file_path": str(conn)}})
    assert "src/db" in additional_context(out, "PostToolUse")
    assert index_rows(project / "src/db/CLAUDE.md") == [("conn.py", "connect", "1", "2")]
    assert "| db/ |" in (project / "src/CLAUDE.md").read_text(encoding="utf-8")


def test_hook_post_edit_resolves_relative_file_path_against_cwd(project):
    init(project)
    prepend_blank_lines_to_auth_source_and_fire_post_edit_hook(project, "src/auth/auth.py")
    assert ("auth.py", "Session", "5", "8") in index_rows(project / "src/auth/CLAUDE.md")


def test_hook_ignores_unmanaged_project(tmp_path):
    (tmp_path / "a.py").write_text("def f(): pass\n", encoding="utf-8")
    out = hook("post-edit", {"cwd": str(tmp_path), "tool_input": {"file_path": str(tmp_path / "a.py")}})
    assert out == ""
    assert json.loads(hook("stop", {"cwd": str(tmp_path)})) == {}
    assert not (tmp_path / "CLAUDE.md").exists()


def test_hook_ignores_doc_edits(project):
    init(project)
    doc = project / "src/CLAUDE.md"
    before = doc.read_text(encoding="utf-8")
    hook("post-edit", {"cwd": str(project), "tool_input": {"file_path": str(doc)}})
    assert doc.read_text(encoding="utf-8") == before


def _fill_all_roles(project):
    for doc in project.rglob("CLAUDE.md"):
        if ".librarian" in doc.parts:
            continue
        text = doc.read_text(encoding="utf-8").replace(EN["placeholder"], "role")
        doc.write_text(text, encoding="utf-8")


def test_hook_stop_after_folder_changes(project):
    init(project)
    _fill_all_roles(project)
    commit_all(project)
    assert json.loads(hook("stop", {"cwd": str(project)})) == {}

    # a deleted folder and a brand-new folder (created without any document)
    shutil.rmtree(project / "src/api")
    (project / "src/billing").mkdir()
    (project / "src/billing/pay.py").write_text("def pay(): pass\n", encoding="utf-8")
    out = json.loads(hook("stop", {"cwd": str(project), "stop_hook_active": False}))
    assert out["decision"] == "block" and "src/billing" in out["reason"]
    table = (project / "src/CLAUDE.md").read_text(encoding="utf-8")
    assert "| api/ |" not in table and f"| billing/ | {EN['placeholder']} |" in table

    again = json.loads(hook("stop", {"cwd": str(project), "stop_hook_active": True}))
    assert "decision" not in again


def test_hook_stop_warns_on_deep_folders_only(project):
    init(project)
    cfg = read_config(project)
    cfg["maxDepth"] = 1
    cfg["maxEntries"] = 1  # a legacy key: many index rows no longer cause a warning
    write_config(project, cfg)
    out = json.loads(hook("stop", {"cwd": str(project), "stop_hook_active": True}))
    assert "src/auth: folder depth 2 > 1" in out["systemMessage"]
    assert "index rows" not in out["systemMessage"]
    assert "native" not in out["systemMessage"]


def test_init_installs_no_skill(project):
    init(project)
    assert not (project / ".librarian/skills").exists()
    assert not any((project / agent / "skills").exists() for agent in (".claude", ".agents", ".codex"))
    assert not (project / ".gitignore").exists()


def test_pending_deepest_first(project, capsys):
    init(project)
    capsys.readouterr()
    run(project, "pending")
    lines = capsys.readouterr().out.split()
    depths = [0 if l == "." else len(Path(l).parts) for l in lines]
    assert depths == sorted(depths, reverse=True) and lines[-1] == "."


# ---------------------------------------------------------------- library language


def test_default_language_is_english(project):
    init(project)
    assert json.loads((project / ".librarian/config.json").read_text(encoding="utf-8"))["language"] == "en"
    text = (project / "src/auth/CLAUDE.md").read_text(encoding="utf-8")
    assert EN["role"] in text and "| File | Function | Start | End |" in text
    assert "| Folder | Role |" in (project / "src/CLAUDE.md").read_text(encoding="utf-8")


def test_korean_library(project):
    init(project, language="ko")
    text = (project / "src/auth/CLAUDE.md").read_text(encoding="utf-8")
    assert text.startswith("# 상위 문서: ../CLAUDE.md")
    assert KO["role"] in text and KO["placeholder"] in text and "| 파일 | 함수 | 시작 줄 | 끝 줄 |" in text
    assert root_doc(project).startswith(f"# {project.name}\n\n{KO['role']}\n")
    assert "src/auth" in [r for r in lb.sync_dirs(lb.load_library(project), None, False).pending]


def test_language_switch_keeps_roles(project):
    init(project, language="ko")
    doc = project / "src/CLAUDE.md"
    doc.write_text(doc.read_text(encoding="utf-8")
                   .replace(KO["placeholder"], "소스 코드", 1)
                   .replace(f"| auth/ | {KO['placeholder']} |", "| auth/ | 인증 |"), encoding="utf-8")
    run(project, "init", "--language", "en")
    run(project, "index", "--all")
    text = doc.read_text(encoding="utf-8")
    assert text.startswith("# Parent: ../CLAUDE.md")
    assert EN["role"] in text and "소스 코드" in text
    assert "| auth/ | 인증 |" in text and f"| api/ | {EN['placeholder']} |" in text
    assert not any(v in text for v in (KO["role"], KO["subdirs"], KO["placeholder"]))


def test_unknown_language_uses_english_headings(project):
    init(project, language="ja")
    assert EN["role"] in (project / "src/CLAUDE.md").read_text(encoding="utf-8")
    init(project)
    out = json.loads(hook("stop", {"cwd": str(project)}))
    assert out["decision"] == "block" and "(ja)" in out["reason"]


# ---------------------------------------------------------------- QA round 3 regressions (sync)


def _role_doc(project, rel):
    return (project / rel / "CLAUDE.md")


def test_unmatched_or_fenced_marker_keeps_human_text(project):
    init(project)
    doc = _role_doc(project, "src/auth")
    text = doc.read_text(encoding="utf-8")
    fenced = ("Example of the generated block:\n\n```markdown\n" + lb.INDEX_START
              + "\n| File | Function | Line |\n```\n")
    text = text.replace(EN["placeholder"], fenced)
    doc.write_text(text, encoding="utf-8")
    run(project, "index", str(project / "src/auth"))
    out = doc.read_text(encoding="utf-8")
    assert fenced in out
    assert ("auth.py", "login", "9", "10") in index_rows(doc)

    # a start marker without an end marker is treated as text, not as the index
    broken = out.replace(lb.INDEX_END, "") + "\n## Notes\n\nkeep me\n"
    doc.write_text(broken, encoding="utf-8")
    run(project, "index", str(project / "src/auth"))
    assert "keep me" in doc.read_text(encoding="utf-8")


def test_heading_inside_code_fence_is_not_a_section(project):
    init(project)
    doc = _role_doc(project, "src")
    role = "Build notes:\n\n```bash\n# install deps first\nnpm ci\n```"
    doc.write_text(doc.read_text(encoding="utf-8").replace(EN["placeholder"], role, 1), encoding="utf-8")
    run(project, "index", str(project / "src"))
    out = doc.read_text(encoding="utf-8")
    assert role in out
    assert out.index(role) < out.index(EN["subdirs"])


def test_text_under_subfolder_table_is_kept(project):
    init(project)
    doc = _role_doc(project, "src")
    text = doc.read_text(encoding="utf-8")
    table_end = text.index("| auth/ |")
    line_end = text.index("\n", table_end)
    text = text[:line_end + 1] + "\nNote: api/ is being split.\n" + text[line_end + 1:]
    doc.write_text(text, encoding="utf-8")
    run(project, "index", str(project / "src"))
    assert "Note: api/ is being split." in doc.read_text(encoding="utf-8")


def convert_library_to_agents_docs(project):
    """Rewrite a fresh library the way older versions stored it with docName "AGENTS.md" and
    "both": every CLAUDE.md becomes AGENTS.md, and CLAUDE.md is left as the "@AGENTS.md" alias."""
    for claude_doc in sorted(project.rglob("CLAUDE.md")):
        if ".librarian" in claude_doc.parts:
            continue
        text = claude_doc.read_text(encoding="utf-8").replace("../CLAUDE.md", "../AGENTS.md")
        (claude_doc.parent / "AGENTS.md").write_text(text, encoding="utf-8")
        claude_doc.write_text("@AGENTS.md\n", encoding="utf-8")


def test_update_converts_agents_based_library_to_claude_docs_keeping_roles(project):
    init(project)
    doc = _role_doc(project, "src")
    doc.write_text(doc.read_text(encoding="utf-8").replace(EN["placeholder"], "Source code.", 1),
                   encoding="utf-8")
    convert_library_to_agents_docs(project)

    run(project, "update")

    assert not list(project.rglob("AGENTS.md"))
    converted = doc.read_text(encoding="utf-8")
    assert "Source code." in converted
    assert converted.startswith("# Parent: ../CLAUDE.md")
    assert "# Parent: ../CLAUDE.md" in _role_doc(project, "src/auth").read_text(encoding="utf-8")
    assert ("auth.py", "Session", "3", "6") in index_rows(_role_doc(project, "src/auth"))


def test_update_keeps_human_written_claude_doc_next_to_agents_doc(project):
    init(project)
    convert_library_to_agents_docs(project)
    human_doc = _role_doc(project, "src")
    human_doc.write_text("# Written by a human\n", encoding="utf-8")

    run(project, "update")

    assert human_doc.read_text(encoding="utf-8").startswith("# Written by a human")
    assert (project / "src/AGENTS.md").is_file()


def test_update_migrating_agents_docs_prints_no_warning(project, capsys):
    init(project)
    doc = _role_doc(project, "src")
    doc.write_text(doc.read_text(encoding="utf-8").replace(EN["placeholder"], "Source code.", 1),
                   encoding="utf-8")
    convert_library_to_agents_docs(project)
    capsys.readouterr()

    run(project, "update")

    output = capsys.readouterr()
    assert "warning" not in (output.out + output.err).lower()
    assert not list(project.rglob("AGENTS.md"))
    assert "Source code." in doc.read_text(encoding="utf-8")


def test_update_indexes_human_written_agents_md_as_ordinary_markdown_and_keeps_it(project):
    init(project)
    human_agents_doc = project / "src/AGENTS.md"
    human_text = "# Agent instructions\n\n## Notes\n\nRun the tests first.\n"
    human_agents_doc.write_text(human_text, encoding="utf-8")

    run(project, "update")

    assert human_agents_doc.read_text(encoding="utf-8") == human_text
    assert ("AGENTS.md", "# Agent instructions", "1", "5") in index_rows(_role_doc(project, "src"))


def test_post_edit_updates_parent_of_topmost_new_folder(project):
    init(project)
    new = project / "x/y z/한/q.py"
    new.parent.mkdir(parents=True)
    new.write_text("def q(): pass\n", encoding="utf-8")
    hook("post-edit", {"cwd": str(project), "tool_input": {"file_path": str(new)}})
    assert "| x/ |" in root_doc(project)
    assert "| y z/ |" in (project / "x/CLAUDE.md").read_text(encoding="utf-8")


def test_renamed_folder_keeps_role_cell(project):
    init(project)
    _fill_all_roles(project)
    commit_all(project)
    doc = project / "src/CLAUDE.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace("| auth/ | role |", "| auth/ | Login |"),
                   encoding="utf-8")
    shutil.move(str(project / "src/auth"), str(project / "src/identity"))
    out = json.loads(hook("stop", {"cwd": str(project)}))
    assert "| identity/ | Login |" in doc.read_text(encoding="utf-8")
    assert "decision" not in out


def test_config_with_bom(project):
    init(project)
    cfg = project / ".librarian/config.json"
    cfg.write_bytes(b"\xef\xbb\xbf" + cfg.read_bytes())
    run(project, "index", "--all")
    src = project / "src/auth/auth.py"
    src.write_text("\n" + src.read_text(encoding="utf-8"), encoding="utf-8")
    hook("post-edit", {"cwd": str(project), "tool_input": {"file_path": str(src)}})
    assert ("auth.py", "Session", "4", "7") in index_rows(project / "src/auth/CLAUDE.md")


def test_stop_hook_active_string_false(project):
    init(project)
    out = json.loads(hook("stop", {"cwd": str(project), "stop_hook_active": "false"}))
    assert out.get("decision") == "block"


def test_parse_failure_keeps_previous_rows(project):
    init(project)
    (project / "src/auth/auth.py").write_text("def broken(:\n", encoding="utf-8")
    run(project, "index", str(project / "src/auth"))
    assert ("auth.py", "login", "9", "10") in index_rows(project / "src/auth/CLAUDE.md")


def test_parse_failure_keeps_legacy_three_column_rows(project):
    init(project)
    doc = project / "src/auth/CLAUDE.md"
    text = doc.read_text(encoding="utf-8")
    new_block = text[text.index(lb.INDEX_START):text.index(lb.INDEX_END)]
    legacy_block = (f"{lb.INDEX_START}\n| File | Function | Line |\n|---|---|---|\n"
                    "| auth.py | Session | 3 |\n| auth.py | login | 9 |\n")
    doc.write_text(text.replace(new_block, legacy_block), encoding="utf-8")
    (project / "src/auth/auth.py").write_text("def broken(:\n", encoding="utf-8")

    run(project, "index", str(project / "src/auth"))

    assert index_rows(doc) == [("auth.py", "Session", "3", "-"), ("auth.py", "login", "9", "-")]
    assert "| File | Function | Start | End |" in doc.read_text(encoding="utf-8")


def test_invalid_config_numbers_fall_back(project):
    init(project)
    cfg = read_config(project)
    cfg["maxDepth"] = "deep"
    write_config(project, cfg)
    run(project, "index", "--all")  # must not raise


def test_many_files_is_fast(tmp_path):
    import time
    for d in range(200):
        for f in range(15):
            p = tmp_path / f"pkg{d % 20}" / f"mod{d}" / f"f{f}.py"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("def f(): pass\n", encoding="utf-8")
    git(tmp_path, "init", "-q")
    run(tmp_path, "init")
    start = time.perf_counter()
    run(tmp_path, "index", "--all")
    run(tmp_path, "pending")
    assert time.perf_counter() - start < 15


def test_unclosed_fence_is_idempotent(project):
    init(project)
    doc = project / "src/CLAUDE.md"
    doc.write_text(f"# Parent: ../CLAUDE.md\n\n{EN['role']}\n\nRole:\n\n```\ncode\n", encoding="utf-8")
    run(project, "index", str(project / "src"))
    first = doc.read_text(encoding="utf-8")
    run(project, "index", str(project / "src"))
    run(project, "index", str(project / "src"))
    assert doc.read_text(encoding="utf-8") == first
    assert first.count(EN["subdirs"]) == 1


def test_orphan_start_marker_never_loses_text(project):
    init(project)
    doc = project / "src/auth/CLAUDE.md"
    text = doc.read_text(encoding="utf-8").replace(lb.INDEX_END, "") + "\n## Notes\n\nImportant human notes\n"
    doc.write_text(text, encoding="utf-8")
    for _ in range(3):
        run(project, "index", str(project / "src/auth"))
    out = doc.read_text(encoding="utf-8")
    assert "Important human notes" in out
    assert out.count(lb.INDEX_START) == 1 and out.count(lb.INDEX_END) == 1


def test_parse_failure_without_previous_rows_lists_file(project):
    init(project)
    (project / "src/auth/new.py").write_text("def broken(:\n", encoding="utf-8")
    run(project, "index", str(project / "src/auth"))
    assert ("new.py", "-", "-", "-") in index_rows(project / "src/auth/CLAUDE.md")


def test_negative_limits_fall_back(project):
    init(project)
    cfg = read_config(project)
    cfg["maxDepth"] = -5
    write_config(project, cfg)
    assert lb.load_library(project).config["maxDepth"] == lb.DEFAULT_CONFIG["maxDepth"]


# ---------------------------------------------------------------- config


def read_config(project):
    return json.loads((project / ".librarian/config.json").read_text(encoding="utf-8"))


def write_config(project, cfg):
    (project / ".librarian/config.json").write_text(json.dumps(cfg), encoding="utf-8")


# keys written by versions that had the index-row warning, the session-start hook, the
# rules skill links, or the AGENTS.md document mode
@pytest.mark.parametrize("key,value", [("maxEntries", 60), ("injectRules", False),
                                       ("targets", ["claude"]), ("docName", "both")])
@pytest.mark.parametrize("command", ["update", "init"])
def test_rewriting_config_drops_removed_key_and_keeps_others(project, key, value, command):
    init(project)
    write_config(project, {"language": "en", "maxDepth": 4, key: value})

    run(project, "index", "--all")  # must not raise
    run(project, command)

    cfg = read_config(project)
    assert key not in cfg
    assert cfg["maxDepth"] == 4


# ---------------------------------------------------------------- folder notes section


@pytest.mark.parametrize("strings,language", [(EN, "en"), (KO, "ko")])
def test_new_document_has_notes_heading_between_role_and_subfolders(project, strings, language):
    init(project, language=language)

    text = _role_doc(project, "src").read_text(encoding="utf-8")

    assert text.index(strings["role"]) < text.index(strings["notes"]) < text.index(strings["subdirs"])
    assert f"{strings['notes']}\n\n{strings['subdirs']}" in text  # empty notes: heading only
    assert text.count(strings["notes"]) == 1


def test_notes_text_written_by_a_human_survives_index_and_hook(project):
    init(project)
    doc = _role_doc(project, "src/auth")
    text = doc.read_text(encoding="utf-8")
    doc.write_text(text.replace(f"{EN['notes']}\n", f"{EN['notes']}\n\nAlways hash tokens.\n\n- keep it short\n", 1),
                   encoding="utf-8")

    prepend_blank_lines_to_auth_source_and_fire_post_edit_hook(project)
    run(project, "index", str(project / "src/auth"))

    out = doc.read_text(encoding="utf-8")
    assert f"{EN['notes']}\n\nAlways hash tokens.\n\n- keep it short\n\n{lb.INDEX_START}" in out
    assert ("auth.py", "Session", "5", "8") in index_rows(doc)


def test_update_adds_notes_heading_to_old_format_document_and_keeps_the_rest(project):
    init(project)
    doc = _role_doc(project, "src")
    doc.write_text(
        "# Parent: ../CLAUDE.md\n\n"
        f"{EN['role']}\n\nSource code.\n\n"
        f"{EN['subdirs']}\n\n| Folder | Role |\n|---|---|\n| api/ | HTTP API |\n| auth/ | Login |\n\n"
        "note under the table\n\n"
        "## Rules\n\nNever import auth from api.\n",
        encoding="utf-8")

    run(project, "update")

    text = doc.read_text(encoding="utf-8")
    assert text.index(EN["role"]) < text.index(EN["notes"]) < text.index(EN["subdirs"])
    assert "Source code." in text and "| api/ | HTTP API |" in text and "| auth/ | Login |" in text
    assert "note under the table" in text
    assert text.index(EN["subdirs"]) < text.index("## Rules") < text.index("Never import auth from api.")
    assert f"{EN['notes']}\n\n{EN['subdirs']}" in text


def test_second_run_leaves_document_with_notes_byte_identical(project):
    init(project)
    doc = _role_doc(project, "src")
    doc.write_text(doc.read_text(encoding="utf-8").replace(
        f"{EN['notes']}\n", f"{EN['notes']}\n\nhuman note\n", 1) + "\n## Rules\n\nkeep me\n",
        encoding="utf-8")
    run(project, "update")
    first = doc.read_bytes()

    run(project, "update")
    run(project, "index", "--all")

    assert doc.read_bytes() == first


def test_empty_notes_do_not_make_a_folder_pending(project, capsys):
    init(project)
    doc = _role_doc(project, "src/auth")
    doc.write_text(doc.read_text(encoding="utf-8").replace(EN["placeholder"], "Login code."),
                   encoding="utf-8")
    capsys.readouterr()

    run(project, "pending")

    assert "src/auth" not in capsys.readouterr().out.split()
    assert f"{EN['notes']}\n\n{lb.INDEX_START}" in doc.read_text(encoding="utf-8")


# ---------------------------------------------------------------- update


def test_update_fills_missing_keys_and_records_version(project):
    init(project)
    write_config(project, {"language": "en"})
    run(project, "update")
    cfg = read_config(project)
    assert cfg["libraryVersion"] == lb.plugin_version()
    assert cfg["maxDepth"] == lb.DEFAULT_CONFIG["maxDepth"]


def test_update_keeps_korean_headings_and_roles(project):
    init(project, language="ko")
    doc = project / "src/CLAUDE.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(KO["placeholder"], "소스 코드", 1),
                   encoding="utf-8")
    run(project, "update")
    text = doc.read_text(encoding="utf-8")
    assert text.startswith("# 상위 문서: ../CLAUDE.md")
    assert KO["role"] in text and "소스 코드" in text


# ---------------------------------------------------------------- stop hook version notice


# These tests pass stop_hook_active: True only to suppress the empty-role block, so the
# output holds nothing but the version notice.


def stop_with_library_version(project, version):
    cfg = read_config(project)
    if version is None:
        del cfg["libraryVersion"]
    else:
        cfg["libraryVersion"] = version
    write_config(project, cfg)
    return json.loads(hook("stop", {"cwd": str(project), "stop_hook_active": True}))


def test_stop_hook_asks_for_update_when_library_is_older(project):
    init(project)
    out = stop_with_library_version(project, "0.0.1")
    assert "/update-library" in out["systemMessage"]


def test_stop_hook_asks_for_update_when_library_has_no_version(project):
    init(project)
    out = stop_with_library_version(project, None)
    assert "/update-library" in out["systemMessage"]


def test_stop_hook_asks_to_update_plugin_when_library_is_newer(project):
    init(project)
    out = stop_with_library_version(project, "99.0.0")
    assert "update the plugin" in out["systemMessage"]
    assert "/update-library" not in out["systemMessage"]


def test_stop_hook_without_plugin_version_still_blocks_on_empty_roles(project, monkeypatch):
    init(project)
    monkeypatch.setattr(lb, "plugin_version", lambda: None)
    out = json.loads(hook("stop", {"cwd": str(project)}))
    assert out["decision"] == "block"
    assert "systemMessage" not in out


def test_stop_hook_has_no_update_notice_when_versions_match(project):
    init(project)
    out = stop_with_library_version(project, lb.plugin_version())
    assert "systemMessage" not in out


# ---------------------------------------------------------------- legacy rules skill


# the exact lines older versions wrote, kept literal because they test real old documents
# ("agent-librarian" below is the plugin's old name, intentionally unchanged)
LEGACY_EN_NOTE = "This repository follows the rules of the `librarian-guide` skill."
LEGACY_KO_NOTE = "이 저장소는 `librarian-guide` 스킬의 규칙을 따릅니다."
LEGACY_GITIGNORE = ("node_modules/\n"
                    "\n"
                    "# agent-librarian: skill links (restored automatically by check)\n"
                    "/.claude/skills/librarian-guide\n"
                    "/.agents/skills/librarian-guide\n"
                    "/.codex/skills/librarian-guide\n")


def write_root_with_note(project, note):
    body = root_doc(project).split("\n", 2)[2]  # everything after "# <name>" and a blank line
    (project / "CLAUDE.md").write_text(
        f"# {project.name}\n\n{note}\n\nOur own intro.\n\n{body}", encoding="utf-8")


@pytest.mark.parametrize("language,note", [("en", LEGACY_EN_NOTE), ("ko", LEGACY_KO_NOTE)])
def test_sync_removes_legacy_root_note_and_keeps_user_text(project, language, note):
    init(project, language=language)
    write_root_with_note(project, note)

    run(project, "index", "--all")

    out = root_doc(project)
    role_heading = lb.DOC_STRINGS[language]["role"]
    assert out.startswith(f"# {project.name}\n\nOur own intro.\n\n{role_heading}\n")
    run(project, "index", "--all")
    assert root_doc(project) == out  # idempotent


def test_legacy_root_note_inside_code_fence_is_kept(project):
    init(project)
    fenced = f"```\n{LEGACY_EN_NOTE}\n```"
    write_root_with_note(project, fenced)
    run(project, "index", "--all")
    assert fenced in root_doc(project)


def make_legacy_skill_install(project):
    """What 0.4 installed: a source folder, a junction/symlink in .claude and copies (the
    fallback when linking failed) in .agents and .codex, plus the .gitignore lines."""
    source = project / ".librarian/skills/librarian-guide"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_bytes(b"---\nname: librarian-guide\n---\n# rules\n")
    link = project / ".claude/skills/librarian-guide"
    link.parent.mkdir(parents=True)
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(source), str(link))
    else:
        os.symlink(source, link, target_is_directory=True)
    for agent in (".agents", ".codex"):
        copy = project / agent / "skills/librarian-guide"
        copy.mkdir(parents=True)
        # a CRLF checkout of the same text still counts as an unedited copy
        (copy / "SKILL.md").write_bytes(b"---\r\nname: librarian-guide\r\n---\r\n# rules\r\n")
    (project / ".gitignore").write_text(LEGACY_GITIGNORE, encoding="utf-8")
    return source


@pytest.mark.parametrize("command", ["update", "init"])
def test_legacy_skill_links_and_gitignore_lines_are_removed(project, capsys, command):
    init(project)
    source = make_legacy_skill_install(project)
    capsys.readouterr()

    run(project, command)

    out = capsys.readouterr().out
    for agent in (".claude", ".agents", ".codex"):
        assert not os.path.lexists(project / agent / "skills/librarian-guide"), agent
        assert f"[updated] {agent}/skills/librarian-guide (removed)" in out
    # empty folders go, but .claude stays because Claude Code keeps settings there
    assert not os.path.lexists(project / ".agents") and not os.path.lexists(project / ".codex")
    assert not os.path.lexists(project / ".claude/skills") and (project / ".claude").is_dir()
    assert (project / ".gitignore").read_text(encoding="utf-8") == "node_modules/\n"
    # the source may hold rules the user wrote, so it stays and a warning names it
    assert (source / "SKILL.md").is_file()
    assert "[warning] .librarian/skills/librarian-guide is no longer used" in out


def test_legacy_skill_cleanup_keeps_other_skills_and_edited_copies(project, capsys):
    init(project)
    make_legacy_skill_install(project)
    (project / ".claude/skills/other").mkdir()  # a skill that is not ours
    edited = project / ".agents/skills/librarian-guide/SKILL.md"
    edited.write_bytes(edited.read_bytes() + b"My own rule.\n")
    capsys.readouterr()

    run(project, "update")

    out = capsys.readouterr().out
    assert (project / ".claude/skills/other").is_dir()
    assert edited.is_file()
    assert "[warning] .agents/skills/librarian-guide differs from" in out
    assert not os.path.lexists(project / ".codex/skills/librarian-guide")


def test_gitignore_cleanup_keeps_bom_and_crlf(project):
    init(project)
    legacy = "﻿" + LEGACY_GITIGNORE.replace("\n", "\r\n")
    (project / ".gitignore").write_bytes(legacy.encode("utf-8"))
    run(project, "update")
    assert (project / ".gitignore").read_bytes() == b"\xef\xbb\xbfnode_modules/\r\n"


def test_update_deletes_gitignore_that_held_only_skill_lines(project):
    init(project)
    (project / ".gitignore").write_text("\n" + LEGACY_GITIGNORE.split("\n", 1)[1], encoding="utf-8")
    run(project, "update")
    assert not (project / ".gitignore").exists()


def test_update_without_legacy_skill_prints_no_skill_lines(project, capsys):
    init(project)
    capsys.readouterr()
    run(project, "update")
    out = capsys.readouterr().out
    assert "librarian-guide" not in out and ".gitignore" not in out


def test_stop_command_from_hooks_json_removes_legacy_root_note(project):
    init(project)
    write_root_with_note(project, LEGACY_EN_NOTE)
    payload = {"cwd": str(project), "hook_event_name": "Stop", "stop_hook_active": True}

    res = run_hook_command("Stop", payload)

    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    assert LEGACY_EN_NOTE not in root_doc(project) and "Our own intro." in root_doc(project)


# ---------------------------------------------------------------- long documents: index levels

# The big folder holds three files with four functions each: 12 index rows. Rendered with the
# table inline its document is 24 lines, index.md is 15 lines, and one per-file table is 7
# lines, so these limits select level 0, 1 and 2.
LEVEL_0_LIMIT = 30
LEVEL_1_LIMIT = 20
LEVEL_2_LIMIT = 12
BIG_FILE_NAMES = ("a.py", "b.py", "c.py")


def write_big_source_files(folder, functions_per_file=4):
    folder.mkdir(exist_ok=True)
    for file_name in BIG_FILE_NAMES:
        prefix = file_name[0]
        (folder / file_name).write_text(
            "".join(f"def {prefix}{n}():\n    pass\n\n" for n in range(functions_per_file)),
            encoding="utf-8")


@pytest.fixture
def big_project(tmp_path):
    """A library whose only code folder, big/, has 12 index rows. Every role is filled in, so
    `check` fails only on drift."""
    write_big_source_files(tmp_path / "big")
    git(tmp_path, "init", "-q")
    init(tmp_path)
    _fill_all_roles(tmp_path)
    return tmp_path


def set_max_doc_lines(project, value):
    cfg = read_config(project)
    cfg["maxDocLines"] = value
    write_config(project, cfg)


def resync_with_limit(project, limit):
    set_max_doc_lines(project, limit)
    run(project, "index", "--all")


def folder_snapshot(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def index_layout(folder):
    if (folder / "index").is_dir():
        return "per-file"
    if (folder / "index.md").is_file():
        return "index.md"
    return "inline"


def text_of(path):
    return path.read_text(encoding="utf-8")


def index_link(strings):
    return strings["index_link"].format(index_file=lb.INDEX_FILE_NAME)


def test_index_stays_inline_when_document_fits_the_limit(big_project):
    resync_with_limit(big_project, LEVEL_0_LIMIT)

    big = big_project / "big"
    assert index_layout(big) == "inline"
    assert len(index_rows(big / "CLAUDE.md")) == 12
    assert lb.GENERATED_MARKER not in text_of(big / "CLAUDE.md")


def test_index_moves_to_index_md_when_document_exceeds_the_limit(big_project):
    big = big_project / "big"
    doc = big / "CLAUDE.md"
    doc.write_text(text_of(doc).replace("\nrole\n", "\nRole written by a human.\n"),
                   encoding="utf-8")

    resync_with_limit(big_project, LEVEL_1_LIMIT)

    assert index_layout(big) == "index.md"
    assert index_rows(doc) == [], "the block holds a link, not a table"
    assert f"{lb.INDEX_START}\n{index_link(EN)}\n{lb.INDEX_END}" in text_of(doc)
    assert "Role written by a human." in text_of(doc)
    generated = text_of(big / "index.md")
    assert generated.startswith(f"{lb.GENERATED_MARKER}\n| File | Function | Start | End |\n")
    assert "| a.py | a0 | 1 | 2 |" in generated
    assert len(generated.splitlines()) <= LEVEL_1_LIMIT


def test_index_splits_per_file_when_index_md_exceeds_the_limit(big_project):
    resync_with_limit(big_project, LEVEL_2_LIMIT)

    big = big_project / "big"
    assert index_layout(big) == "per-file"
    assert f"{lb.INDEX_START}\n{index_link(EN)}\n{lb.INDEX_END}" in text_of(big / "CLAUDE.md")
    assert text_of(big / "index.md") == (
        f"{lb.GENERATED_MARKER}\n- [a.py](index/a.py.md)\n- [b.py](index/b.py.md)\n"
        "- [c.py](index/c.py.md)\n")
    per_file = text_of(big / "index/b.py.md")
    assert per_file.startswith(f"{lb.GENERATED_MARKER}\n| File | Function | Start | End |\n")
    assert "| b.py | b3 | 10 | 11 |" in per_file
    assert "a.py" not in per_file
    assert sorted(p.name for p in (big / "index").iterdir()) == ["a.py.md", "b.py.md", "c.py.md"]


@pytest.mark.parametrize("limit", [LEVEL_0_LIMIT, LEVEL_1_LIMIT, LEVEL_2_LIMIT])
def test_second_run_leaves_every_index_level_byte_identical(big_project, limit):
    resync_with_limit(big_project, limit)
    before = folder_snapshot(big_project)

    run(big_project, "index", "--all")
    run(big_project, "index", "--all")

    assert folder_snapshot(big_project) == before
    run(big_project, "check")  # exits 1 when any document or generated file drifted


def test_index_reverts_to_lower_levels_when_the_folder_shrinks(big_project):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_2_LIMIT)
    assert index_layout(big) == "per-file"

    write_big_source_files(big, functions_per_file=1)  # 3 rows: index.md is 6 lines
    run(big_project, "index", "--all")
    assert index_layout(big) == "index.md"
    assert not (big / "index").exists(), "the per-file folder is deleted once empty"
    assert "| a.py | a0 | 1 | 2 |" in text_of(big / "index.md")

    resync_with_limit(big_project, LEVEL_0_LIMIT)
    assert index_layout(big) == "inline"
    assert not (big / "index.md").exists()
    assert len(index_rows(big / "CLAUDE.md")) == 3


def test_index_grows_from_inline_to_per_file_when_the_limit_shrinks(big_project):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_0_LIMIT)
    resync_with_limit(big_project, LEVEL_2_LIMIT)

    assert index_layout(big) == "per-file"
    assert index_rows(big / "CLAUDE.md") == []
    assert (big / "index/a.py.md").is_file()


def test_korean_library_writes_korean_link_and_headings_at_level_2(project):
    write_big_source_files(project / "big")
    init(project, "ko")

    resync_with_limit(project, LEVEL_2_LIMIT)

    big = project / "big"
    assert f"{lb.INDEX_START}\n{index_link(KO)}\n{lb.INDEX_END}" in text_of(big / "CLAUDE.md")
    assert "| 파일 | 함수 | 시작 줄 | 끝 줄 |" in text_of(big / "index/a.py.md")


def test_file_names_with_spaces_are_encoded_in_per_file_links(big_project):
    big = big_project / "big"
    (big / "my mod.py").write_text("def only():\n    pass\n", encoding="utf-8")

    resync_with_limit(big_project, LEVEL_2_LIMIT)

    assert "- [my mod.py](index/my%20mod.py.md)" in text_of(big / "index.md")
    assert (big / "index/my mod.py.md").is_file()


def test_generated_files_are_not_indexed_or_counted_as_folders(big_project):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_2_LIMIT)

    library = lb.load_library(big_project)
    listed = {p.relative_to(big_project).as_posix() for p in lb.list_files(library)}
    assert "big/index.md" not in listed
    assert not any(name.startswith("big/index/") for name in listed)
    assert big / "index" not in lb.managed_dirs(library, lb.list_files(library))
    assert not (big / "index/CLAUDE.md").exists()
    assert "index/" not in text_of(big / "CLAUDE.md").replace("(index.md)", "")
    run(big_project, "check")  # would exit 1 if generated files were indexed and drifted


def test_generated_files_are_excluded_without_git(big_project, monkeypatch):
    resync_with_limit(big_project, LEVEL_2_LIMIT)
    monkeypatch.setattr(lb, "_git", lambda *args, **kwargs: None)

    listed = {p.relative_to(big_project).as_posix() for p in lb.list_files(lb.load_library(big_project))}

    assert "big/a.py" in listed
    assert "big/index.md" not in listed and not any(n.startswith("big/index/") for n in listed)


def test_index_md_written_by_a_human_is_never_overwritten_and_warns(big_project, capsys):
    big = big_project / "big"
    (big / "index.md").write_text("# My own index\n\nhand written\n", encoding="utf-8")
    capsys.readouterr()

    resync_with_limit(big_project, LEVEL_1_LIMIT)

    out = capsys.readouterr().out
    assert text_of(big / "index.md") == "# My own index\n\nhand written\n"
    assert not (big / "index").exists()
    assert len([row for row in index_rows(big / "CLAUDE.md") if row[0] != "index.md"]) == 12
    assert "[warning] big: " in out and "index.md already exists" in out
    run(big_project, "check")  # the stable layout is not drift


def test_human_index_md_is_kept_when_the_layout_would_need_it_at_level_0(big_project, capsys):
    (big_project / "big/index.md").write_text("# My own index\n", encoding="utf-8")
    capsys.readouterr()

    resync_with_limit(big_project, LEVEL_0_LIMIT)

    assert "warning" not in capsys.readouterr().out
    assert text_of(big_project / "big/index.md") == "# My own index\n"


def test_real_source_folder_named_index_is_managed_and_never_used_for_generated_files(
        big_project, capsys):
    big = big_project / "big"
    (big / "index").mkdir()
    (big / "index/core.py").write_text("def core():\n    pass\n", encoding="utf-8")
    capsys.readouterr()

    resync_with_limit(big_project, LEVEL_2_LIMIT)

    out = capsys.readouterr().out
    assert text_of(big / "index/core.py") == "def core():\n    pass\n"
    # the tiny limit also splits the index of the real folder, into its own index.md
    assert sorted(p.name for p in (big / "index").iterdir()) == ["CLAUDE.md", "core.py", "index.md"]
    assert "| core.py | core | 1 | 2 |" in text_of(big / "index/index.md")
    assert "| index/ |" in text_of(big / "CLAUDE.md")
    assert text_of(big / "index.md").startswith(lb.GENERATED_MARKER)
    assert "| a.py | a0 | 1 | 2 |" in text_of(big / "index.md"), "level 1 holds the whole table"
    assert "[warning] big: " in out and "'index' already exists" in out
    _fill_all_roles(big_project)
    run(big_project, "check")


def test_human_file_added_to_generated_index_folder_survives_and_index_falls_back_to_index_md(
        big_project, capsys):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_2_LIMIT)
    (big / "index/notes.txt").write_text("keep me\n", encoding="utf-8")
    capsys.readouterr()

    run(big_project, "index", "--all")

    assert text_of(big / "index/notes.txt") == "keep me\n"
    assert sorted(p.name for p in (big / "index").iterdir()) == ["CLAUDE.md", "notes.txt"]
    assert "| a.py | a0 | 1 | 2 |" in text_of(big / "index.md")
    assert "'index' already exists" in capsys.readouterr().out


@pytest.mark.parametrize("limit", [LEVEL_0_LIMIT, LEVEL_1_LIMIT, LEVEL_2_LIMIT])
def test_parse_failure_keeps_previous_rows_wherever_the_index_lives(big_project, limit):
    big = big_project / "big"
    resync_with_limit(big_project, limit)
    (big / "a.py").write_text("def broken(:\n", encoding="utf-8")

    run(big_project, "index", "--all")

    doc_and_generated = "".join(text_of(p) for p in big.rglob("*.md"))
    assert "| a.py | a3 | 10 | 11 |" in doc_and_generated
    assert "| b.py | b3 | 10 | 11 |" in doc_and_generated


@pytest.mark.parametrize("limit", [LEVEL_1_LIMIT, LEVEL_2_LIMIT])
def test_parse_failure_keeps_previous_inline_rows_when_the_index_moves_in_the_same_run(
        big_project, limit):
    big = big_project / "big"
    (big / "a.py").write_text("def broken(:\n", encoding="utf-8")

    resync_with_limit(big_project, limit)

    assert index_layout(big) != "inline"
    assert "| a.py | a3 | 10 | 11 |" in "".join(text_of(p) for p in big.rglob("*.md"))


def test_parse_failure_does_not_read_rows_from_a_human_index_md(big_project):
    big = big_project / "big"
    (big / "index.md").write_text("| a.py | fake | 1 | 1 |\n", encoding="utf-8")
    (big / "a.py").write_text("def broken(:\n", encoding="utf-8")

    run(big_project, "index", "--all")

    assert "fake" not in text_of(big / "CLAUDE.md")
    assert ("a.py", "a3", "10", "11") in index_rows(big / "CLAUDE.md")


def test_parse_failure_ignores_the_index_md_of_a_real_source_folder_named_index(big_project):
    big = big_project / "big"
    inner = big / "index"
    inner.mkdir()
    (inner / "a.py").write_text(
        "".join(f"def inner{n}():\n    pass\n\n" for n in range(12)), encoding="utf-8")
    resync_with_limit(big_project, LEVEL_1_LIMIT)
    assert lb.GENERATED_MARKER in text_of(big / "index.md"), "big keeps its index at level 1"
    assert lb.GENERATED_MARKER in text_of(inner / "index.md"), "the inner folder splits its own index"
    (big / "a.py").write_text("def broken(:\n", encoding="utf-8")

    run(big_project, "index", "--all")

    assert "| a.py | a3 | 10 | 11 |" in text_of(big / "index.md")
    assert "inner" not in text_of(big / "index.md")


def test_check_reports_a_deleted_generated_file_as_drift_and_fix_restores_it(big_project):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_2_LIMIT)
    (big / "index/a.py.md").unlink()

    with pytest.raises(SystemExit) as failure:
        run(big_project, "check")
    assert failure.value.code == 1
    assert not (big / "index/a.py.md").exists(), "check without --fix writes nothing"

    run(big_project, "check", "--fix")
    assert (big / "index/a.py.md").is_file()


def test_check_without_fix_reports_stale_generated_files_and_deletes_nothing(big_project):
    big = big_project / "big"
    resync_with_limit(big_project, LEVEL_2_LIMIT)
    set_max_doc_lines(big_project, LEVEL_0_LIMIT)

    with pytest.raises(SystemExit):
        run(big_project, "check")

    assert (big / "index.md").is_file() and (big / "index/a.py.md").is_file()


def test_post_edit_hook_splits_the_index_of_the_edited_folder(big_project):
    big = big_project / "big"
    set_max_doc_lines(big_project, LEVEL_2_LIMIT)
    (big / "a.py").write_text("\n" + text_of(big / "a.py"), encoding="utf-8")

    hook("post-edit", {"cwd": str(big_project), "tool_input": {"file_path": str(big / "a.py")}})

    assert index_layout(big) == "per-file"
    assert "| a.py | a0 | 2 | 3 |" in text_of(big / "index/a.py.md")


# ---------------------------------------------------------------- long documents: config, hook, check


@pytest.mark.parametrize("value", ["many", 0, -3, None])
def test_invalid_max_doc_lines_falls_back_to_default(big_project, value):
    set_max_doc_lines(big_project, value)

    assert lb.load_library(big_project).config["maxDocLines"] == 200 == lb.DEFAULT_CONFIG["maxDocLines"]


@pytest.mark.parametrize("value", [50, "50"])
def test_valid_max_doc_lines_is_used(big_project, value):
    set_max_doc_lines(big_project, value)

    assert lb.load_library(big_project).config["maxDocLines"] == 50


def test_update_writes_the_default_max_doc_lines_into_an_old_config(project):
    init(project)
    write_config(project, {"language": "en"})

    run(project, "update")

    assert read_config(project)["maxDocLines"] == 200


def write_rule_file(project, name, line_count):
    path = project / ".claude/rules" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"rule line {n}\n" for n in range(line_count)), encoding="utf-8")
    return path


def write_overlong_rule_file(project, name="long.md"):
    """Write a 25-line rule file and set maxDocLines to 20, so the file is over the limit."""
    write_rule_file(project, name, 25)
    set_max_doc_lines(project, 20)


def session_start_context(project):
    out = hook("session-start", {"cwd": str(project), "hook_event_name": "SessionStart"})
    return additional_context(out, "SessionStart") if out else None


def test_session_start_lists_an_overlong_rule_file_and_points_to_rule_creator(big_project):
    write_overlong_rule_file(big_project, "api/style.md")
    write_rule_file(big_project, "short.md", 3)

    context = session_start_context(big_project)

    assert ".claude/rules/api/style.md (25 lines)" in context
    assert "short.md" not in context
    assert "split a long document" in context
    assert str(lb.RULE_CREATOR_SKILL) in context
    assert "one-line pointer" in context and "do not duplicate" in context
    assert "library language (en)" in context


def test_session_start_counts_only_prose_lines_of_a_folder_document(big_project):
    big_doc = big_project / "big/CLAUDE.md"
    total_lines = len(text_of(big_doc).splitlines())
    assert total_lines == 24 and len(index_rows(big_doc)) == 12  # 16 of them are the index block
    set_max_doc_lines(big_project, 20)  # not re-synced: the index stays inline

    assert session_start_context(big_project) is None

    set_max_doc_lines(big_project, 7)
    assert "big/CLAUDE.md (8 lines)" in session_start_context(big_project)


def test_session_start_reports_all_overlong_documents_in_one_message(big_project):
    write_rule_file(big_project, "one.md", 9)
    write_rule_file(big_project, "two.md", 8)
    set_max_doc_lines(big_project, 7)

    out = hook("session-start", {"cwd": str(big_project)})

    assert out.count("\n") == 1, "exactly one JSON message"
    context = additional_context(out, "SessionStart")
    assert ".claude/rules/one.md (9 lines)" in context
    assert ".claude/rules/two.md (8 lines)" in context
    assert "big/CLAUDE.md (8 lines)" in context


def test_session_start_is_silent_when_every_document_fits(big_project):
    write_rule_file(big_project, "fine.md", 10)

    assert hook("session-start", {"cwd": str(big_project)}) == ""


def test_session_start_is_silent_in_a_project_without_a_library(tmp_path):
    write_rule_file(tmp_path, "long.md", 500)

    assert hook("session-start", {"cwd": str(tmp_path)}) == ""


def test_session_start_skips_an_unreadable_rule_file_and_still_reports_the_others(big_project):
    binary = big_project / ".claude/rules/binary.md"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"\xff\xfe\x00\x81" * 50 + b"\n" * 30)
    write_overlong_rule_file(big_project)

    context = session_start_context(big_project)

    assert ".claude/rules/long.md (25 lines)" in context
    assert "binary.md" not in context


def test_session_start_tolerates_a_folder_document_that_disappears(big_project):
    (big_project / "big/CLAUDE.md").unlink()
    write_overlong_rule_file(big_project)

    assert ".claude/rules/long.md (25 lines)" in session_start_context(big_project)


def test_session_start_command_from_hooks_json_runs_and_reports(big_project):
    write_overlong_rule_file(big_project)
    payload = {"cwd": str(big_project), "hook_event_name": "SessionStart"}

    res = run_hook_command("SessionStart", payload)

    assert hooks_json_entry("SessionStart")["timeout"] == 30
    assert res.returncode == 0, res.stderr.decode("utf-8", "replace")
    context = additional_context(res.stdout.decode("utf-8"), "SessionStart")
    assert ".claude/rules/long.md (25 lines)" in context


def test_check_lists_overlong_documents_as_warnings_without_failing(big_project, capsys):
    write_overlong_rule_file(big_project)
    run(big_project, "index", "--all")
    capsys.readouterr()

    run(big_project, "check")  # long documents are not drift: no SystemExit

    out = capsys.readouterr().out
    assert "[warning] .claude/rules/long.md: 25 lines > maxDocLines 20" in out
    assert "[warning] big/CLAUDE.md" not in out, "its index block is not counted"


def test_check_has_no_long_document_warning_when_everything_fits(big_project, capsys):
    write_rule_file(big_project, "fine.md", 10)
    capsys.readouterr()

    run(big_project, "check")

    assert "maxDocLines" not in capsys.readouterr().out
