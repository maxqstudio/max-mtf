from __future__ import annotations

from core.project_paths import MODELLAB_ROOT
from acceptance.runners.acceptance_process_env import acceptance_utf8_env, utf8_text_subprocess_kwargs
import ctypes
import hashlib
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, sync_playwright

ROOT = MODELLAB_ROOT
EVIDENCE = ROOT / "runtime_ui_acceptance"
REPORT = EVIDENCE / "RUNTIME_UI_ACCEPTANCE.json"
EVIDENCE_ZIP = EVIDENCE / "UI_RUNTIME_ACCEPTANCE_EVIDENCE.zip"
EXPECTED_STREAMLIT = "1.63.0"
EXPECTED_PLAYWRIGHT = "1.57.0"
SENTINEL = "draft-runtime-persistence-sentinel"


class AcceptanceFailure(RuntimeError):
    pass


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class GateBook:
    def __init__(self) -> None:
        self.gates: list[dict[str, Any]] = []
        self.first_failed_gate: str | None = None

    def gate(self, name: str, ok: bool, detail: Any = "") -> None:
        row = {"gate": name, "status": "PASS" if ok else "FAIL", "detail": detail}
        self.gates.append(row)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
        if not ok:
            if self.first_failed_gate is None:
                self.first_failed_gate = name
            raise AcceptanceFailure(f"{name}: {detail}")


def _free_port(start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"No free port in {start}-{end}")


def _wait_http(url: str, timeout: float = 60.0) -> str:
    end = time.time() + timeout
    last = ""
    while time.time() < end:
        try:
            with urllib.request.urlopen(url, timeout=2.0) as r:
                body = r.read().decode("utf-8", errors="replace")
                if r.status == 200:
                    return body
        except Exception as exc:
            last = str(exc)
        time.sleep(0.35)
    raise RuntimeError(f"HTTP readiness timeout: {url}; last={last}")


