from __future__ import annotations

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = (
    "owner_acceptance/",
    "ModelLab/evidence/",
    "Releases/",
    "artifacts/",
    "history/",
)
FORBIDDEN_EXT = {
    ".ex5", ".onnx", ".zip", ".7z", ".pfx", ".p12", ".pem", ".key",
    ".db", ".sqlite", ".sqlite3", ".pkl", ".joblib", ".npy", ".npz",
    ".pt", ".pth", ".bin", ".dll", ".exe", ".log",
}
TEXT_EXT = {
    ".py", ".ps1", ".md", ".json", ".yaml", ".yml", ".toml", ".ini",
    ".cfg", ".txt", ".mq5", ".mqh", ".js", ".ts", ".tsx", ".jsx",
    ".html", ".css", ".xml",
}
SECRET_PATTERNS = {
    "GITHUB_TOKEN": re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}"),
    "AWS_ACCESS_KEY": re.compile(r"AKIA[0-9A-Z]{16}"),
    "GOOGLE_API_KEY": re.compile(r"AIza[0-9A-Za-z\-_]{20,}"),
    "OPENAI_STYLE_KEY": re.compile(r"sk-[A-Za-z0-9]{20,}"),
    "PRIVATE_KEY_BLOCK": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "PASSWORD_ASSIGNMENT": re.compile(
        r"""(?i)(?<!["'])\b(?:password|passwd|pwd)\b\s*[:=]\s*["'][^"'\r\n]{6,}"""
    ),
    "TOKEN_ASSIGNMENT": re.compile(
        r"""(?i)(?<!["'])\b(?:api[_-]?key|access[_-]?token|secret[_-]?key|auth[_-]?token)\b\s*[:=]\s*["'][^"'\r\n]{8,}"""
    ),
}
OWNER_HOME = re.compile(r"(?i)C:\\Users\\[^<\\\s]+")


def tracked_files() -> list[str]:
    cp = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        check=True,
        stdout=subprocess.PIPE,
    )
    return [part.decode("utf-8") for part in cp.stdout.split(b"\0") if part]


def main() -> int:
    findings: list[str] = []
    files = tracked_files()

    for rel in files:
        normalized = rel.replace("\\", "/")
        if any(normalized.startswith(prefix) for prefix in FORBIDDEN_DIRS):
            findings.append(f"FORBIDDEN_PATH|{rel}")
            continue

        path = ROOT / rel
        suffix = path.suffix.lower()
        if suffix in FORBIDDEN_EXT:
            findings.append(f"FORBIDDEN_EXT|{rel}")
            continue
        if suffix not in TEXT_EXT:
            continue

        text = path.read_text(encoding="utf-8", errors="replace")
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                findings.append(f"SECRET_PATTERN|{rel}|{name}")
        if OWNER_HOME.search(text):
            findings.append(f"OWNER_USER_PATH|{rel}")

    if findings:
        for finding in sorted(set(findings)):
            print(finding)
        print(f"PUBLIC_SOURCE_GUARD=FAIL findings={len(set(findings))}")
        return 1

    print(f"PUBLIC_SOURCE_GUARD=PASS tracked_files={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
