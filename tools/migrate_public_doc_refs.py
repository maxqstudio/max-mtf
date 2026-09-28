from __future__ import annotations

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".workflow", ".idea", ".vscode", ".venv", "venv", "node_modules", "dist", "build", "coverage", "vendor", "__pycache__"}
PATH_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".kts",
    ".cs", ".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".rs", ".go",
    ".swift", ".m", ".mm", ".php", ".rb", ".scala", ".sh", ".ps1", ".bat",
    ".cmd", ".sql", ".proto", ".graphql", ".gql", ".xml", ".gradle",
    ".md", ".json", ".yaml", ".yml", ".toml", ".ini",
}
GENERATED_DOCS = {
    "SYSTEM_OVERVIEW.md","PROJECT_MANIFEST.md","CURRENT_STATE.md","SOURCE_AUTHORITY_MAP.md",
    "ARCHITECTURE.md","WORKFLOW_STATE_MACHINE.md","SEQUENCE_CONTRACTS.md","MODULE_MAP.md",
    "SYMBOL_INDEX.md","FLOW_INDEX.md","TEST_ACCEPTANCE_MATRIX.md","DOC_SYNC_MATRIX.md",
    "PROJECT_TRUTH_SYNC.md","API_CONTRACTS.md","DATA_CONTRACTS.md","UI_INFORMATION_ARCHITECTURE.md",
    "RUNBOOK.md","DECISIONS.md","KNOWN_DEFECTS.md","GLOSSARY.md","CHANGELOG.md",
}
INLINE = re.compile(r"`([^`\n]+)`")


def git_files() -> list[str]:
    raw = subprocess.check_output(["git","-C",str(ROOT),"ls-files","-z"])
    return [x.decode("utf-8") for x in raw.split(b"\0") if x]


def likely_path(token: str) -> bool:
    token=token.strip().strip("<>").split("#",1)[0].split("?",1)[0]
    if not token or " " in token:
        return False
    if token.startswith(("http://","https://","mailto:","#","app://")):
        return False
    return Path(token.replace("\\","/")).suffix.lower() in PATH_EXTS


def resolve_local(doc: Path, token: str, tracked: list[str]) -> str | None:
    target=token.strip().strip("<>").split("#",1)[0].split("?",1)[0].replace("\\","/")
    if not target:
        return None
    for candidate in (ROOT/target, doc.parent/target):
        if candidate.exists():
            try:
                return candidate.resolve().relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                return None

    suffix_matches=[p for p in tracked if p==target or p.endswith("/"+target)]
    if len(suffix_matches)==1:
        return suffix_matches[0]
    base=Path(target).name
    base_matches=[p for p in tracked if Path(p).name==base]
    if len(base_matches)==1:
        return base_matches[0]
    return None


def migrate_doc(path: Path, tracked: list[str]) -> tuple[int,int]:
    rel=path.relative_to(ROOT).as_posix()
    if rel.startswith("docs/") and path.name in GENERATED_DOCS:
        return 0,0
    original=path.read_text(encoding="utf-8",errors="replace")
    lines=original.splitlines(keepends=True)
    inside=False
    marker=""
    resolved_count=0
    external_count=0
    out=[]
    for line in lines:
        stripped=line.lstrip()
        if not inside and (stripped.startswith("```") or stripped.startswith("~~~")):
            inside=True; marker=stripped[:3]; out.append(line); continue
        if inside:
            out.append(line)
            if stripped.startswith(marker):
                inside=False; marker=""
            continue

        def repl(match: re.Match[str]) -> str:
            nonlocal resolved_count, external_count
            token=match.group(1)
            if token.startswith("historical external: ") or not likely_path(token):
                return match.group(0)
            local=resolve_local(path,token,tracked)
            if local:
                if local==token.replace("\\","/"):
                    return match.group(0)
                resolved_count+=1
                return "`"+local+"`"
            external_count+=1
            return "`historical external: "+token+"`"

        out.append(INLINE.sub(repl,line))
    updated="".join(out)
    if updated!=original:
        path.write_text(updated,encoding="utf-8",newline="\n")
    return resolved_count,external_count


def main() -> int:
    tracked=git_files()
    total_resolved=0
    total_external=0
    changed=0
    for path in sorted(ROOT.rglob("*.md")):
        rel=path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in rel.parts):
            continue
        before=path.read_bytes()
        resolved,external=migrate_doc(path,tracked)
        if path.read_bytes()!=before:
            changed+=1
        total_resolved+=resolved
        total_external+=external
    print(f"PUBLIC_DOC_REF_MIGRATION=PASS changed_docs={changed} resolved_local={total_resolved} historical_external={total_external}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