def _find_browser() -> Path | None:
    names = ["msedge.exe", "chrome.exe", "chromium.exe", "msedge", "google-chrome", "chromium"]
    for name in names:
        p = shutil.which(name)
        if p:
            return Path(p)
    candidates: list[Path] = []
    if os.name == "nt":
        for base in (os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")):
            if not base:
                continue
            b = Path(base)
            candidates.extend([
                b / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                b / "Google" / "Chrome" / "Application" / "chrome.exe",
            ])
    else:
        candidates.extend([Path("/usr/bin/chromium"), Path("/usr/bin/google-chrome")])
    return next((p for p in candidates if p.exists()), None)


def _screen_size() -> tuple[int, int]:
    if os.name == "nt":
        try:
            user32 = ctypes.windll.user32
            user32.SetProcessDPIAware()
            w = int(user32.GetSystemMetrics(0))
            h = int(user32.GetSystemMetrics(1))
            if w >= 800 and h >= 500:
                return w, h
        except Exception:
            pass
    return 1440, 900


def _rect(page: Page, selector: str) -> dict[str, float] | None:
    box = page.locator(selector).first.bounding_box()
    if box is None:
        return None
    return {
        "x": float(box["x"]),
        "y": float(box["y"]),
        "width": float(box["width"]),
        "height": float(box["height"]),
        "right": float(box["x"] + box["width"]),
        "bottom": float(box["y"] + box["height"]),
    }


def _style_snapshot(page: Page) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const q=s=>document.querySelector(s);
          const style=s=>{const e=q(s); if(!e)return null; const c=getComputedStyle(e); return {
            overflowY:c.overflowY, overflowX:c.overflowX, marginLeft:c.marginLeft,
            marginRight:c.marginRight, position:c.position, transform:c.transform
          };};
          return {
            main:style('section[data-testid="stMain"]'),
            left:style('.st-key-left_nav_panel'),
            scientist:style('.st-key-scientist_chat_drawer'),
            history:style('.st-key-scientist_chat_history'),
            topbar:style('.st-key-scientist_chat_topbar'),
            toolbar:style('.st-key-scientist_chat_config'),
            composer:style('.st-key-scientist_chat_compose')
          };
        }
        """
    ) or {}


def _px(value: str | None) -> float:
    return float(str(value or "0").replace("px", "").strip() or 0)


def _wait_shell(page: Page, timeout_ms: int = 90000) -> None:
    page.locator(".st-key-left_nav_panel").first.wait_for(state="visible", timeout=timeout_ms)
    page.locator(".st-key-scientist_chat_drawer").first.wait_for(state="visible", timeout=timeout_ms)
    page.locator(".cp-top-page").first.wait_for(state="visible", timeout=timeout_ms)
    page.wait_for_timeout(600)


def _run_geometry_view(page: Page, gates: GateBook, label: str, width: int, height: int, screenshot_name: str) -> None:
    _wait_shell(page)
    exception_count = page.locator('[data-testid="stException"]').count()
    gates.gate(f"{label}_no_streamlit_exception", exception_count == 0, {"exceptions": exception_count})

    left = _rect(page, ".st-key-left_nav_panel")
    sci = _rect(page, ".st-key-scientist_chat_drawer")
    history = _rect(page, ".st-key-scientist_chat_history")
    topbar = _rect(page, ".st-key-scientist_chat_topbar")
    composer = _rect(page, ".st-key-scientist_chat_compose")
    styles = _style_snapshot(page)

    slide_over = width <= 900
    phone = width <= 640
    gates.gate(
        f"{label}_left_width",
        bool(left) and 170.0 <= float(left["width"]) <= min(float(width) * 0.90, 255.0),
        left,
    )
    gates.gate(
        f"{label}_scientist_width",
        bool(sci) and (
            (phone and abs(float(sci["width"]) - float(width)) <= 5.0)
            or (not phone and 300.0 <= float(sci["width"]) <= min(float(width) * 0.95, 425.0))
        ),
        sci,
    )
    expected_left = 0.0 if slide_over else float(left["width"] if left else 0.0)
    expected_right = 0.0 if slide_over else float(sci["width"] if sci else 0.0)
    gates.gate(
        f"{label}_center_margins",
        styles.get("main") is not None
        and abs(_px(styles["main"]["marginLeft"]) - expected_left) <= 5.0
        and abs(_px(styles["main"]["marginRight"]) - expected_right) <= 5.0,
        {"main": styles.get("main"), "expected_left": expected_left, "expected_right": expected_right, "slide_over": slide_over},
    )
    gates.gate(
        f"{label}_history_only_scroll",
        styles.get("history", {}).get("overflowY") == "auto"
        and styles.get("scientist", {}).get("overflowY") == "hidden",
        {"history": styles.get("history"), "scientist": styles.get("scientist")},
    )
    gates.gate(
        f"{label}_drawer_fixed_edges",
        bool(sci) and abs(float(sci["y"])) <= 2 and abs(float(sci["bottom"]) - height) <= 5,
        sci,
    )
    gates.gate(
        f"{label}_header_composer_fixed",
        bool(topbar) and bool(composer) and abs(float(topbar["y"])) <= 3 and abs(float(composer["bottom"]) - height) <= 6,
        {"topbar": topbar, "composer": composer},
    )
    gates.gate(
        f"{label}_history_between_fixed_regions",
        bool(history) and bool(topbar) and bool(composer)
        and float(history["y"]) >= float(topbar["bottom"]) - 3
        and float(history["bottom"]) <= float(composer["y"]) + 3,
        {"history": history, "topbar": topbar, "composer": composer},
    )
    page.screenshot(path=str(EVIDENCE / screenshot_name), full_page=False)


def _click_nav(page: Page, name: str) -> None:
    ok = page.evaluate(
        """
        (want) => {
          const labels=[...document.querySelectorAll('.st-key-left_nav_panel label')];
          const e=labels.find(x=>(x.innerText||x.textContent||'').trim()===want);
          if(!e) return false;
          e.click();
          return true;
        }
        """,
        name,
    )
    if not ok:
        raise RuntimeError(f"Navigation label not found: {name}")


def _scientist_toolbar_snapshot(page: Page) -> dict[str, Any]:
    """Inspect Scientist controls using semantic/runtime geometry instead of a single framework-internal selector."""
    return page.evaluate(
        """
        () => {
          const cfg=document.querySelector('.st-key-scientist_chat_config');
          if(!cfg) return {present:false, semanticControlCount:0, modelKey:false, contextKey:false, brightNodes:[]};
          const visible=(e)=>{
            const r=e.getBoundingClientRect(), c=getComputedStyle(e);
            return r.width>2 && r.height>2 && c.display!=='none' && c.visibility!=='hidden' && Number(c.opacity||1)>0;
          };
          const desc=(e)=>{
            const r=e.getBoundingClientRect(), c=getComputedStyle(e);
            return {
              tag:e.tagName,
              role:e.getAttribute('role'),
              testid:e.getAttribute('data-testid'),
              cls:String(e.className||'').slice(0,180),
              text:String(e.innerText||e.textContent||'').trim().slice(0,120),
              value:('value' in e)?String(e.value||'').slice(0,120):'',
              aria:String(e.getAttribute('aria-label')||'').slice(0,120),
              background:c.backgroundColor,
              color:c.color,
              rect:{x:r.x,y:r.y,width:r.width,height:r.height}
            };
          };
          const candidates=[...cfg.querySelectorAll('[data-testid="stSelectbox"],[role="combobox"],input,button')].filter(visible);
          const unique=[];
          for(const e of candidates){
            if(!unique.some(x=>x===e)) unique.push(e);
          }
          const keyModel=document.querySelector('.st-key-scientist_chat_model');
          const keyContext=document.querySelector('.st-key-scientist_chat_context_scope');
          const semantic=unique.filter(e=>
            e.matches('[data-testid="stSelectbox"],[role="combobox"]') ||
            !!e.closest('[data-testid="stSelectbox"]')
          );
          const bright=[];
          for(const e of cfg.querySelectorAll('*')){
            if(!visible(e)) continue;
            const r=e.getBoundingClientRect();
            if(r.width<36 || r.height<18) continue;
            const bg=getComputedStyle(e).backgroundColor||'';
            const m=bg.match(/rgba?\\((\\d+)\\D+(\\d+)\\D+(\\d+)(?:\\D+([\\d.]+))?\\)/);
            if(!m) continue;
            const rr=+m[1], gg=+m[2], bb=+m[3], aa=m[4]===undefined?1:+m[4];
            if(aa>=0.75 && rr>=220 && gg>=220 && bb>=220){
              bright.push(desc(e));
              if(bright.length>=12) break;
            }
          }
          return {
            present:true,
            toolbarText:String(cfg.innerText||cfg.textContent||'').trim(),
            modelKey:!!keyModel && visible(keyModel),
            contextKey:!!keyContext && visible(keyContext),
            semanticControlCount:semantic.length,
            controls:unique.slice(0,20).map(desc),
            brightNodes:bright
          };
        }
        """
    ) or {}


def _run_interactions(page: Page, gates: GateBook, width: int) -> None:
    pages = ["Research", "Data", "Discovery", "Pool", "CPCV", "Tournament", "Monte Carlo", "Forward Championship", "Champion", "Advanced"]
    visible_pages = page.evaluate(
        "[...document.querySelectorAll('.st-key-left_nav_panel label')].map(e=>(e.innerText||e.textContent||'').trim()).filter(Boolean)"
    ) or []
    gates.gate("nav_all_pages_present", all(p in visible_pages for p in pages), {"found": visible_pages})

    lifecycle = page.evaluate(
        """
        () => {
          const labels=[...document.querySelectorAll('button')].map(b=>(b.innerText||b.textContent||'').trim());
          const keys=['START RESEARCH','PAUSE','RESUME','STOP','ABORT'];
          const out={}; for(const k of keys) out[k]=labels.filter(x=>x===k).length; return out;
        }
        """
    ) or {}
    gates.gate("lifecycle_no_duplicate_controls", all(int(v) <= 1 for v in lifecycle.values()), lifecycle)

    toolbar_snapshot = _scientist_toolbar_snapshot(page)
    toolbar_text = str(toolbar_snapshot.get("toolbarText") or "")
    controls_ok = bool(
        (toolbar_snapshot.get("modelKey") and toolbar_snapshot.get("contextKey"))
        or int(toolbar_snapshot.get("semanticControlCount") or 0) >= 2
    )
    gates.gate("scientist_model_context_controls_render", controls_ok, toolbar_snapshot)
    gates.gate(
        "scientist_toolbar_dark_theme",
        len(toolbar_snapshot.get("brightNodes") or []) == 0,
        {"bright_nodes": toolbar_snapshot.get("brightNodes") or [], "controls": toolbar_snapshot.get("controls") or []},
    )

    composer = page.locator('input[placeholder^="Ask about current research"]').first
    gates.gate("scientist_compact_composer_present", composer.count() == 1, {"count": composer.count()})
    composer_input = _rect(page, 'input[placeholder^="Ask about current research"]')
    gates.gate("scientist_composer_compact_height", bool(composer_input) and float(composer_input["height"]) <= 46.0, composer_input)

    init = page.evaluate(
        """
        () => {
          const d=document.querySelector('.st-key-scientist_chat_drawer');
          const l=document.querySelector('.st-key-left_nav_panel');
          const i=document.querySelector('input[placeholder^="Ask about current research"]');
          if(!d||!l||!i) return false;
          d.dataset.runtimeIdentity='scientist-runtime-node';
          l.dataset.runtimeIdentity='left-runtime-node';
          window.__maxScientistNode=d;
          window.__maxLeftNode=l;
          return true;
        }
        """
    )
    gates.gate("interaction_sentinels_initialized", bool(init), init)
    composer.fill(SENTINEL)
    gates.gate("draft_sentinel_entered", composer.input_value() == SENTINEL, composer.input_value())

    for target in ["Data", "Discovery", "Pool", "CPCV"]:
        _click_nav(page, target)
        page.locator(".cp-top-page").filter(has_text=target).first.wait_for(state="visible", timeout=30000)
        page.wait_for_timeout(150)
        same = bool(page.evaluate("window.__maxScientistNode === document.querySelector('.st-key-scientist_chat_drawer')"))
        draft = composer.input_value()
        gates.gate(f"scientist_not_reinitialized_after_{target.replace(' ', '_')}", same, same)
        gates.gate(f"draft_persists_after_{target.replace(' ', '_')}", draft == SENTINEL, draft)

    model_context_after_nav = page.locator(".st-key-scientist_chat_config").first.inner_text()
    gates.gate("model_context_persist_after_navigation", model_context_after_nav == toolbar_text, {"before": toolbar_text, "after": model_context_after_nav})

    page.locator(".st-key-left_nav_hide button").first.click()
    page.wait_for_function("Math.abs(parseFloat(getComputedStyle(document.querySelector('section[data-testid=\"stMain\"]')).marginLeft)) < 1", timeout=15000)
    gates.gate("draft_persists_left_hide", composer.input_value() == SENTINEL, composer.input_value())
    gates.gate("scientist_not_reinitialized_left_hide", bool(page.evaluate("window.__maxScientistNode === document.querySelector('.st-key-scientist_chat_drawer')")), "same DOM node")
    left_hidden = _rect(page, ".st-key-left_nav_panel")
    gates.gate("left_no_reserved_gutter_when_hidden", bool(left_hidden) and float(left_hidden["right"]) <= 3.0, left_hidden)

    page.locator(".st-key-left_nav_restore button").first.click()
    page.wait_for_function(
        """(slide) => { const m=document.querySelector('section[data-testid=\"stMain\"]'); const l=document.querySelector('.st-key-left_nav_panel'); if(!m||!l)return false; const got=parseFloat(getComputedStyle(m).marginLeft)||0; const want=slide?0:l.getBoundingClientRect().width; return Math.abs(got-want)<5; }""",
        arg=(width <= 900), timeout=15000
    )
    gates.gate("left_show_again", True, {"responsive_mode":"slide_over" if width <= 900 else "reflow"})

    page.locator(".st-key-scientist_chat_close_button button").first.click()
    page.wait_for_function("Math.abs(parseFloat(getComputedStyle(document.querySelector('section[data-testid=\"stMain\"]')).marginRight)) < 1", timeout=15000)
    gates.gate("draft_persists_scientist_hide", composer.input_value() == SENTINEL, composer.input_value())
    gates.gate("scientist_dom_stays_mounted_when_hidden", bool(page.evaluate("window.__maxScientistNode === document.querySelector('.st-key-scientist_chat_drawer')")), "same DOM node")
    sci_hidden = _rect(page, ".st-key-scientist_chat_drawer")
    gates.gate("scientist_main_reflow_when_hidden", bool(sci_hidden) and float(sci_hidden["x"]) >= width - 2, sci_hidden)

    page.locator(".st-key-scientist_chat_restore button").first.click()
    page.wait_for_function(
        """(slide) => { const m=document.querySelector('section[data-testid=\"stMain\"]'); const d=document.querySelector('.st-key-scientist_chat_drawer'); if(!m||!d)return false; const got=parseFloat(getComputedStyle(m).marginRight)||0; const want=slide?0:d.getBoundingClientRect().width; return Math.abs(got-want)<5; }""",
        arg=(width <= 900), timeout=15000
    )
    gates.gate("draft_persists_scientist_show_again", composer.input_value() == SENTINEL, composer.input_value())

    injected = page.evaluate(
        """
        () => {
          const h=document.querySelector('.st-key-scientist_chat_history'); if(!h)return false;
          const x=document.createElement('div');
          x.className='st-key-scientist_message_assistant_runtime_fixture'; x.id='runtimeLongBubble';
          x.innerHTML='<div data-testid="stVerticalBlock"><div data-testid="stMarkdownContainer"><p>'+
            ('Scientist runtime acceptance long response with wrapped quantitative evidence. '.repeat(24))+
            '</p><pre>'+('metric=value '.repeat(80))+'</pre></div></div>';
          h.appendChild(x); return true;
        }
        """
    )
    gates.gate("long_reply_fixture_injected", bool(injected), injected)
    bubble = _rect(page, "#runtimeLongBubble")
    drawer = _rect(page, ".st-key-scientist_chat_drawer")
    no_overflow = bool(page.evaluate("document.querySelector('.st-key-scientist_chat_history').scrollWidth <= document.querySelector('.st-key-scientist_chat_history').clientWidth + 2"))
    gates.gate(
        "long_scientist_bubble_contained",
        bool(bubble) and bool(drawer) and float(bubble["x"]) >= float(drawer["x"]) - 1 and float(bubble["right"]) <= float(drawer["right"]) + 1,
        {"bubble": bubble, "drawer": drawer},
    )
    gates.gate("long_scientist_reply_no_horizontal_overflow", no_overflow, no_overflow)


def _prepare_isolated_settings(localapp: Path) -> None:
    root = localapp / "ComplexPolicy" / "ModelLab"
    root.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "CPMF_USER_SETTINGS_V1",
        "config": {
            "agent": {
                "llm": {
                    "enabled": False,
                    "provider": "custom",
                    "base_url": "http://127.0.0.1:9/v1",
                    "model": "acceptance/mock-model",
                    "stack": [],
                }
            }
        },
        "ui_state": {
            "nav_page_v071": "Research",
            "left_nav_open": True,
            "scientist_chat_open": True,
            "scientist_chat_context_scope": "DATA QUALITY",
            "scientist_chat_model": "acceptance/mock-model",
            "scientist_chat_fallback": False,
        },
    }
    (root / "settings.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _package_evidence(files: list[Path]) -> None:
    if EVIDENCE_ZIP.exists():
        EVIDENCE_ZIP.unlink()
    with zipfile.ZipFile(EVIDENCE_ZIP, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.write(REPORT, REPORT.name)
        seen: set[Path] = {REPORT}
        for path in files:
            if path.exists() and path.is_file() and path not in seen and path != EVIDENCE_ZIP:
                z.write(path, path.name)
                seen.add(path)


def _new_page(browser, url: str, width: int, height: int) -> Page:
    context = browser.new_context(viewport={"width": width, "height": height})
    page = context.new_page()
    page.goto(url, wait_until="domcontentloaded", timeout=90000)
    return page


def main() -> int:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    for p in EVIDENCE.iterdir():
        if p.is_file() and p.name not in {"README.md"}:
            try:
                p.unlink()
            except Exception:
                pass

    gates = GateBook()
    started = utcnow()
    server: subprocess.Popen | None = None
    server_log_handle = None
    isolated: Path | None = None
    generated: list[Path] = []
    error = ""
    streamlit_version: str | None = None
    playwright_version: str | None = None
    browser_path: Path | None = None
    owner_size = _screen_size()

    try:
        import importlib.metadata
        from ui.ui_launcher import ensure_env, venv_python, _pip_env

        playwright_version = importlib.metadata.version("playwright")
        gates.gate("playwright_exact_acceptance_version", playwright_version == EXPECTED_PLAYWRIGHT, {"actual": playwright_version, "expected": EXPECTED_PLAYWRIGHT})

        ensure_env()
        py = str(venv_python())
        streamlit_version = subprocess.check_output([py, "-c", "import streamlit; print(streamlit.__version__)"], cwd=ROOT, env=acceptance_utf8_env(), text=True, **utf8_text_subprocess_kwargs()).strip()
        gates.gate("streamlit_exact_version", streamlit_version == EXPECTED_STREAMLIT, {"actual": streamlit_version, "expected": EXPECTED_STREAMLIT})

        browser_path = _find_browser()
        gates.gate("browser_runtime_available", browser_path is not None, str(browser_path) if browser_path else "Edge/Chrome/Chromium not found")

        isolated = Path(tempfile.mkdtemp(prefix="max-ui-runtime-acceptance-"))
        localapp = isolated / "LocalAppData"
        _prepare_isolated_settings(localapp)
        port = _free_port(8561, 8599)
        server_log = EVIDENCE / "streamlit_server.log"
        server_log_handle = server_log.open("wb")
        generated.append(server_log)
        env = acceptance_utf8_env(_pip_env())
        env["LOCALAPPDATA"] = str(localapp)
        env["MAX_UI_RUNTIME_ACCEPTANCE"] = "1"
        cmd = [
            py, "-m", "streamlit", "run", str(ROOT / "ui/app.py"),
            "--server.address=127.0.0.1",
            f"--server.port={port}",
            "--server.headless=true",
            "--server.fileWatcherType=none",
            "--browser.gatherUsageStats=false",
        ]
        server = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=server_log_handle, stderr=subprocess.STDOUT)
        health = _wait_http(f"http://127.0.0.1:{port}/_stcore/health", timeout=90)
        gates.gate("streamlit_server_health", "ok" in health.lower(), health.strip()[:120])
        url = f"http://127.0.0.1:{port}"

        launch_args = ["--disable-background-networking"]
        if os.name != "nt":
            launch_args.append("--no-sandbox")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, executable_path=str(browser_path), args=launch_args)
            try:
                matrix=[
                    (1920,1080,"desktop_1920x1080"),
                    (1440,900,"desktop_1440x900"),
                    (1280,720,"compact_1280x720"),
                    (1024,768,"compact_1024x768"),
                    (768,1024,"tablet_768x1024"),
                    (430,932,"phone_430x932"),
                    (390,844,"phone_390x844"),
                ]
                covered=set()
                for vw,vh,label in matrix:
                    page=_new_page(browser,url,vw,vh)
                    try:
                        name=f"{label}.png"
                        _run_geometry_view(page,gates,label,vw,vh,name)
                        if (vw,vh)==(1440,900):
                            dom_before=EVIDENCE/"desktop_1440x900_before_interactions.html"
                            dom_before.write_text(page.content(),encoding="utf-8")
                            generated.append(dom_before)
                            toolbar_debug=EVIDENCE/"scientist_toolbar_dom_debug.json"
                            toolbar_debug.write_text(json.dumps(_scientist_toolbar_snapshot(page),indent=2),encoding="utf-8")
                            generated.append(toolbar_debug)
                            _run_interactions(page,gates,vw)
                            page.screenshot(path=str(EVIDENCE/"desktop_1440x900_after_interactions.png"),full_page=False)
                            generated.append(EVIDENCE/"desktop_1440x900_after_interactions.png")
                        generated.append(EVIDENCE/name); covered.add((vw,vh))
                    finally:
                        page.context.close()

                ow,oh=owner_size
                if (ow,oh) not in covered:
                    page=_new_page(browser,url,ow,oh)
                    try:
                        _run_geometry_view(page,gates,f"owner_{ow}x{oh}",ow,oh,f"owner_{ow}x{oh}.png")
                        generated.append(EVIDENCE/f"owner_{ow}x{oh}.png")
                        gates.gate("owner_exact_resolution_render",True,{"resolution":f"{ow}x{oh}","dedicated_view":True})
                    finally:
                        page.context.close()
                else:
                    gates.gate("owner_exact_resolution_render",True,{"resolution":f"{ow}x{oh}","covered_by_matrix":True})
            finally:
                browser.close()

    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        print(f"[ERROR] {error}", flush=True)
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=5)
            except Exception:
                try:
                    server.kill()
                except Exception:
                    pass
        if server_log_handle:
            try:
                server_log_handle.close()
            except Exception:
                pass
        if isolated is not None:
            shutil.rmtree(isolated, ignore_errors=True)

    overall = "PASS" if not error and gates.first_failed_gate is None else "FAIL"
    report = {
        "schema": "MAX_UI_RUNTIME_ACCEPTANCE_V4_ADAPTIVE_DOM",
        "evidence_class": "REAL_STREAMLIT_1_63_BROWSER_RENDER",
        "generated_utc": utcnow(),
        "started_utc": started,
        "overall_status": overall,
        "first_failed_gate": gates.first_failed_gate,
        "error": error or None,
        "streamlit_version": streamlit_version,
        "playwright_version": playwright_version,
        "browser": str(browser_path) if browser_path else None,
        "owner_primary_screen": {"width": owner_size[0], "height": owner_size[1]},
        "scientific_authority": "v0.7.6",
        "research_mutation_performed": False,
        "external_calls_performed": False,
        "settings_mode": "ISOLATED_TEMP_LOCALAPPDATA_WITH_NON_SENDING_CHAT_MODEL_FIXTURE",
        "source_app_sha256": sha256(ROOT / "ui/app.py"),
        "gates": gates.gates,
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    generated.append(REPORT)
    try:
        _package_evidence(generated)
    except Exception as exc:
        print(f"[WARN] Could not create evidence ZIP: {exc}", flush=True)

    print(json.dumps({
        "overall_status": overall,
        "gate_count": len(gates.gates),
        "first_failed_gate": gates.first_failed_gate,
        "report": str(REPORT),
        "evidence_zip": str(EVIDENCE_ZIP),
    }, indent=2), flush=True)
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
