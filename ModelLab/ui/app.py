from __future__ import annotations
from core.project_paths import MODELLAB_ROOT
import json
import csv
import copy
import hashlib
import html
import math
import os
import shutil
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

APP_DIR = MODELLAB_ROOT
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from models.model_lab import load_cfg, run_pipeline
from factory.supervisor_agent import run_supervisor_agent, run_post_locked_policy_discovery, validate_frozen_policy_on_fresh_data, validate_frozen_model_on_fresh_data
from scientist.core.scientist import LLMScientist
from scientist.chat.scientist_chat import ScientistChatStore, available_chat_models, available_chat_fallback_models, build_read_only_context, build_research_settings_snapshot, chat_model_profile, discuss as scientist_chat_discuss
from host.provider_catalog import PROVIDERS, provider_labels, provider_key_from_label, list_models, normalize_base_url, estimate_token_count
from scientist.chat.scientist_chat_component import render_scientist_chat_component
from scientist.chat.scientist_chat_jobs import start_job as start_scientist_chat_job, load_job as load_scientist_chat_job, cancel_job as cancel_scientist_chat_job, cleanup_job_files as cleanup_scientist_chat_job_files
from research.risk_kpi import ensure_risk_kpi_config
from scientist.core.llm_health import health_snapshot
from host.hardware_profile import collect_hardware_profile, summarize_hardware_profile
from research.creativity_governor import adaptive_creativity_profile
from research.research_architect import capability_catalog, recommended_parameter_envelopes
from models.model_size_advisor import build_advisor as build_model_size_advisor, current_family_resolution
from models.model_inspector import candidate_detail as resolve_model_detail, parameter_groups as model_parameter_groups
from models.model_registry import registry_for_scientist, hybrid_parts, family_spec, enabled_families, clamp_size_priority, all_families, get_bounds
from research.research_control import research_mode as get_research_mode, manual_cfg as get_manual_research_cfg, default_manual_candidate, compile_manual_runtime
from core.training_method_contract import training_method_context
from factory.governance import load_registry, load_evidence, save_evidence, assess_promotion, promote
from factory.challenger_registry import load_challenger_registry, publish_challenger_to_terminal
from strategy.strategy_challenger_registry import ensure_strategy_registry, load_strategy_registry, promote_strategy_challenger, delete_strategy_challenger
from research.kpi import shadow_acceptance, shadow_recovery_factor, walk_forward_acceptance, locked_test_acceptance
from host.preflight import default_mt5_training_csv, detect_terminal_files_dirs, quick_summary, label_summary, list_runs, load_manifest, period_label
from host.workflow_router import route_for_manifest, route_steps
from data.feature_label_audit import run_feature_label_audit
from research.guided_research import run_guided_research
from data.dataset_integrity import integrity_summary, repair_legacy_duplicates, available_date_range, research_window_preview, build_research_window_snapshot, fresh_readiness, read_csv_auto, writer_lock
from data.data_quality import audit_dataset, research_readiness, llm_data_quality_context, SCHEMA as DATA_QUALITY_SCHEMA
from host.mt5_gap_repair import build_gap_fill_plan, discover_mt5_gap_fill_targets, matching_mt5_gap_fill_targets, launch_gap_fill_tester, run_gap_repair_cycle
from core.settings_store import UserSettingsStore, is_persistable_ui_key, merge_persisted_ui_state
from research.research_memory import build_research_memory
from research.sample_policy import auto_trade_sample
from research.gate_kpi import ensure_gate_kpi_profiles, gate_profile
from factory.champion_factory import run_discovery_pool, run_cpcv_qualification, run_tournament, run_monte_carlo, run_forward_championship
from host.compute_backend import resolve_compute_plan, compact_compute_status
from factory.factory_jobs import start_job as start_factory_job, latest_job as latest_factory_job, load_job as load_factory_job, read_candidates as read_factory_candidates, read_events as read_factory_events, request_stop as request_factory_stop, request_pause as request_factory_pause, force_stop as force_factory_stop, abort_job as abort_factory_job, resume_job as resume_factory_job, failed_recovery_contract as factory_failed_recovery_contract, job_is_resumable as factory_job_is_resumable, ACTIVE_STATUSES as FACTORY_ACTIVE_STATUSES, RESUMABLE_STATUSES as FACTORY_RESUMABLE_STATUSES
from core.inherited_v147 import provisional_cpcv_summary
from strategy.strategy_optimizer import discover_mt5_installations, EA_SOURCE, canonical_ea_identity, DEFAULT_SPACE, optimizer_trade_sample, optimizer_kpi_policy, search_space_cardinality, sanitize_scientist_llm_config
from strategy.strategy_optimizer_jobs import start_job as start_strategy_optimizer_job, latest_job as latest_strategy_optimizer_job, cancel_job as cancel_strategy_optimizer_job, resume_job as resume_strategy_optimizer_job, ACTIVE as STRATEGY_OPTIMIZER_ACTIVE, RECOVERABLE as STRATEGY_OPTIMIZER_RECOVERABLE

st.set_page_config(page_title="Max MTF · v2.0.1", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

def _streamlit_version_tuple() -> tuple[int, int, int]:
    parts=[]
    for raw in str(getattr(st, "__version__", "0.0.0")).split(".")[:3]:
        digits="".join(ch for ch in raw if ch.isdigit())
        parts.append(int(digits or 0))
    while len(parts)<3:
        parts.append(0)
    return tuple(parts[:3])

if _streamlit_version_tuple() < (1, 63, 0):
    st.error("This UI shell requires Streamlit 1.63.0 or newer. Run `pip install -r requirements-ui.txt`.")
    st.stop()
st.markdown("""
<style>
:root{
  --cp-bg:#07111f;--cp-surface:#0b1625;--cp-surface-2:#101d2f;--cp-surface-3:#15253a;
  --cp-border:#263a53;--cp-border-soft:#192b40;--cp-text:#f7f9fc;--cp-text-2:#d3dbe7;--cp-muted:#9aaac0;
  --cp-blue:#5aaeff;--cp-green:#56d693;--cp-amber:#f2b661;--cp-red:#ff7676;--cp-violet:#a78bfa;
  --cp-radius:12px;--cp-shadow:0 8px 26px rgba(0,0,0,.16);--cp-shell-h:54px;--cp-nav-h:48px;
}
html,body,[data-testid="stAppViewContainer"],.stApp{background:var(--cp-bg)!important;color:var(--cp-text)!important;}
[data-testid="stHeader"]{height:0!important;min-height:0!important;background:transparent!important;border:0!important;overflow:visible!important;}
[data-testid="stToolbar"],#MainMenu,footer{display:none!important;}
/* typography */
h1,h2,h3,h4,h5{color:var(--cp-text)!important;letter-spacing:-.018em} h1{font-size:1.72rem!important} h2{font-size:1.35rem!important} h3{font-size:1.12rem!important} h4{font-size:.98rem!important}
p,li,label,[data-testid="stMarkdownContainer"]{color:var(--cp-text-2)}
small,.stCaption,[data-testid="stCaptionContainer"]{color:var(--cp-muted)!important}
hr{border-color:var(--cp-border-soft)!important}

/* sticky app shell */
.cp-appbar{position:sticky;top:0;z-index:1002;display:flex;align-items:center;justify-content:space-between;gap:1rem;height:var(--cp-shell-h);padding:.45rem .8rem;margin:0 0 .35rem;background:rgba(8,18,32,.96);backdrop-filter:blur(16px);border:1px solid var(--cp-border-soft);border-radius:0 0 12px 12px;box-shadow:0 10px 28px rgba(0,0,0,.18)}
.cp-brand{display:flex;align-items:center;gap:.68rem;min-width:0}.cp-brand-mark{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:linear-gradient(145deg,#2d7bdc,#61b6ff);color:white;font-size:.78rem;font-weight:950;box-shadow:0 6px 18px rgba(47,126,230,.25)}
.cp-brand-title{font-size:.98rem;font-weight:850;line-height:1.08;color:var(--cp-text)}.cp-brand-sub{font-size:.68rem;color:var(--cp-muted);margin-top:.08rem}.cp-shell-badges{display:flex;gap:.35rem;flex-wrap:wrap;justify-content:flex-end}
.cp-badge,.cp-chip{display:inline-flex;align-items:center;gap:.25rem;padding:.2rem .5rem;border-radius:999px;border:1px solid var(--cp-border);font-size:.66rem;font-weight:780;color:var(--cp-text-2);background:var(--cp-surface-2);white-space:nowrap}.cp-chip.blue{color:#b8dcff;border-color:#315f92;background:#10294a}.cp-chip.green{color:#a8eec3;border-color:#2c6548;background:#0f3024}.cp-chip.amber{color:#ffd49a;border-color:#77552b;background:#34250f}.cp-chip.red{color:#ffb8b8;border-color:#743b42;background:#33171d}.cp-chip.violet{color:#d7c9ff;border-color:#5a4787;background:#211a35}

/* page hierarchy */
.cp-page-head{display:flex;justify-content:space-between;align-items:flex-end;gap:1rem;margin:.55rem 0 .55rem;padding:.08rem .02rem .55rem;border-bottom:1px solid var(--cp-border-soft)}
.cp-page-kicker{font-size:.63rem;color:var(--cp-blue);font-weight:850;letter-spacing:.105em;text-transform:uppercase;margin-bottom:.14rem}.cp-page-title{font-size:1.38rem;line-height:1.12;font-weight:900;color:var(--cp-text);letter-spacing:-.025em}.cp-page-meta{font-size:.72rem;color:var(--cp-muted);text-align:right}
.cp-section-head{display:flex;align-items:center;justify-content:space-between;gap:.7rem;margin:.72rem 0 .4rem}.cp-section-title{font-size:.98rem;font-weight:850;color:var(--cp-text)}.cp-section-meta{font-size:.68rem;color:var(--cp-muted)}
.cp-subtle{font-size:.72rem;color:var(--cp-muted);line-height:1.4}

/* low-noise surfaces: cards are reserved for major conceptual groups. */
[data-testid="stVerticalBlockBorderWrapper"]{background:var(--cp-surface)!important;border:1px solid var(--cp-border-soft)!important;border-radius:var(--cp-radius)!important;box-shadow:none!important}
[data-testid="stVerticalBlockBorderWrapper"]>[data-testid="stVerticalBlock"]{padding:1rem 1.05rem!important}
.cp-panel,.cp-card{border:1px solid var(--cp-border-soft);border-radius:var(--cp-radius);padding:1rem 1.05rem;background:var(--cp-surface);margin:.3rem 0 .78rem}
.cp-command-strip{border:1px solid var(--cp-border);background:linear-gradient(90deg,#0f2035,#0c1929);border-radius:11px;padding:.68rem .8rem}
.cp-activity{display:flex;align-items:flex-start;gap:.6rem;border-left:3px solid var(--cp-blue);background:#0c1a2b;padding:.68rem .78rem;border-radius:8px;font-size:.78rem;color:var(--cp-text-2);margin:.3rem 0 .65rem;line-height:1.42}.cp-activity strong{color:var(--cp-text);white-space:nowrap}
.cp-live-status{display:flex;align-items:center;gap:.58rem;padding:.18rem 0 .46rem;margin:.05rem 0 .28rem;border:0;border-bottom:1px solid var(--cp-border-soft);background:transparent;color:var(--cp-text-2);font-size:.76rem;line-height:1.38}.cp-live-status strong{color:var(--cp-text);font-weight:860}.cp-live-status .cp-live-meta{color:var(--cp-muted);font-size:.67rem}.cp-live-status .cp-busy-spinner{flex:0 0 auto}
.cp-inline-meta{display:flex;gap:.45rem;flex-wrap:wrap;align-items:center;font-size:.7rem;color:var(--cp-muted);margin:.25rem 0 .55rem}
.cp-subsection{margin:.92rem 0 .48rem;padding-top:.78rem;border-top:1px solid var(--cp-border-soft)}
.cp-subsection.first{margin-top:.1rem;padding-top:0;border-top:0}.cp-inline-kicker{margin:.55rem 0 .28rem;font-size:.68rem;font-weight:800;color:var(--cp-text-2);letter-spacing:.02em}.cp-subsection-title{font-size:.82rem;font-weight:840;color:var(--cp-text)}.cp-subsection-note{font-size:.66rem;color:var(--cp-muted);margin-top:.1rem;line-height:1.38}
.cp-policy-intro{display:flex;align-items:baseline;justify-content:space-between;gap:.8rem;flex-wrap:wrap;margin:.1rem 0 .42rem;padding:.08rem 0 .46rem;border-bottom:1px solid var(--cp-border-soft)}
.cp-policy-title{font-size:.92rem;font-weight:880;color:var(--cp-text)}.cp-policy-note{font-size:.64rem;color:var(--cp-muted)}
.cp-policy-info{font-size:.69rem;line-height:1.45;color:var(--cp-muted);padding:.18rem 0 .5rem;max-width:78rem}
.st-key-advanced_policy_group{margin:0 0 .45rem!important}.st-key-advanced_policy_group div[role="radiogroup"]{display:flex!important;flex-wrap:wrap!important;gap:.3rem!important;padding:0!important}.st-key-advanced_policy_group div[role="radiogroup"] label{border:1px solid var(--cp-border-soft)!important;border-radius:8px!important;background:#0b1727!important;padding:.32rem .52rem!important;margin:0!important}.st-key-advanced_policy_group div[role="radiogroup"] label:has(input:checked){background:#173354!important;border-color:#315f92!important}.st-key-advanced_policy_group div[role="radiogroup"] label p{font-size:.68rem!important;font-weight:760!important}
.cp-fact-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:.25rem 1rem;margin:.48rem 0 .2rem}.cp-fact{min-width:0;padding:.18rem 0}.cp-fact-label{font-size:.58rem;color:var(--cp-muted);font-weight:820;letter-spacing:.06em;text-transform:uppercase}.cp-fact-value{font-size:.94rem;color:var(--cp-text);font-weight:850;margin-top:.13rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cp-fact.wide{grid-column:span 2}
.cp-info-line{display:flex;align-items:center;justify-content:space-between;gap:.7rem;flex-wrap:wrap;padding:.5rem 0;border-top:1px solid var(--cp-border-soft);font-size:.72rem;color:var(--cp-muted)}

/* metrics: values stay visible, but micro-cards no longer compete with the parent grouping. */
[data-testid="stMetric"]{background:transparent!important;border:0!important;border-radius:0!important;padding:.2rem .18rem!important;min-height:64px;box-shadow:none!important}
[data-testid="stMetricLabel"]{font-size:.61rem!important;color:#a8b7ca!important;font-weight:820!important;text-transform:uppercase!important;letter-spacing:.055em!important}
[data-testid="stMetricValue"]{font-size:1.08rem!important;color:var(--cp-text)!important;font-weight:880!important;line-height:1.16!important}[data-testid="stMetricDelta"]{font-size:.66rem!important}

/* scientist */
.cp-scientist-round{font-size:.62rem;color:var(--cp-blue);font-weight:860;letter-spacing:.07em;text-transform:uppercase;margin:.18rem 0 .35rem}.cp-scientist-compact{border:1px solid var(--cp-border-soft);background:#0d1a2b;border-radius:10px;padding:.68rem .78rem;margin:.25rem 0 .55rem}.cp-scientist-compact-head{display:flex;align-items:center;justify-content:space-between;gap:.5rem;flex-wrap:wrap}.cp-scientist-model{font-size:.82rem;font-weight:820;color:var(--cp-text)}.cp-scientist-meta{font-size:.68rem;color:var(--cp-muted)}
.cp-summary-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.55rem;margin-top:.55rem}.cp-summary-cell{border-top:1px solid var(--cp-border-soft);padding-top:.48rem}.cp-summary-label{font-size:.6rem;font-weight:850;letter-spacing:.065em;text-transform:uppercase;color:var(--cp-muted);margin-bottom:.2rem}.cp-summary-body{font-size:.77rem;line-height:1.42;color:var(--cp-text-2)}
.cp-insight-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.6rem;margin:.4rem 0 .55rem}.cp-method-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.6rem;margin:.4rem 0}.cp-method-grid .wide{grid-column:1/-1}.cp-insight-card{border:1px solid var(--cp-border-soft);border-radius:10px;background:#0e1b2d;padding:.68rem .74rem;min-height:100%}.cp-insight-card .label{font-size:.6rem;font-weight:900;letter-spacing:.07em;text-transform:uppercase;color:#a6b5c8;margin-bottom:.24rem}.cp-insight-card .body{font-size:.77rem;line-height:1.43;color:var(--cp-text-2)}
@media(max-width:980px){.cp-summary-grid,.cp-insight-grid{grid-template-columns:1fr}.cp-method-grid{grid-template-columns:1fr}.cp-method-grid .wide{grid-column:auto}}

/* controls/forms */
div.stButton>button,[data-testid="stBaseButton-primary"],[data-testid="stBaseButton-secondary"]{border-radius:9px!important;min-height:2.25rem!important;font-weight:780!important;border:1px solid var(--cp-border)!important;background:var(--cp-surface-2)!important;color:var(--cp-text)!important;box-shadow:none!important} div.stButton>button:hover{border-color:#4775a9!important;background:#172a44!important;color:#fff!important}
[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,[data-baseweb="select"]>div,[data-testid="stDateInput"] input,textarea{background:#0b1727!important;border-color:var(--cp-border)!important;color:var(--cp-text)!important;border-radius:9px!important}
[data-testid="stToggle"] label p,[data-testid="stCheckbox"] label p{color:var(--cp-text-2)!important}

/* expanders/tabs/tables */
[data-testid="stExpander"]{border:1px solid var(--cp-border-soft)!important;border-radius:10px!important;background:#0a1625!important;overflow:hidden;margin:.22rem 0!important}[data-testid="stExpander"] summary{padding:.5rem .7rem!important;color:var(--cp-text-2)!important;font-weight:760!important}[data-testid="stExpander"] summary:hover{background:var(--cp-surface-2)!important}
/* Nested disclosures are semantic detail rows, not cards-in-cards. */
[data-testid="stExpander"] [data-testid="stExpander"]{border:0!important;border-top:1px solid var(--cp-border-soft)!important;border-radius:0!important;background:transparent!important;margin:.55rem 0 0!important;box-shadow:none!important}
[data-testid="stExpander"] [data-testid="stExpander"] summary{padding:.48rem .1rem!important;background:transparent!important}
[data-testid="stExpander"] [data-testid="stExpander"] summary:hover{background:transparent!important}
[data-baseweb="tab-list"]{gap:.2rem;background:#0a1625;padding:.25rem;border:1px solid var(--cp-border-soft);border-radius:9px}[data-baseweb="tab"]{font-size:.74rem!important;padding:.4rem .62rem!important}
[data-testid="stDataFrame"], [data-testid="stTable"]{border:1px solid var(--cp-border-soft)!important;border-radius:10px!important;overflow:hidden}
/* v1.4.4: center compact advisor popovers/tooltips for symmetric readout. */
div[data-baseweb="popover"] [data-testid="stMarkdownContainer"],div[data-baseweb="popover"] [data-testid="stCaptionContainer"]{text-align:center!important}
div[data-baseweb="popover"] [data-testid="stDataFrame"]{margin-left:auto!important;margin-right:auto!important}

/* alerts use semantic accent but stay restrained */
[data-testid="stAlert"]{border-radius:10px!important;border-width:1px!important;padding:.62rem .72rem!important}[data-testid="stAlert"] p{font-size:.78rem!important;line-height:1.42!important}

.cp-busy-row{display:flex;align-items:flex-start;gap:.48rem;min-height:34px;padding:.42rem .46rem;margin:0 0 .42rem;border:1px solid var(--cp-border-soft);border-radius:8px;background:#0c1929;color:#aebed0;font-size:.66rem;font-weight:720;line-height:1.28;white-space:normal;overflow:visible;}
.cp-busy-row>span:nth-child(2){min-width:0;flex:1;overflow-wrap:anywhere;}.cp-busy-row .cp-busy-spinner{margin-top:1px}.cp-busy-row .cp-busy-pulse{margin-top:4px;flex:0 0 auto;}
.cp-lifecycle-error{margin:0 0 .42rem;padding:.42rem .5rem;border:1px solid #593239;border-radius:8px;background:#211319;color:#ffb9c3;font-size:.66rem;font-weight:700;line-height:1.32;overflow-wrap:anywhere;}
.cp-busy-spinner{width:13px;height:13px;border-radius:50%;border:2px solid #304963;border-top-color:var(--cp-blue);animation:cp-spin .72s linear infinite;flex:0 0 auto;}
.cp-busy-pulse{display:inline-flex;gap:3px;margin-left:auto}.cp-busy-pulse i{width:4px;height:4px;border-radius:50%;background:#79b8f2;animation:cp-pulse 1s ease-in-out infinite}.cp-busy-pulse i:nth-child(2){animation-delay:.14s}.cp-busy-pulse i:nth-child(3){animation-delay:.28s}
@keyframes cp-spin{to{transform:rotate(360deg)}}@keyframes cp-pulse{0%,70%,100%{opacity:.25;transform:translateY(0)}35%{opacity:1;transform:translateY(-2px)}}

/* dense but readable page rhythm */
[data-testid="stVerticalBlock"]{gap:.52rem!important}.element-container{margin-bottom:0!important}
@media(max-width:760px){.cp-brand-sub,.cp-shell-badges{display:none}.cp-appbar{height:48px}.cp-page-title{font-size:1.22rem}.block-container{padding-top:.25rem!important}}

.cp-side-brand{padding:.68rem .62rem .8rem;margin:.1rem 0 .6rem;border-bottom:1px solid var(--cp-border-soft)}
.cp-side-logo{display:flex;align-items:center;gap:.62rem}.cp-side-mark{width:32px;height:32px;border-radius:9px;display:grid;place-items:center;background:linear-gradient(145deg,#2d7bdc,#61b6ff);font-weight:950;color:white}.cp-side-name{font-size:.92rem;font-weight:900;color:var(--cp-text)}.cp-side-ver{font-size:.62rem;color:var(--cp-muted);margin-top:.08rem}

.cp-appbar{top:.2rem;margin:.05rem 0 .55rem;height:50px;border-radius:10px;}
.cp-top-page{font-size:.88rem;font-weight:860;color:var(--cp-text)}.cp-top-context{font-size:.64rem;color:var(--cp-muted);margin-top:.08rem}
.cp-top-left{display:flex;align-items:center;gap:.7rem;min-width:0}.cp-top-dot{width:8px;height:8px;border-radius:50%;background:var(--cp-blue);box-shadow:0 0 0 4px rgba(90,174,255,.12)}

/* compact dashboard metrics: one information band, not four competing cards. */
.cp-stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0;margin:.4rem 0 .72rem;border:1px solid var(--cp-border-soft);border-radius:10px;background:#0c1929;overflow:hidden}.cp-stat{background:transparent;border:0;border-left:1px solid var(--cp-border-soft);border-radius:0;padding:.72rem .82rem;min-height:74px}.cp-stat:first-child{border-left:0}.cp-stat-label{font-size:.58rem;font-weight:850;letter-spacing:.06em;text-transform:uppercase;color:#9fb0c5}.cp-stat-value{font-size:1.14rem;font-weight:900;color:var(--cp-text);margin-top:.2rem;line-height:1.1}.cp-stat-note{font-size:.62rem;color:var(--cp-muted);margin-top:.17rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cp-data-surface{border:1px solid var(--cp-border-soft);background:#0a1625;border-radius:11px;padding:.82rem .88rem;margin:.35rem 0 .72rem}.cp-data-head{display:flex;align-items:center;justify-content:space-between;gap:.6rem;margin-bottom:.5rem}.cp-data-title{font-size:.88rem;font-weight:860;color:var(--cp-text)}.cp-data-meta{font-size:.65rem;color:var(--cp-muted)}
.cp-health-strip{display:flex;align-items:center;justify-content:space-between;gap:.7rem;flex-wrap:wrap;border:1px solid #3b4b61;background:#0c1928;border-radius:9px;padding:.65rem .75rem;margin:.38rem 0 .65rem}.cp-health-main{font-size:.74rem;font-weight:800;color:var(--cp-text)}.cp-health-meta{font-size:.65rem;color:var(--cp-muted);margin-top:.08rem}
.st-key-llm_connect_models button{min-height:2.45rem!important;max-width:180px!important;margin-left:auto!important;margin-top:1.75rem!important}
@media(max-width:760px){.st-key-llm_connect_models button{margin-top:0!important;max-width:none!important}}
@media(max-width:980px){.cp-stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.cp-stat:nth-child(3){border-left:0;border-top:1px solid var(--cp-border-soft)}.cp-stat:nth-child(4){border-top:1px solid var(--cp-border-soft)}.cp-fact-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:680px){.cp-stat-grid{grid-template-columns:1fr}.cp-stat{border-left:0!important;border-top:1px solid var(--cp-border-soft)}.cp-stat:first-child{border-top:0}.cp-fact-grid{grid-template-columns:1fr}}
</style>
""", unsafe_allow_html=True)


def _page_header(title: str, kicker: str = "Workspace", meta: str = ""):
    safe_title=html.escape(str(title))
    safe_kicker=html.escape(str(kicker))
    safe_meta=html.escape(str(meta))
    meta_html=f'<div class="cp-page-meta">{safe_meta}</div>' if safe_meta else ''
    st.markdown(
        f'<div class="cp-page-head"><div><div class="cp-page-kicker">{safe_kicker}</div>'
        f'<div class="cp-page-title">{safe_title}</div></div>{meta_html}</div>',
        unsafe_allow_html=True,
    )

def _compact_note(text: str):
    if text:
        st.markdown(f'<div class="cp-subtle">{html.escape(str(text))}</div>',unsafe_allow_html=True)

def _section_header(title: str, meta: str = ""):
    st.markdown(
        f'<div class="cp-section-head"><div class="cp-section-title">{html.escape(str(title))}</div>'
        f'<div class="cp-section-meta">{html.escape(str(meta))}</div></div>',
        unsafe_allow_html=True,
    )


def _subsection_header(title: str, note: str = "", *, first: bool=False):
    cls="cp-subsection first" if first else "cp-subsection"
    note_html=(f'<div class="cp-subsection-note">{html.escape(str(note))}</div>' if note else '')
    st.markdown(
        f'<div class="{cls}"><div class="cp-subsection-title">{html.escape(str(title))}</div>{note_html}</div>',
        unsafe_allow_html=True,
    )


def _fact_grid(items: list[tuple[str, object]], *, wide_labels: set[str] | None=None):
    wide_labels=wide_labels or set()
    out=[]
    for label,value in items:
        cls='cp-fact wide' if str(label) in wide_labels else 'cp-fact'
        out.append(
            f'<div class="{cls}"><div class="cp-fact-label">{html.escape(str(label))}</div>'
            f'<div class="cp-fact-value" title="{html.escape(str(value))}">{html.escape(str(value))}</div></div>'
        )
    st.markdown('<div class="cp-fact-grid">'+''.join(out)+'</div>',unsafe_allow_html=True)


def _stat_strip(items: list[tuple[str, object, str]]):
    cards=[]
    for label,value,note in items:
        cards.append(
            '<div class="cp-stat"><div class="cp-stat-label">'+html.escape(str(label))+'</div>'
            '<div class="cp-stat-value">'+html.escape(str(value))+'</div>'
            + (f'<div class="cp-stat-note">{html.escape(str(note))}</div>' if note else '')
            + '</div>'
        )
    st.markdown('<div class="cp-stat-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)

def _data_heading(title: str, meta: str = ""):
    st.markdown(
        f'<div class="cp-data-head"><div class="cp-data-title">{html.escape(str(title))}</div>'
        f'<div class="cp-data-meta">{html.escape(str(meta))}</div></div>',
        unsafe_allow_html=True,
    )

BASE_CFG_PATH = APP_DIR / "config" / "config.json"
RUNS_DIR = APP_DIR / "runs"
FACTORY_DIR = APP_DIR / "factory_runs"
FACTORY_DIR.mkdir(exist_ok=True)
CACHE_DIR = APP_DIR / ".ui_cache"
CACHE_DIR.mkdir(exist_ok=True)
SETTINGS_ROOT = (Path(os.environ.get("LOCALAPPDATA")) / "ComplexPolicy" / "ModelLab") if os.environ.get("LOCALAPPDATA") else (APP_DIR / "runtime" / "user_data")
SETTINGS_STORE = UserSettingsStore(SETTINGS_ROOT)
SCIENTIST_CHAT_STORE = ScientistChatStore(SETTINGS_ROOT / "scientist_chat")


def fresh_cfg():
    return load_cfg(BASE_CFG_PATH)


def _config_digest(cfg: dict) -> str:
    raw=json.dumps(cfg or {},ensure_ascii=False,sort_keys=True,default=str,separators=(",",":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def ensure_state():
    if "ui_cfg" not in st.session_state:
        saved_cfg, saved_key, settings_meta, saved_ui = SETTINGS_STORE.load(fresh_cfg())
        # Durable shadow state is intentionally separate from Streamlit widget state.
        # Streamlit removes widget keys when a page is no longer rendered; without a
        # shadow copy, a later save would silently erase hidden-page settings.
        st.session_state._persistent_ui_cache = copy.deepcopy(saved_ui or {})
        # Restore ordinary widget/operator state before widgets are created.
        for k,v in (saved_ui or {}).items():
            if (k not in st.session_state
                    and k not in {"llm_api_key","ui_cfg","manual_cfg"}
                    and is_persistable_ui_key(k)):
                st.session_state[k]=copy.deepcopy(v)
        st.session_state.ui_cfg = saved_cfg
        st.session_state.llm_api_key = saved_key
        st.session_state.settings_meta = settings_meta
        st.session_state._last_saved_cfg_digest = _config_digest(saved_cfg)
    elif "_persistent_ui_cache" not in st.session_state:
        # Hot-reload / legacy-session repair: recover the durable cache from disk even
        # when ui_cfg already exists in the Streamlit session.
        try:
            _, _, _, saved_ui = SETTINGS_STORE.load(fresh_cfg())
            st.session_state._persistent_ui_cache = copy.deepcopy(saved_ui or {})
        except Exception:
            st.session_state._persistent_ui_cache = {}
    if "llm_api_key" not in st.session_state:
        st.session_state.llm_api_key = ""
    if "manual_cfg" not in st.session_state:
        st.session_state.manual_cfg = json.loads(json.dumps(st.session_state.ui_cfg))
    if "llm_models" not in st.session_state:
        st.session_state.llm_models = []
    if "llm_provider_connected" not in st.session_state:
        st.session_state.llm_provider_connected = False
    if "llm_connection_message" not in st.session_state:
        st.session_state.llm_connection_message = ""
    if "llm_last_provider" not in st.session_state:
        st.session_state.llm_last_provider = None
    if "left_nav_open" not in st.session_state:
        st.session_state.left_nav_open = True
    if "scientist_chat_open" not in st.session_state:
        st.session_state.scientist_chat_open = True
    if "scientist_chat_width" not in st.session_state:
        st.session_state.scientist_chat_width = "Balanced"
    if "scientist_chat_context_scope" not in st.session_state:
        st.session_state.scientist_chat_context_scope = "AUTO"
    if "scientist_chat_fallback" not in st.session_state:
        st.session_state.scientist_chat_fallback = False
    if "scientist_chat_clear_epoch" not in st.session_state:
        st.session_state.scientist_chat_clear_epoch = 0


def _rehydrate_persisted_ui_state(*, prefix: str | None = None) -> None:
    """Restore durable widget values that Streamlit removed while their page was hidden."""
    cache=st.session_state.get("_persistent_ui_cache")
    if not isinstance(cache,dict):
        return
    for k,v in cache.items():
        if prefix is not None and not str(k).startswith(prefix):
            continue
        if k not in st.session_state and is_persistable_ui_key(k):
            st.session_state[k]=copy.deepcopy(v)


def persist_user_settings() -> bool:
    # Persist all serializable operator/widget settings, excluding runtime/transient objects and secrets.
    # Start from the durable cache instead of only the currently rendered widgets.  This
    # prevents navigation away from Strategy Optimizer (or any future persisted page)
    # from deleting its saved values when Streamlit cleans up hidden widget keys.
    skip_exact={"llm_api_key","ui_cfg","manual_cfg","llm_models","llm_connection_message","settings_meta","_persistent_ui_cache"}
    skip_prefix=("pending_","uploaded_","FormSubmitter:","_progress")
    prior=st.session_state.get("_persistent_ui_cache")
    live_ui={}
    for k,v in st.session_state.items():
        if k in skip_exact or any(str(k).startswith(p) for p in skip_prefix) or not is_persistable_ui_key(k):
            continue
        live_ui[str(k)]=copy.deepcopy(v)
    ui_state=merge_persisted_ui_state(prior if isinstance(prior,dict) else {}, live_ui)
    try:
        SETTINGS_STORE.save(st.session_state.ui_cfg, st.session_state.llm_api_key, ui_state)
        st.session_state._persistent_ui_cache=copy.deepcopy(ui_state)
        st.session_state.pop("settings_persist_error",None)
        return True
    except Exception as e:
        st.session_state["settings_persist_error"]=str(e)
        return False


def save_uploaded_csv(uploaded) -> Path:
    p = CACHE_DIR / "uploaded_training.csv"
    tmp = p.with_name(p.name + ".tmp")
    data = bytes(uploaded.getbuffer())
    with writer_lock(p):
        tmp.write_bytes(data)
        os.replace(tmp, p)
    return p


def resolve_dataset(key_prefix: str = "main") -> Path | None:
    detected = default_mt5_training_csv()
    opts = ["Auto-detect MT5", "Upload CSV", "Custom path"]
    choice = st.radio("Sumber dataset", opts, horizontal=True, label_visibility="collapsed", key=f"{key_prefix}_source")
    if choice == opts[0]:
        if detected:
            st.caption(f"Terdeteksi: `{detected}`")
            return detected
        st.warning("ONNX training CSV belum ditemukan di MT5 Common Files.")
        return None
    if choice == opts[1]:
        up = st.file_uploader("Training CSV", type=["csv"], label_visibility="collapsed", key=f"{key_prefix}_upload")
        return save_uploaded_csv(up) if up else None
    text = st.text_input("Path CSV", value=str(detected or ""), key=f"{key_prefix}_path")
    if not text.strip():
        return None
    p = Path(text.strip().strip('"'))
    if p.exists() and p.is_file():
        return p
    st.error("File tidak ditemukan.")
    return None


def _dq_state_key(dataset: Path) -> str:
    return "data_quality::" + str(dataset.resolve()).lower()


def _cached_data_quality(dataset: Path) -> dict | None:
    row=st.session_state.get(_dq_state_key(dataset))
    if not isinstance(row,dict):
        return None
    # Audit semantics are versioned.  Never reuse a cached report created by an
    # older data-quality schema after Max itself has been upgraded.
    if str(row.get("schema") or "") != str(DATA_QUALITY_SCHEMA):
        return None
    try:
        current=integrity_summary(dataset)
        if str(row.get("sha256") or "") != str(current.get("sha256") or ""):
            return None
    except Exception:
        return None
    return row


def _render_data_quality(dataset: Path) -> dict | None:
    report=_cached_data_quality(dataset)
    with st.expander("Data quality · MT5 broker reconciliation", expanded=(not report or str(report.get("status")) not in {"VALID","VALID_WITH_WARNINGS"})):
        st.caption("Staged deterministic authority. AUDIT is local/cached only and never opens MT5. If the audit cannot prove readiness, REPAIR/VERIFY opens MT5, repairs only broker-backed gaps with the verified EA writer, then re-audits before Research may continue.")
        c1,c2=st.columns([1,1])
        with c1:
            if st.button("AUDIT DATA QUALITY",use_container_width=True,key=f"dq_audit_{str(dataset)}"):
                with st.spinner("Auditing CP32 locally · MT5 will not be opened…"):
                    report=audit_dataset(dataset,broker_reconcile=False,use_cached_broker_proof=True)
                    st.session_state[_dq_state_key(dataset)]=report
                st.rerun()
        with c2:
            if st.button("CLEAR AUDIT CACHE",use_container_width=True,key=f"dq_clear_{str(dataset)}",disabled=(report is None)):
                st.session_state.pop(_dq_state_key(dataset),None); st.rerun()
        report=_cached_data_quality(dataset)
        if not report:
            st.info("Belum diaudit. AUDIT DATA QUALITY tidak membuka MT5. START RESEARCH melakukan flow yang sama: local audit → PASS langsung Research; FAIL repair/verify → baru MT5 boleh dibuka.")
            return None
        b=dict(report.get("broker_reconciliation") or {})
        m=dict(report.get("market_sanity") or {})
        fh=dict(report.get("feature_health") or {})
        _stat_strip([
            ("STATUS",str(report.get("status") or "?"),"dataset authority"),
            ("MISSING",int(b.get("source_backed_missing_count",0) or 0),"exists in broker history"),
            ("DUPLICATES",int((report.get("physical") or {}).get("duplicate_extra_rows",0) or 0),"identity keys"),
            ("FEATURE WARN",int(fh.get("warnings",0) or 0),"CP32 health"),
        ])
        _fact_grid([
            ("Broker",b.get("server") or "unverified"),
            ("Time match",f"{float(b.get('match_ratio',0.0) or 0.0)*100:.2f}%"),
            ("OHLC match",f"{float(b.get('ohlc_match_ratio',0.0) or 0.0)*100:.2f}%" if b.get("verified") else "—"),
            ("OHLC invalid",int(m.get("invalid_ohlc_rows",0) or 0)),
            ("Quote invalid",int(m.get("invalid_decision_quote_rows",0) or 0)),
            ("Zero-spread",int(m.get("zero_spread_decision_quote_rows",0) or 0)),
            ("Dataset-only",int(b.get("dataset_only_count",0) or 0)),
        ])
        if not b.get("verified"):
            st.warning(f"Broker reconciliation belum VERIFIED · {b.get('reason') or 'unknown reason'}")
        if report.get("hard_reasons"):
            st.error("Hard data gate: " + " · ".join(str(x) for x in report.get("hard_reasons") or []))
        if report.get("warnings"):
            st.caption("Warnings: " + " · ".join(str(x) for x in report.get("warnings") or []))
        missing=list(b.get("missing_timestamps") or [])
        if missing:
            st.warning(f"{len(missing):,} source-backed missing bar ditemukan dari exact cached/live broker proof. Tidak ada interpolation/synthetic candle yang diizinkan.")
            st.dataframe(pd.DataFrame({"Missing broker bar":missing[:250]}),use_container_width=True,hide_index=True,height=min(300,55+28*min(8,len(missing))))
        elif b.get("verified"):
            proof_note="cached exact-SHA proof" if b.get("proof_cache") else "live broker proof"
            st.success(f"Broker reconciliation PASS · tidak ada source-backed missing bar · {proof_note}.")
        else:
            st.warning("Local audit belum memiliki exact-SHA broker proof. Ini bukan alasan membuka MT5 saat AUDIT; MT5 baru boleh dibuka pada REPAIR / VERIFY.")

        ok,reasons=research_readiness(report)
        repairable=(not report.get("hard_reasons")) and all(
            str(r).startswith("BROKER_RECONCILIATION_REQUIRED") or str(r).startswith("SOURCE_BACKED_MISSING_BARS:")
            for r in reasons
        )
        if (not ok) and repairable:
            try:
                all_targets=discover_mt5_gap_fill_targets()
                targets=matching_mt5_gap_fill_targets(all_targets,report) if b.get("verified") else all_targets
                if targets:
                    labels=[f"{Path(t['origin']).name} · {t['expert_relative']}" for t in targets]
                    pick=st.selectbox("MT5 repair target",list(range(len(targets))),format_func=lambda i:labels[i],key=f"gap_target_{str(dataset)}")
                    st.caption("REPAIR / VERIFY adalah satu-satunya tahap yang boleh membuka MT5. Target MT5 harus tertutup sebelum klik. Max akan verify broker feed, membuat Max_MTF_GapRepair.set dengan encoding MT5 yang benar, menjalankan tester writer, lalu verify ulang missing=0 sebelum menyatakan PASS.")
                    if st.button("REPAIR / VERIFY WITH MT5",type="primary",use_container_width=True,key=f"gap_repair_{str(dataset)}"):
                        with st.spinner("MT5 verify/repair running · tunggu sampai post-repair audit selesai…"):
                            repaired=run_gap_repair_cycle(dataset,target=targets[int(pick)])
                            report=dict(repaired.get("report") or {})
                            st.session_state[_dq_state_key(dataset)]=report
                            st.session_state[f"gap_repair_launch::{str(dataset)}"]=repaired
                        st.success("MT5 repair/verify selesai dan Data Quality PASS.")
                        st.rerun()
                else:
                    st.error("Max_MTF.ex5 tidak ditemukan pada MT5 target. Deploy/compile canonical Max_MTF.ex5 terlebih dahulu; audit lokal tidak akan membuka terminal lain secara otomatis.")
            except Exception as exc:
                st.error(f"Gap repair belum dapat dijalankan: {exc}")
        if ok:
            st.success("RESEARCH DATA GATE READY")
        else:
            st.warning("RESEARCH DATA GATE BLOCKED · " + " · ".join(reasons))
        return report


def dataset_card(
    dataset: Path | None,
    *,
    show_identity: bool = True,
    show_data_quality: bool = True,
) -> bool:
    if not dataset:
        return False
    try:
        physical=integrity_summary(dataset)
        if physical["duplicate_extra_rows"]:
            st.error(
                f"CSV fisik memiliki {physical['duplicate_extra_rows']:,} duplicate identity rows "
                f"({physical['duplicate_rows']:,} rows terlibat). Research fail-closed sampai dibersihkan."
            )
            st.caption("Repair memakai first-write-wins, membuat backup, lalu mengurutkan ulang berdasarkan signal_time.")
            if st.button("CLEAN LEGACY DUPLICATES · BACKUP FIRST", use_container_width=True, key=f"cleanup_{str(dataset)}"):
                try:
                    res=repair_legacy_duplicates(dataset)
                    st.success(f"{res['status']} · removed {res['removed']:,} · backup: {res['backup']}")
                    st.session_state.pop(_dq_state_key(dataset),None)
                    st.rerun()
                except Exception as e:
                    st.error(f"Cleanup gagal: {e}")
            return False
        x=quick_summary(dataset)
        if show_identity:
            with st.expander("Dataset identity · Clean master CSV", expanded=True):
                _fact_grid([
                    ("Symbol",x['symbol']),
                    ("Timeframe",x.get('timeframe') or period_label(x['period'])),
                    ("Unique rows",f"{x['rows']:,}"),
                    ("Available",f"{str(x['start'])[:10]} → {str(x['end'])[:10]}"),
                    ("Features",x['feature_count']),
                ],wide_labels={"Available"})
                st.markdown(
                    f'<div class="cp-info-line"><span>{html.escape(str(dataset))}</span>'
                    f'<span>{x["size_mb"]:.1f} MB · {html.escape(str(x["contract"]))} · duplicate keys 0 · SHA {html.escape(str(x["sha256"])[:12])}…</span></div>',
                    unsafe_allow_html=True,
                )
        if show_data_quality:
            _render_data_quality(dataset)
        return True
    except Exception as e:
        st.error(f"Dataset gagal preflight: {e}")
        return False


def research_window_controls(dataset: Path | None, cfg: dict, prefix: str):
    if dataset is None:
        return None, None, None
    try:
        info=available_date_range(dataset)
        dates=info["available_dates"]
        if len(dates)==1:
            start=end=dates[0]
            st.caption(f"Research date: {start}")
        else:
            start,end=st.select_slider(
                "Research date range",
                options=dates,
                value=(dates[0],dates[-1]),
                format_func=lambda d:d.strftime("%d %b %Y"),
                key=f"{prefix}_research_date_range",
            )
        preview=research_window_preview(dataset,start,end)
        a,b,c,d=st.columns(4)
        a.metric("Research rows",f"{preview['selected_rows']:,}")
        b.metric("Research cutoff",str(preview["cutoff"])[:16])
        c.metric("Reserved fresh raw",f"{preview['reserve_raw_rows']:,}")
        d.metric("Fresh mature",f"{preview['reserve_mature_raw_rows']:,}")
        st.caption(
            f"Master tersedia sampai {str(preview['master_end'])[:16]} · horizon {preview['horizon_bars']} bars · "
            f"pending maturity {preview['pending_horizon_rows']:,}. Data setelah cutoff tidak masuk snapshot research."
        )
        if preview["reserve_raw_rows"]==0:
            st.warning("Range memakai ujung CSV. Tidak ada fresh reserve setelah research cutoff; validation berikutnya harus menunggu data baru.")
        elif preview["reserve_mature_raw_rows"]==0:
            st.info("Fresh reserve sudah ada, tetapi belum ada row yang matang terhadap label horizon.")
        try:
            ident=quick_summary(dataset)
            sample=auto_trade_sample(ident["period"],start,end,cfg,"DISCOVERY",observed_fraction=0.50)
            if sample.get("minimum_trades") is not None:
                st.caption(f"Trade Sample AUTO · baseline H1 {int(sample['base_h1_trades_per_month'])}/bulan · estimated OOF minimum ≈ {int(sample['minimum_trades'])} closed trades. Exact gate dibekukan setelah fold exposure diketahui.")
        except Exception:
            pass
        return start,end,preview
    except Exception as e:
        st.error(f"Research range gagal: {e}")
        return None,None,None


def authority_source_csv(run_dir: Path) -> Path | None:
    """Resolve immutable source_window.csv through lineage; never fall back to master CSV."""
    cur=Path(run_dir)
    seen=set()
    for _ in range(12):
        if str(cur) in seen:
            break
        seen.add(str(cur))
        snap=cur/"source_window.csv"
        if snap.exists():
            return snap
        mp=cur/"model_manifest.json"
        if not mp.exists():
            break
        m=json.loads(mp.read_text(encoding="utf-8"))
        parent=m.get("source_run_id") or m.get("model_source_run_id")
        if not parent:
            break
        cur=RUNS_DIR/str(parent)
    return None


def authority_research_meta(run_dir: Path) -> dict:
    """Resolve immutable research window/hash/cutoff through lineage for display and routing."""
    cur=Path(run_dir); seen=set(); meta={"hash":"","cutoff":"","window":{}}
    for _ in range(12):
        if str(cur) in seen: break
        seen.add(str(cur))
        mp=cur/"model_manifest.json"
        if not mp.exists(): break
        m=json.loads(mp.read_text(encoding="utf-8"))
        rw=dict(m.get("research_window") or {})
        if not meta["window"] and rw: meta["window"]=rw
        if not meta["hash"]:
            meta["hash"]=str(m.get("research_source_csv_sha256") or rw.get("authority_snapshot_sha256") or "")
        if not meta["cutoff"]:
            meta["cutoff"]=str(m.get("research_source_raw_end") or rw.get("source_raw_end") or m.get("source_raw_end") or "")
        parent=m.get("source_run_id") or m.get("model_source_run_id")
        if not parent: break
        cur=RUNS_DIR/str(parent)
    return meta


def render_fresh_readiness(dataset: Path | None, cutoff, cfg: dict):
    if dataset is None or not cutoff:
        return None
    try:
        r=fresh_readiness(dataset,cutoff,cfg)
        a,b,c,d=st.columns(4)
        a.metric("Fresh raw",f"{r['raw_new_rows']:,}")
        b.metric("Mature raw",f"{r['mature_raw_rows']:,}")
        c.metric("Labeled fresh",f"{r['labeled_fresh_rows']:,}")
        d.metric("Pending horizon",f"{r['pending_horizon_rows']:,}")
        if r["status"]=="READY": st.success(f"READY · horizon {r['horizon_bars']} bars · newest {r['newest']}")
        elif r["status"]=="WAITING_LABEL_HORIZON": st.info(f"WAITING_LABEL_HORIZON · horizon {r['horizon_bars']} bars · newest {r['newest']}")
        else: st.warning(f"{r['status']} · horizon {r['horizon_bars']} bars · newest {r['newest']}")
        return r
    except Exception as e:
        st.error(f"Fresh readiness gagal: {e}")
        return None

def core_controls(cfg: dict, prefix: str):
    """Execution/label controls only. Statistical acceptance lives in KPI by Gate."""
    tsp=cfg.setdefault("trade_sample_policy",{})
    current_mode=str(tsp.get("mode","AUTO")).upper()
    st.markdown(
        '<div class="cp-policy-intro"><div class="cp-policy-title">Research policy</div>'
        '<div class="cp-policy-note">Execution and label policy only · statistical thresholds live in KPI by Gate</div></div>',
        unsafe_allow_html=True,
    )
    groups=["Execution","Labels"]
    group=st.radio("Research policy section",groups,horizontal=True,key=f"{prefix}_policy_group",label_visibility="collapsed")
    if group=="Execution":
        _subsection_header("Execution", "Sampling, compute budget, walk-forward structure and deterministic seed", first=True)
        tsp["mode"]=st.selectbox("Trade sample authority",["AUTO","MANUAL"],index=0 if current_mode=="AUTO" else 1,key=f"{prefix}_trade_sample_mode",help="AUTO calculates minimum closed trades from timeframe and exact evaluated range; the resolved requirement is frozen with the Factory.")
        if tsp["mode"]=="AUTO":
            st.markdown(
                f'<div class="cp-policy-info">AUTO · H1 baseline {int(tsp.get("base_h1_trades_per_month",8))} trades/month · '
                'timeframe scaling √ · monthly requirement ROUND UP to integer · final exact-range requirement ROUND UP. '
                'Discovery/CPCV use their actual evaluation exposure; Tournament/Fresh use the full evaluated window.</div>',
                unsafe_allow_html=True,
            )
        a,b,c=st.columns(3,gap="medium")
        cfg["cpu_threads"]=int(a.number_input("CPU threads",1,32,int(cfg.get("cpu_threads",4)),1,key=f"{prefix}_threads"))
        cfg["split"]["walk_forward_folds"]=int(b.number_input("Walk-forward folds",2,8,int(cfg["split"]["walk_forward_folds"]),1,key=f"{prefix}_folds"))
        cfg["seed"]=int(c.number_input("Seed",1,999999,int(cfg.get("seed",42)),1,key=f"{prefix}_seed"))
        _subsection_header("Search lifecycle", "Bounded experiment budget and stale-round patience")
        ac=cfg.setdefault("agent",{})
        a,b=st.columns(2,gap="medium")
        ac["max_experiments"]=int(a.number_input("Legacy experiment budget",6,300,int(ac.get("max_experiments",36)),6,key=f"{prefix}_max_experiments"))
        ac["patience_rounds"]=int(b.number_input("Stale rounds",1,10,int(ac.get("patience_rounds",2)),1,key=f"{prefix}_patience_rounds"))
    else:
        _subsection_header("Label policy", "Strategy execution geometry is inherited upstream; Research owns only label separation", first=True)
        d,e=st.columns(2,gap="medium")
        cfg["label"]["min_edge_r"]=float(d.number_input("Min edge R",-1.0,5.0,float(cfg["label"]["min_edge_r"]),.05,key=f"{prefix}_edge"))
        cfg["label"]["min_margin_r"]=float(e.number_input("Min margin R",0.0,5.0,float(cfg["label"]["min_margin_r"]),.05,key=f"{prefix}_margin"))
        u1,u2,u3=st.columns(3,gap="medium")
        cfg["label"]["utility_weight_enabled"]=bool(u1.toggle("Utility-aware label weight",value=bool(cfg["label"].get("utility_weight_enabled",True)),key=f"{prefix}_utility_enabled"))
        cfg["label"]["utility_weight_scale"]=float(u2.number_input("Utility scale",0.0,2.0,float(cfg["label"].get("utility_weight_scale",0.50)),.05,key=f"{prefix}_utility_scale"))
        cfg["label"]["utility_weight_cap_r"]=float(u3.number_input("Utility cap R",0.0,5.0,float(cfg["label"].get("utility_weight_cap_r",2.0)),.10,key=f"{prefix}_utility_cap"))
        st.caption("Execution-ineligible rows remain temporal context but are masked from supervised loss. Utility weighting only changes training emphasis; SELL/SKIP/BUY output semantics stay unchanged. SL/TP/MaxHold and execution gates are inherited from the promoted Strategy Champion and verified fail-closed at START.")


def _gate_num(container, label: str, profile: dict, key: str, *, lo=-1000.0, hi=1000.0, step=0.05, ui_key: str):
    profile[key]=float(container.number_input(label,min_value=float(lo),max_value=float(hi),value=float(profile.get(key,0.0)),step=float(step),key=ui_key))


def _gate_nested_num(container, label: str, profile: dict, parent: str, key: str, *, lo=-1000.0, hi=1000.0, step=0.05, ui_key: str):
    node=profile.setdefault(parent,{})
    if not isinstance(node,dict):
        node={}; profile[parent]=node
    node[key]=float(container.number_input(label,min_value=float(lo),max_value=float(hi),value=float(node.get(key,0.0)),step=float(step),key=ui_key))


def _render_risk_evidence_requirements(profile: dict, gate_key: str):
    rk=profile.get("risk_kpis") if isinstance(profile.get("risk_kpis"),dict) else {}
    if not rk: return
    with st.expander("Risk KPI evidence sufficiency · hard when metric is ON",expanded=False):
        st.caption("These are sample-validity gates, not performance targets. If an enabled metric lacks its required evidence, the stage fails as INSUFFICIENT_EVIDENCE rather than misclassifying model quality.")
        for key,spec in rk.items():
            if not isinstance(spec,dict):
                continue
            req_keys=[x for x in ("min_trades","min_active_days","min_tail_days","min_sample_years") if x in spec]
            if not req_keys:
                continue
            st.markdown(f"**{spec.get('label',key)}** · {'ON' if bool(spec.get('enabled',True)) else 'OFF'}")
            cols=st.columns(max(1,len(req_keys)),gap="small")
            for i,rk_key in enumerate(req_keys):
                if rk_key=="min_sample_years":
                    spec[rk_key]=float(cols[i].number_input("Min sample years",min_value=0.0,max_value=100.0,value=float(spec.get(rk_key,0.0) or 0.0),step=0.05,key=f"gate_{gate_key}_{key}_{rk_key}"))
                else:
                    label={"min_trades":"Min trades","min_active_days":"Min active days","min_tail_days":"Min tail days"}[rk_key]
                    spec[rk_key]=int(cols[i].number_input(label,min_value=0,max_value=100000,value=int(spec.get(rk_key,0) or 0),step=1,key=f"gate_{gate_key}_{key}_{rk_key}"))


def _render_gate_risk_kpis(profile: dict, gate_key: str):
    rk=profile.get("risk_kpis") if isinstance(profile.get("risk_kpis"),dict) else {}
    if not rk: return
    st.markdown('<div class="cp-inline-kicker">Risk-adjusted metrics</div>',unsafe_allow_html=True)
    for key,spec in rk.items():
        if key=="psr":
            cols=st.columns([1.15,.85,1.05,1.95],gap="small")
            spec["enabled"]=cols[0].toggle(str(spec.get("label",key)),value=bool(spec.get("enabled",True)),key=f"gate_{gate_key}_risk_enabled_{key}")
            op="≥" if str(spec.get("direction","higher"))=="higher" else "≤"
            spec["threshold"]=float(cols[1].number_input(f"{op} threshold",min_value=float(spec.get("ui_min",-1000.0)),max_value=float(spec.get("ui_max",1000.0)),value=float(spec.get("threshold",0.0)),step=float(spec.get("ui_step",0.01)),key=f"gate_{gate_key}_risk_threshold_{key}"))
            spec["benchmark_sharpe"]=float(cols[2].number_input("Benchmark Sharpe",min_value=-5.0,max_value=5.0,value=float(spec.get("benchmark_sharpe",0.20)),step=0.05,key=f"gate_{gate_key}_risk_psr_benchmark"))
            cols[3].caption(f"{spec.get('unit','')} · {spec.get('basis','')}")
        else:
            cols=st.columns([1.15,.85,3.0],gap="small")
            spec["enabled"]=cols[0].toggle(str(spec.get("label",key)),value=bool(spec.get("enabled",True)),key=f"gate_{gate_key}_risk_enabled_{key}")
            op="≥" if str(spec.get("direction","higher"))=="higher" else "≤"
            spec["threshold"]=float(cols[1].number_input(f"{op} threshold",min_value=float(spec.get("ui_min",-1000.0)),max_value=float(spec.get("ui_max",1000.0)),value=float(spec.get("threshold",0.0)),step=float(spec.get("ui_step",0.01)),key=f"gate_{gate_key}_risk_threshold_{key}"))
            note=f"{spec.get('unit','')} · {spec.get('basis','')}"
            if key=="cvar":
                note += " · Sign: -0.80 means worst 5% days average must be no worse than -0.80R; +0.80 requires worst days to remain profitable."
            mins=[]
            if spec.get("min_trades"): mins.append(f"≥{int(spec['min_trades'])} trades")
            if spec.get("min_active_days"): mins.append(f"≥{int(spec['min_active_days'])} active days")
            if spec.get("min_tail_days"): mins.append(f"≥{int(spec['min_tail_days'])} tail days")
            if spec.get("min_sample_years"): mins.append(f"≥{float(spec['min_sample_years']):.2f} years")
            if mins: note += " · Evidence: " + ", ".join(mins)
            cols[2].caption(note)
    _render_risk_evidence_requirements(profile,gate_key)


def render_gate_kpi_controls(cfg: dict):
    ensure_gate_kpi_profiles(cfg)
    st.caption("Each gate owns one independent profile. Profiles are frozen at START; changing one after START requires a new Factory/generation.")

    tsp=cfg.setdefault("trade_sample_policy",{})
    _subsection_header("Trade sample", "Research minimum closed-trade authority · separate from Strategy Optimizer", first=True)
    _ts_a,_ts_b,_ts_c=st.columns([1.15,1.0,2.1],gap="medium")
    _ts_mode=str(tsp.get("mode","AUTO")).upper()
    tsp["base_h1_trades_per_month"]=int(_ts_a.number_input(
        "Research H1 min trades / month",1,1000,int(tsp.get("base_h1_trades_per_month",8) or 8),1,
        key="research_kpi_h1_min_trades",disabled=(_ts_mode!="AUTO"),
        help="Research baseline only. AUTO scales this H1 rate by timeframe, rounds the monthly rate up, prorates the exact evaluated window/exposure, then rounds the final required closed trades up."
    ))
    _opt_h1=int((((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("base_h1_trades_per_month",20)) or 20)
    _ts_b.metric("Optimizer H1 baseline",f"{_opt_h1}/month",help="Separate Strategy Optimizer KPI authority; changing Research does not change Optimizer.")
    _ts_c.caption(
        f"Research authority {_ts_mode} · default H1 = 8/month · current H1 = {int(tsp.get('base_h1_trades_per_month',8))}/month · "
        "timeframe scaling uses the existing deterministic sample-policy engine with integer round-up. One Research baseline feeds Discovery/CPCV/Tournament/Fresh exposure rules; it is not duplicated per gate."
    )

    p=gate_profile(cfg,"discovery")
    _subsection_header("Discovery", "Full 3-fold WFA qualification", first=True)
    a,b,c=st.columns(3); _gate_num(a,"WFA overall Mean R",p,"cv_min_overall_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_dis_oexp"); _gate_num(b,"WFA median Mean R",p,"cv_min_median_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_dis_exp"); _gate_num(c,"WFA worst Mean R",p,"cv_min_worst_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_dis_wexp")
    a,b,c=st.columns(3); _gate_num(a,"WFA median PF",p,"cv_min_median_profit_factor",lo=0,hi=20,ui_key="g_dis_pf"); _gate_num(b,"Max DD R",p,"max_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_dis_dd"); _gate_num(c,"Worst-fold DD R",p,"cv_max_worst_fold_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_dis_wdd")
    a,b,c=st.columns(3); _gate_num(a,"Median Recovery",p,"cv_min_median_recovery_factor",lo=-100,hi=100,step=.1,ui_key="g_dis_mrf"); _gate_num(b,"Worst-fold Recovery",p,"cv_min_worst_fold_recovery_factor",lo=-100,hi=100,step=.1,ui_key="g_dis_wrf"); _gate_num(c,"Positive folds",p,"cv_min_positive_fold_ratio",lo=0,hi=1,step=.05,ui_key="g_dis_fold")
    a,b,c=st.columns(3); _gate_num(a,"Positive months",p,"min_positive_month_ratio",lo=0,hi=1,step=.05,ui_key="g_dis_pm"); _gate_num(b,"Positive quarters",p,"min_positive_quarter_ratio",lo=0,hi=1,step=.05,ui_key="g_dis_pq"); _gate_num(c,"Max regime concentration",p,"max_dominant_positive_regime_share",lo=0,hi=1,step=.05,ui_key="g_dis_regime")
    a,b,c=st.columns(3); _gate_num(a,"Max top-10% win share",p,"max_top10_win_profit_share",lo=0,hi=1,step=.05,ui_key="g_dis_top10"); _gate_nested_num(b,"Spread ×1.25 Min Exp R",p,"stress_min_expectancy_r","spread_x1.25",lo=-5,hi=5,step=.01,ui_key="g_dis_sp125"); _gate_nested_num(c,"Spread ×1.50 Min Exp R",p,"stress_min_expectancy_r","spread_x1.50",lo=-5,hi=5,step=.01,ui_key="g_dis_sp150")
    a,b,c=st.columns(3); _gate_num(a,"Threshold plateau profitable ratio",p,"sensitivity_min_profitable_ratio",lo=0,hi=1,step=.05,ui_key="g_dis_plateau")
    _render_gate_risk_kpis(p,"discovery")

    p=gate_profile(cfg,"cpcv")
    _subsection_header("CPCV", "Combinatorial robustness")
    a,b,c=st.columns(3); _gate_num(a,"Median PF",p,"cv_min_median_profit_factor",lo=0,hi=20,ui_key="g_cpcv_pf"); _gate_num(b,"Median Mean R",p,"cv_min_median_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_cpcv_exp"); _gate_num(c,"Worst Mean R",p,"cpcv_min_worst_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_cpcv_wexp")
    a,b,c=st.columns(3); _gate_num(a,"Worst DD R",p,"cv_max_worst_fold_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_cpcv_dd"); _gate_num(b,"Median Recovery",p,"cv_min_median_recovery_factor",lo=-100,hi=100,step=.1,ui_key="g_cpcv_mrf"); _gate_num(c,"Worst Recovery",p,"cv_min_worst_fold_recovery_factor",lo=-100,hi=100,step=.1,ui_key="g_cpcv_wrf")
    a,b,c=st.columns(3); _gate_num(a,"Positive paths",p,"cv_min_positive_fold_ratio",lo=0,hi=1,step=.05,ui_key="g_cpcv_paths"); _gate_num(b,"Min path sample ratio",p,"cpcv_min_path_sample_ratio",lo=0,hi=1,step=.05,ui_key="g_cpcv_sample")
    st.markdown('<div class="cp-inline-kicker">PBO</div>',unsafe_allow_html=True)
    pbo_a,pbo_b,pbo_c=st.columns([.8,.9,1.8],gap="medium")
    p["pbo_enabled"]=bool(pbo_a.toggle("Hard gate",value=bool(p.get("pbo_enabled",False)),key="g_cpcv_pbo_enabled"))
    p["pbo_max"]=float(pbo_b.number_input("Maximum PBO",min_value=0.0,max_value=1.0,value=float(p.get("pbo_max",0.20)),step=0.01,key="g_cpcv_pbo_max"))
    p["pbo_min_candidates"]=int(pbo_b.number_input("Min finalists",min_value=4,max_value=64,value=int(p.get("pbo_min_candidates",4)),step=1,key="g_cpcv_pbo_min_candidates"))
    pbo_status=str(p.get("pbo_status") or "COMPUTABLE_FROM_CROSS_STRATEGY_CPCV_GROUP_MATRIX_WHEN_ENABLED")
    pbo_c.markdown(f"**Status:** `{html.escape(pbo_status)}`")
    pbo_c.caption("Optional cross-strategy CSCV-style PBO on the six CPCV group OOS expectancy matrix. Requires enough finalists; if enabled and evidence is insufficient, CPCV fails closed. Candidate-local pseudo-PBO is forbidden.")
    _render_gate_risk_kpis(p,"cpcv")

    p=gate_profile(cfg,"tournament")
    _subsection_header("Tournament", "Hard eligibility before deterministic ranking")
    a,b,c=st.columns(3); _gate_num(a,"Min PF",p,"min_profit_factor",lo=0,hi=20,ui_key="g_t_pf"); _gate_num(b,"Min Exp R",p,"min_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_t_exp"); _gate_num(c,"Min Recovery",p,"min_recovery_factor",lo=0,hi=50,step=.1,ui_key="g_t_rf")
    a,b,c=st.columns(3); _gate_num(a,"Max DD R",p,"max_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_t_dd"); _gate_num(b,"Positive months",p,"min_positive_month_ratio",lo=0,hi=1,step=.05,ui_key="g_t_pm"); _gate_num(c,"Positive quarters",p,"min_positive_quarter_ratio",lo=0,hi=1,step=.05,ui_key="g_t_pq")
    a,b,c=st.columns(3); p["require_every_year_nonnegative"]=bool(a.toggle("Every year Exp R ≥ 0",value=bool(p.get("require_every_year_nonnegative",True)),key="g_t_every_year")); _gate_num(b,"Max regime concentration",p,"max_dominant_positive_regime_share",lo=0,hi=1,step=.05,ui_key="g_t_regime"); _gate_num(c,"Max top-10% win share",p,"max_top10_win_profit_share",lo=0,hi=1,step=.05,ui_key="g_t_top10")
    a,b,c=st.columns(3); _gate_num(a,"Spread ×1.50 Min Exp R",p,"stress_x1_50_min_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_t_sp150")
    st.caption("Ranking never rescues a candidate that failed eligibility. Tournament does not use Top-K elimination. Every active hard eligibility threshold is exposed above or in Risk-adjusted metrics.")
    _render_gate_risk_kpis(p,"tournament")

    p=gate_profile(cfg,"monte_carlo")
    _subsection_header("Monte Carlo", "Path and tail robustness")
    a,b,c,d=st.columns(4); _gate_num(a,"P05 PF",p,"min_p05_profit_factor",lo=0,hi=20,ui_key="g_mc_pf"); _gate_num(b,"P05 Exp R",p,"min_p05_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_mc_exp"); _gate_num(c,"P95 Max DD R",p,"max_p95_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_mc_dd"); _gate_num(d,"P05 Recovery",p,"min_p05_recovery_factor",lo=0,hi=50,step=.1,ui_key="g_mc_rf")
    a,b,c,d=st.columns(4); _gate_num(a,"Max P(loss)",p,"max_probability_loss",lo=0,hi=1,step=.01,ui_key="g_mc_ploss"); _gate_num(b,"Max P(ruin)",p,"max_probability_ruin",lo=0,hi=1,step=.01,ui_key="g_mc_pruin"); _gate_num(c,"Min survival",p,"min_survival_rate",lo=0,hi=1,step=.01,ui_key="g_mc_survival"); _gate_num(d,"Ruin floor R",p,"ruin_floor_r",lo=-1000,hi=0,step=1,ui_key="g_mc_ruin_floor")

    p=gate_profile(cfg,"fresh_forward")
    _subsection_header("Fresh Forward", "Untouched generalization")
    a,b,c,d=st.columns(4); _gate_num(a,"Min PF",p,"min_profit_factor",lo=0,hi=20,ui_key="g_f_pf"); _gate_num(b,"Min Exp R",p,"min_expectancy_r",lo=-5,hi=5,step=.01,ui_key="g_f_exp"); _gate_num(c,"Min Recovery",p,"min_recovery_factor",lo=0,hi=50,step=.1,ui_key="g_f_rf"); _gate_num(d,"Max DD R",p,"max_drawdown_r",lo=0,hi=1000,step=1,ui_key="g_f_dd")
    st.caption("Fresh degradation placeholders are inactive and therefore are not rendered as KPI controls. Every ACTIVE Fresh hard gate is visible here or under Risk-adjusted metrics.")
    _render_gate_risk_kpis(p,"fresh_forward")

    p=gate_profile(cfg,"champion_promotion")
    _subsection_header("Champion Promotion", "Promotion/integrity authority · no new statistical market test")
    checks=[("All upstream gates PASS",p.get("require_all_upstream_pass",True)),("Artifact integrity PASS",p.get("require_artifact_integrity",True)),("No post-Fresh tuning",p.get("require_no_post_forward_tuning",True)),("ONNX export PASS",p.get("require_onnx_export",True)),("ONNX parity PASS",p.get("require_onnx_parity",True))]
    cols=st.columns(5,gap="small")
    for col,(label,value) in zip(cols,checks): col.checkbox(label,value=bool(value),disabled=True,key=f"champion_contract_{label}")


def model_toggles(cfg: dict, prefix: str):
    items = [
        ("XGBoost", "xgboost", f"{prefix}_xgb", False),
        ("LightGBM", "lightgbm", f"{prefix}_lgb", False),
        ("Random Forest", "random_forest", f"{prefix}_rf", False),
        ("GRU Temporal", "gru", f"{prefix}_gru", False),
        ("GRU → XGBoost", "hybrid_xgboost", f"{prefix}_hxgb", False),
        ("GRU → LightGBM", "hybrid_lightgbm", f"{prefix}_hlgb", False),
        ("GRU → RandomForest", "hybrid_random_forest", f"{prefix}_hrf", False),
    ]
    for offset in range(0,len(items),4):
        cols=st.columns(4)
        for col,(title,key,widget_key,disabled) in zip(cols,items[offset:offset+4]):
            with col:
                st.markdown(f'<div class="cp-model-title">{title}</div>', unsafe_allow_html=True)
                value=False if disabled else bool(cfg["models"].get(key,True))
                enabled=st.toggle(title,value=value,disabled=disabled,key=widget_key,label_visibility="collapsed")
                if not disabled: cfg["models"][key]=enabled


def write_runtime_cfg(cfg: dict, name: str) -> Path:
    p = CACHE_DIR / name
    p.write_text(json.dumps(cfg,indent=2),encoding="utf-8")
    return p


def _llm_stack_health(llmc: dict) -> dict:
    stack=[x for x in (llmc.get("stack") or []) if isinstance(x,dict) and x.get("enabled",True)]
    if not stack and llmc.get("model"):
        stack=[{"provider":llmc.get("provider") or "custom","model":llmc.get("model")} ]
    try:
        snap=health_snapshot(llmc.get("model_health_path") or None)
    except Exception:
        snap={"models":{}}
    rows=[]; next_ready=None
    for i,e in enumerate(stack):
        provider=str(e.get("provider") or llmc.get("provider") or "custom"); model=str(e.get("model") or "")
        key=f"{provider.strip().lower()}|{model.strip()}"
        h=dict((snap.get("models") or {}).get(key) or {})
        cooldown=bool(h.get("cooldown_active")); status=str(h.get("status") or ("AVAILABLE" if not cooldown else "COOLDOWN"))
        if cooldown and status=="READY": status="COOLDOWN"
        if not cooldown and next_ready is None: next_ready={"priority":i+1,"provider":provider,"model":model,"status":status}
        rows.append({"priority":i+1,"provider":provider,"model":model,"status":status,"cooldown":cooldown,"until":h.get("cooldown_until_utc"),"category":h.get("last_error_category")})
    return {"rows":rows,"next_ready":next_ready,"snapshot":snap}

def _render_llm_route_health(llmc: dict, *, compact: bool=True):
    h=_llm_stack_health(llmc); rows=h.get("rows") or []
    if not rows: return
    primary=rows[0]; nxt=h.get("next_ready")
    if primary.get("cooldown"):
        route=(f"Primary {primary['model']} · {primary['status']} → next {nxt['model']}" if nxt else f"Primary {primary['model']} · {primary['status']} · no eligible fallback")
        st.warning(route)
    elif compact:
        st.caption(f"LLM route · {primary['model']} · {primary['status']}" + (f" · {len(rows)-1} fallback" if len(rows)>1 else ""))
    if not compact:
        view=[]
        for r in rows:
            view.append({"#":r["priority"],"Model":r["model"],"Provider":r["provider"],"Health":r["status"],"Cooldown until":r.get("until") or "—","Last error":r.get("category") or "—"})
        st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True)

def llm_provider_controls(llmc: dict):
    current_key=str(llmc.get("provider") or "gemini")
    current_label=PROVIDERS.get(current_key,PROVIDERS["custom"]).label
    labels=provider_labels(); idx=labels.index(current_label) if current_label in labels else 0
    top_left,top_right=st.columns(2,gap="medium")
    provider_label=top_left.selectbox("Provider",labels,index=idx,key="llm_provider_picker")
    provider_key=provider_key_from_label(provider_label); spec=PROVIDERS[provider_key]
    if st.session_state.llm_last_provider!=provider_key:
        st.session_state.llm_models=[]; st.session_state.llm_provider_connected=False; st.session_state.llm_connection_message=""; st.session_state.llm_last_provider=provider_key; llmc["model"]=""
    llmc["provider"]=provider_key
    if provider_key=="custom":
        base=top_right.text_input("OpenAI-compatible base URL",value=str(llmc.get("base_url") or llmc.get("endpoint") or ""),placeholder="https://provider.example/v1/",key="llm_custom_base")
    else:
        base=spec.base_url
        top_right.text_input("Endpoint",value=str(base),disabled=True,key="llm_provider_endpoint")
    llmc["base_url"]=normalize_base_url(base); llmc.pop("endpoint",None)

    key_col,connect_col=st.columns([4.5,1.0],gap="small")
    if spec.needs_api_key or provider_key=="custom":
        st.session_state.llm_api_key=key_col.text_input("API key · encrypted on disk (Windows DPAPI)",value=st.session_state.llm_api_key,type="password",key="llm_api_key_input")
    else:
        st.session_state.llm_api_key=""; key_col.text_input("API key",value="Not required",disabled=True,key="llm_api_key_not_required")
    connect=connect_col.button("CONNECT",use_container_width=True,key="llm_connect_models")
    if connect:
        try:
            if spec.needs_api_key and not st.session_state.llm_api_key.strip(): raise ValueError("API key belum diisi")
            models=list_models(llmc["base_url"],st.session_state.llm_api_key,timeout=int(llmc.get("timeout_sec",60)),chat_only=True)
            st.session_state.llm_models=models; st.session_state.llm_provider_connected=True; st.session_state.llm_connection_message=f"Connected · {len(models)} model"
            if str(llmc.get("model") or "") not in models: llmc["model"]=models[0]
        except Exception as e:
            st.session_state.llm_models=[]; st.session_state.llm_provider_connected=False; st.session_state.llm_connection_message=str(e)

    if st.session_state.llm_provider_connected and st.session_state.llm_models:
        models=st.session_state.llm_models; cur=str(llmc.get("model") or ""); midx=models.index(cur) if cur in models else 0
        primary=st.selectbox("Primary model",models,index=midx,key="llm_model_picker"); llmc["model"]=primary
        existing=[str(x.get("model")) for x in (llmc.get("stack") or [])[1:] if isinstance(x,dict) and str(x.get("model") or "") in models and str(x.get("model"))!=primary]
        fallbacks=st.multiselect("Fallback models · ordered",[m for m in models if m!=primary],default=existing,key="llm_fallback_models",help="AUTONOMOUS Scientist/Director route only. Quota/rate-limit/unavailable/5xx/timeout may fall through this ordered stack.")
        llmc["stack"]=[{"provider":provider_key,"base_url":llmc["base_url"],"model":primary,"api_key_env":str(llmc.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY"),"enabled":True}] + [{"provider":provider_key,"base_url":llmc["base_url"],"model":m,"api_key_env":str(llmc.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY"),"enabled":True} for m in fallbacks]
        chat_existing=[]
        for raw in llmc.get("chat_fallback_stack") or []:
            m=str(raw.get("model") if isinstance(raw,dict) else raw or "").strip()
            if m in models and m!=primary and m not in chat_existing: chat_existing.append(m)
        chat_fallbacks=st.multiselect(
            "Scientist Chat fallback · explicit/manual",[m for m in models if m!=primary],default=chat_existing,
            key="llm_chat_fallback_models",
            help="Separate from autonomous research routing. Empty = a manually selected Chat model NEVER falls back. Add models here only if you explicitly want Chat fallback.",
        )
        llmc["chat_fallback_stack"]=[{"provider":provider_key,"base_url":llmc["base_url"],"model":m,"api_key_env":str(llmc.get("api_key_env") or "COMPLEXPOLICY_LLM_API_KEY"),"enabled":True} for m in chat_fallbacks]
        st.caption(st.session_state.llm_connection_message + f" · research stack {len(llmc['stack'])} · Chat fallback {len(llmc['chat_fallback_stack'])}")

        # Scientist Chat model profiles are separate from autonomous Research routing.
        # Every model keeps its own analysis/latency/context envelope. Unsupported
        # provider-specific reasoning knobs are deliberately not fabricated here.
        with st.expander("Scientist Chat · per-model profile",expanded=False):
            profiles=llmc.setdefault("chat_model_profiles",{})
            profile_model=st.selectbox("Configure model",models,index=(models.index(primary) if primary in models else 0),key="chat_profile_model")
            safe_key=''.join(ch if ch.isalnum() else '_' for ch in profile_model)[:48]
            prof=profiles.setdefault(profile_model,{})
            resolved=chat_model_profile(llmc,profile_model)
            a,b,c=st.columns(3,gap="small")
            prof["analysis_depth"]=a.selectbox("Analysis depth",["QUICK","BALANCED","DEEP"],index=["QUICK","BALANCED","DEEP"].index(str(resolved.get("analysis_depth") or "DEEP")),key=f"chat_profile_depth_{safe_key}",help="Prompt/context depth only; never exposes hidden chain-of-thought.")
            prof["temperature"]=float(b.slider("Temperature",0.0,1.5,float(resolved.get("temperature",0.20)),0.05,key=f"chat_profile_temp_{safe_key}"))
            prof["streaming"]=c.toggle("Streaming",value=bool(resolved.get("streaming",True)),key=f"chat_profile_stream_{safe_key}",help="Uses provider SSE when supported; same-model buffered compatibility fallback remains available.")
            d,e,f=st.columns(3,gap="small")
            prof["timeout_sec"]=int(d.number_input("Request timeout · sec",10,180,int(resolved.get("timeout_sec",60)),5,key=f"chat_profile_timeout_{safe_key}"))
            prof["max_output_tokens"]=int(e.number_input("Max output tokens",256,32768,int(resolved.get("max_output_tokens",8192)),256,key=f"chat_profile_output_{safe_key}"))
            prof["stream_fallback_to_buffered"]=f.toggle("Same-model buffered fallback",value=bool(resolved.get("stream_fallback_to_buffered",True)),key=f"chat_profile_buffered_{safe_key}")
            g,h,i=st.columns(3,gap="small")
            prof["context_chars"]=int(g.number_input("Research context chars",4000,120000,int(resolved.get("context_chars",60000)),2000,key=f"chat_profile_context_{safe_key}"))
            prof["history_messages"]=int(h.number_input("History messages",0,32,int(resolved.get("history_messages",16)),1,key=f"chat_profile_history_n_{safe_key}"))
            prof["history_chars"]=int(i.number_input("History chars",0,60000,int(resolved.get("history_chars",28000)),1000,key=f"chat_profile_history_chars_{safe_key}"))
            st.caption("Chat profile affects discussion only. AUTO Research Scientist/Director continues to use the ordered autonomous model stack above.")
        _render_llm_route_health(llmc,compact=False)
    else:
        st.selectbox("Primary model",["Connect provider dulu"],disabled=True,key="llm_model_disabled")
        if st.session_state.llm_connection_message: st.error(st.session_state.llm_connection_message)

    stack=[x for x in (llmc.get("stack") or []) if isinstance(x,dict) and x.get("enabled",True)]
    if stack:
        with st.expander("Token pricing · optional cost estimator",expanded=False):
            pricing=llmc.setdefault("pricing_usd_per_1m",{})
            for i,entry in enumerate(stack):
                pkey=f"{entry.get('provider','custom')}|{entry.get('model','')}"; row=pricing.setdefault(pkey,{"enabled":False,"input":0.0,"output":0.0,"cached_input":0.0})
                st.markdown(f"**#{i+1} · {entry.get('model')}** · {entry.get('provider')}")
                pc=st.columns([.8,1,1,1],gap="small")
                row["enabled"]=pc[0].toggle("Cost",value=bool(row.get("enabled",False)),key=f"llm_price_on_{i}_{pkey}")
                row["input"]=float(pc[1].number_input("Input $/1M",min_value=0.0,max_value=100000.0,value=float(row.get("input",0.0) or 0.0),step=0.01,format="%.4f",key=f"llm_price_in_{i}_{pkey}"))
                row["output"]=float(pc[2].number_input("Output $/1M",min_value=0.0,max_value=100000.0,value=float(row.get("output",0.0) or 0.0),step=0.01,format="%.4f",key=f"llm_price_out_{i}_{pkey}"))
                row["cached_input"]=float(pc[3].number_input("Cached $/1M",min_value=0.0,max_value=100000.0,value=float(row.get("cached_input",row.get("input",0.0)) or 0.0),step=0.01,format="%.4f",key=f"llm_price_cache_{i}_{pkey}"))
    return provider_key

def _human_label(name: str) -> str:
    mapping = {
        "CV_MIN_TRADES":"CV minimum trades",
        "CV_MEDIAN_MAX_DD":"CV median Max Drawdown",
        "CV_WORST_FOLD_MAX_DD":"CV worst-fold Max Drawdown",
        "CV_MEDIAN_RECOVERY":"CV median Recovery Factor",
        "CV_WORST_FOLD_RECOVERY":"CV worst-fold Recovery Factor",
        "CV_MEDIAN_PF":"CV median Profit Factor",
        "CV_MEDIAN_EXPECTANCY":"CV median Expectancy",
        "CV_WORST_EXPECTANCY":"CV worst-fold Expectancy",
        "CV_POSITIVE_FOLD_RATIO":"Positive folds",
        "CV_POSITIVE_MONTH_RATIO":"Positive months",
        "CV_POSITIVE_QUARTER_RATIO":"Positive quarters",
        "CV_REGIME_CONCENTRATION":"Regime concentration",
        "CV_TOP10_WIN_CONCENTRATION":"Top-10% win concentration",
        "CV_STRESS_SPREAD_X1.25_EXPECTANCY":"CV spread ×1.25 Expectancy",
        "CV_STRESS_SPREAD_X1.50_EXPECTANCY":"CV spread ×1.50 Expectancy",
        "CV_TAKE_THRESHOLD_PLATEAU":"CV take-threshold plateau",
        "TEST_MIN_TRADES":"Locked-test minimum trades",
        "TEST_PROFIT_FACTOR":"Locked-test Profit Factor",
        "TEST_EXPECTANCY":"Locked-test Expectancy",
        "TEST_MAX_DRAWDOWN":"Locked-test Max Drawdown",
        "TEST_RECOVERY_FACTOR":"Locked-test Recovery Factor",
        "TEST_POSITIVE_MONTH_RATIO":"Positive months",
        "TEST_POSITIVE_QUARTER_RATIO":"Positive quarters",
        "TEST_REGIME_CONCENTRATION":"Regime concentration",
        "TEST_TOP10_WIN_CONCENTRATION":"Top-10% winning-profit concentration",
        "ONNX_PARITY":"Python ↔ ONNX parity",
        "TAKE_THRESHOLD_PLATEAU":"Take-threshold plateau",
        "STRESS_SPREAD_X1.25_EXPECTANCY":"Spread ×1.25 Expectancy",
        "STRESS_SPREAD_X1.50_EXPECTANCY":"Spread ×1.50 Expectancy",
    }
    return mapping.get(str(name), str(name).replace("_"," ").title())

def _fmt(v, kind: str = "num") -> str:
    if v is None:
        return "—"
    try:
        x=float(v)
    except Exception:
        return str(v)
    if not math.isfinite(x):
        return "—"
    if kind=="pct": return f"{x*100:.1f}%"
    if kind=="r": return f"{x:.4f} R"
    if kind=="r2": return f"{x:.2f} R"
    if kind=="int": return f"{int(round(x)):,}"
    if kind=="sci": return f"{x:.2e}"
    return f"{x:.4f}" if abs(x)<10 else f"{x:.2f}"


def _priority_text(priorities: dict) -> str:
    if not priorities:
        return "Tidak ada perubahan prioritas family."
    ordered=sorted(priorities.items(), key=lambda kv: float(kv[1]), reverse=True)
    return " · ".join(f"{str(k).replace('_',' ').title()} {float(v):.2g}×" for k,v in ordered)


def _scientist_proposal_row(p: dict) -> dict:
    """Registry-aware proposal projection; pure and composed families share one UI contract."""
    params=p.get("params") if isinstance(p.get("params"),dict) else {}
    fam=str(p.get("family") or "?").lower(); parts=hybrid_parts(fam); spec=family_spec(fam) or {}
    row={"Model":p.get("name","?"),"Family":_family_display_name(fam),"Memory M":params.get("training_memory_months","—")}
    if parts:
        temporal,policy=parts; row.update({"Temporal":temporal.upper(),"Policy":policy.replace("_"," ").title(),
            "Seq":params.get("temporal_sequence_length",params.get("gru_sequence_length","—")),
            "Width":params.get("temporal_hidden_size",params.get("temporal_d_model",params.get("temporal_tcn_channels",params.get("gru_hidden_size","—")))),
            "Layers":params.get("temporal_num_layers",params.get("temporal_tcn_blocks",params.get("gru_num_layers","—"))),
            "Dropout":params.get("temporal_dropout",params.get("gru_dropout","—")),
            "Temporal LR":params.get("temporal_learning_rate",params.get("gru_learning_rate","—")),
            "Policy Trees":params.get("policy_n_estimators","—"),"Policy Depth":params.get("policy_max_depth","—"),
            "Policy LR":params.get("policy_learning_rate","—"),
            "Policy Child":params.get("policy_min_child_weight",params.get("policy_min_child_samples",params.get("policy_min_samples_leaf","—"))),
            "Reg α":params.get("policy_reg_alpha","—"),"Reg λ":params.get("policy_reg_lambda","—")})
    elif spec.get("role")=="temporal":
        row.update({"Seq":params.get("sequence_length","—"),"Width":params.get("hidden_size",params.get("d_model",params.get("tcn_channels","—"))),
                    "Layers":params.get("num_layers",params.get("tcn_blocks","—")),"Dropout":params.get("dropout","—"),
                    "LR":params.get("learning_rate","—"),"Epochs":params.get("epochs","—"),"Batch":params.get("batch_size","—")})
    else:
        row.update({"Trees":params.get("n_estimators","—"),"Depth":params.get("max_depth","—"),"LR":params.get("learning_rate","—"),
                    "Child":params.get("min_child_weight",params.get("min_child_samples",params.get("min_samples_leaf","—"))),
                    "Reg α":params.get("reg_alpha","—"),"Reg λ":params.get("reg_lambda","—"),"Subsample":params.get("subsample","—"),"Columns":params.get("colsample_bytree","—")})
    return row


def _fmt_tokens(v) -> str:
    if v is None or v == "":
        return "—"
    try:
        n=int(v)
    except Exception:
        return "—"
    if n>=1_000_000: return f"{n/1_000_000:.2f}M"
    if n>=1_000: return f"{n/1_000:.1f}k"
    return str(n)


def _fmt_cost(v, partial: bool = False) -> str:
    try:
        if v is None: return "Not set"
        x=float(v)
        if x < 0.0001: txt=f"${x:.6f}"
        elif x < 0.01: txt=f"${x:.5f}"
        else: txt=f"${x:.4f}"
        return txt + ("+" if partial else "")
    except Exception:
        return "Not set"


def _ui_llm_cfg() -> dict:
    try:
        cfg=st.session_state.get("ui_cfg") or {}
        llm=((cfg.get("agent") or {}).get("llm") or {})
        return llm if isinstance(llm,dict) else {}
    except Exception:
        return {}


def _configured_llm_identity() -> dict:
    llm=_ui_llm_cfg()
    stack=[x for x in (llm.get("stack") or []) if isinstance(x,dict) and x.get("enabled",True)]
    primary=stack[0] if stack else {}
    return {
        "provider": str(primary.get("provider") or llm.get("provider") or "—"),
        "model": str(primary.get("model") or llm.get("model") or "UNKNOWN"),
        "pricing": llm.get("pricing_usd_per_1m") if isinstance(llm.get("pricing_usd_per_1m"),dict) else {},
    }


def _nested_dict(obj, *keys):
    cur=obj
    for k in keys:
        if not isinstance(cur,dict): return {}
        cur=cur.get(k)
    return cur if isinstance(cur,dict) else {}


def _first_dict(*items):
    for x in items:
        if isinstance(x,dict) and x:
            return x
    return {}


def _ui_report_text(entry: dict) -> str:
    # Only text already present in the rendered Scientist artifact is counted here.
    # This is deliberately NOT presented as total API usage because the original
    # prompt/context may not exist in legacy journal entries.
    keep={}
    for k in ("summary","report","scientific_method","strategy","hypotheses","next_discovery_plan","proposals","error"):
        v=entry.get(k)
        if v not in (None,"",{},[]): keep[k]=v
    try:
        return json.dumps(keep,ensure_ascii=False,sort_keys=True,default=str)
    except Exception:
        return str(keep)


def _scientist_usage(entry: dict) -> dict:
    # UI-only backward-compatible resolver. New reports can expose provenance in
    # several shapes; old/running backends may expose none at all. Never invent an
    # actual fallback route when it was not persisted.
    report=entry.get("report") if isinstance(entry.get("report"),dict) else {}
    prov=_first_dict(
        entry.get("llm_provenance"), entry.get("provenance"),
        report.get("llm_provenance"), report.get("provenance"),
        _nested_dict(entry,"metadata","llm_provenance"),
        _nested_dict(entry,"scientist","llm_provenance"),
    )
    usage=_first_dict(
        prov.get("usage"), entry.get("token_usage"), entry.get("usage"),
        report.get("token_usage"), report.get("usage"),
    )
    cost=_first_dict(prov.get("cost"),entry.get("cost"),report.get("cost"))
    actual=bool(prov.get("selected_model") or prov.get("selected_provider") or prov.get("attempts"))

    ident=_configured_llm_identity()
    if not prov:
        prov={
            "selected_priority":None,
            "selected_provider":None,
            "selected_model":None,
            "configured_provider":ident["provider"],
            "configured_model":ident["model"],
            "fallback_used":None,
            "attempts":[],
            "display_source":"ACTUAL_ROUTE_UNAVAILABLE",
        }
    else:
        prov=dict(prov)
        prov.setdefault("display_source","ACTUAL_PROVENANCE" if actual else "JOURNAL_METADATA")
        if not actual:
            prov.setdefault("configured_provider",ident["provider"])
            prov.setdefault("configured_model",ident["model"])

    if not usage:
        out_est=int(estimate_token_count(_ui_report_text(entry)) or 0)
        usage={
            "input_tokens":None,
            "output_tokens":out_est if out_est>0 else None,
            "total_tokens":None,
            "cached_input_tokens":None,
            "reasoning_tokens":None,
            "source":"UI_OUTPUT_ESTIMATE_ONLY" if out_est>0 else "UNAVAILABLE",
            "partial":True,
        }
    else:
        usage=dict(usage)
        usage.setdefault("partial",False)

    if not cost and usage.get("output_tokens") is not None:
        provider=str(prov.get("selected_provider") or prov.get("configured_provider") or ident["provider"])
        model=str(prov.get("selected_model") or prov.get("configured_model") or ident["model"])
        row=(ident.get("pricing") or {}).get(f"{provider}|{model}")
        if isinstance(row,dict) and row.get("enabled"):
            # With a legacy backend only output tokens are reconstructable here.
            # Mark cost partial so the operator never mistakes it for full API cost.
            out_cost=float(usage.get("output_tokens") or 0)*float(row.get("output",0.0) or 0.0)/1_000_000.0
            cost={"configured":True,"estimated_cost_usd":out_cost,"partial":bool(usage.get("partial")),"source":"UI_PARTIAL_ESTIMATE"}

    return {"provenance":prov,"usage":usage,"cost":cost,"actual_provenance":actual}


def _aggregate_llm_usage(entries: list[dict]) -> dict:
    seen=set(); out={"calls":0,"input_tokens":0,"output_tokens":0,"total_tokens":0,"input_known_calls":0,"total_known_calls":0,"fallbacks":0,"known_cost_usd":0.0,"cost_calls":0,"partial_cost_calls":0,"estimated_usage_calls":0,"configured_model_calls":0}
    for e in entries or []:
        rid=str(e.get("report_id") or "")
        key=rid or f"{e.get('created_utc')}|{e.get('source')}|{e.get('factory_generation')}|{e.get('round')}|{e.get('summary')}"
        if key in seen: continue
        seen.add(key)
        x=_scientist_usage(e); p=x["provenance"]; u=x["usage"]; c=x["cost"]
        if not p: continue
        out["calls"]+=1
        if u.get("input_tokens") is not None:
            out["input_tokens"]+=int(u.get("input_tokens") or 0); out["input_known_calls"]+=1
        if u.get("output_tokens") is not None:
            out["output_tokens"]+=int(u.get("output_tokens") or 0)
        if u.get("total_tokens") is not None:
            out["total_tokens"]+=int(u.get("total_tokens") or 0); out["total_known_calls"]+=1
        out["fallbacks"]+=1 if p.get("fallback_used") is True else 0
        out["configured_model_calls"]+=1 if p.get("display_source")=="ACTUAL_ROUTE_UNAVAILABLE" else 0
        out["estimated_usage_calls"]+=1 if str(u.get("source") or "").upper().startswith("UI_") or str(u.get("source") or "").upper()=="ESTIMATED" else 0
        if c.get("configured") and c.get("estimated_cost_usd") is not None:
            out["known_cost_usd"]+=float(c.get("estimated_cost_usd") or 0.0); out["cost_calls"]+=1
            out["partial_cost_calls"]+=1 if c.get("partial") else 0
    return out


def _render_scientist_entry(entry: dict, compact: bool = False):
    rnd=int(entry.get("round",0) or 0); gen=int(entry.get("factory_generation",0) or 0)
    phase=str(entry.get("phase") or "").strip().upper(); source=str(entry.get("source") or "").strip().upper(); stage=str(entry.get("stage") or "").strip().upper()
    summary=str(entry.get("summary") or "").strip(); report=entry.get("report") if isinstance(entry.get("report"),dict) else {}; strategy=entry.get("strategy") if isinstance(entry.get("strategy"),dict) else {}
    condition=str(report.get("condition") or summary or "Belum ada laporan substantif dari Scientist."); interpretation=str(report.get("interpretation") or ""); next_action=str(report.get("next_action") or strategy.get("focus") or ""); confidence=report.get("confidence"); err=entry.get("error")
    if stage and str(entry.get("schema") or "").startswith("CP_STAGE_SCIENTIST"):
        label=f"{stage.replace('_',' ')} · SCIENTIST REVIEW"; subject=entry.get("subject") if isinstance(entry.get("subject"),dict) else {}
        if stage=="CPCV_CANDIDATE" and subject: label+=f" · {subject.get('pool_id') or subject.get('name') or '?'} · {subject.get('status') or ''}"
    elif source=="FACTORY_RESEARCH_DIRECTOR": label="FACTORY PRE-FLIGHT" if phase=="PREFLIGHT" else f"FACTORY GEN {gen} · {phase.replace('_',' ')}"
    elif gen>0: label=f"FACTORY GEN {gen} · ROUND {rnd}" + (f" · {phase.replace('_',' ')}" if phase and phase!="SUPERVISOR_ROUND_REVIEW" else "")
    else: label=f"ROUND {rnd}" + (f" · {phase.replace('_',' ')}" if phase else "")
    if err:
        st.warning(f"{label}: {err}" + (" · non-fatal; deterministic research tetap berjalan." if source=="FACTORY_RESEARCH_DIRECTOR" and phase=="PREFLIGHT" else "")); return

    x=_scientist_usage(entry); prov=x["provenance"]; usage=x["usage"]; cost=x["cost"]
    model=str(prov.get("selected_model") or "Actual model unavailable"); provider=str(prov.get("selected_provider") or "—"); priority=prov.get("selected_priority"); actual=bool(x.get("actual_provenance")); configured_model=str(prov.get("configured_model") or _configured_llm_identity().get("model") or "—"); configured_provider=str(prov.get("configured_provider") or _configured_llm_identity().get("provider") or "—")
    route=("PRIMARY" if priority in (1,"1") else (f"FALLBACK #{max(1,int(priority or 1)-1)}" if priority else "ACTUAL MODEL")) if actual else "ACTUAL ROUTE UNAVAILABLE"
    total_display=_fmt_tokens(usage.get("total_tokens")) if usage.get("total_tokens") is not None else (f">={_fmt_tokens(usage.get('output_tokens'))}" if usage.get("output_tokens") is not None else "—")
    cost_display=_fmt_cost(cost.get("estimated_cost_usd") if cost.get("configured") else None,partial=bool(cost.get("partial")))
    conf="—"
    if confidence is not None:
        try: conf=f"{float(confidence)*100:.0f}%"
        except Exception: pass

    if compact:
        usage_badge=f"{total_display} tok" if total_display!="—" else "usage unavailable"
        st.markdown(
            f'<div class="cp-scientist-compact"><div class="cp-scientist-compact-head"><div><div class="cp-scientist-round">{html.escape(label)}</div><div class="cp-scientist-model">{html.escape(model)}</div><div class="cp-scientist-meta">{html.escape(provider)} · {html.escape(route)} · {html.escape(usage_badge)} · cost {html.escape(cost_display)} · confidence {html.escape(conf)}{(" · configured " + html.escape(configured_model)) if not actual else ""}</div></div></div>'
            f'<div class="cp-summary-grid"><div class="cp-summary-cell"><div class="cp-summary-label">Condition</div><div class="cp-summary-body">{html.escape(condition)}</div></div>'
            f'<div class="cp-summary-cell"><div class="cp-summary-label">Interpretation</div><div class="cp-summary-body">{html.escape(interpretation or "—")}</div></div>'
            f'<div class="cp-summary-cell"><div class="cp-summary-label">Next action</div><div class="cp-summary-body">{html.escape(next_action or "—")}</div></div></div></div>',unsafe_allow_html=True)
        return

    st.markdown(f'<div class="cp-scientist-round">{html.escape(label)}</div>', unsafe_allow_html=True)
    meta=st.columns([2.35,1.0,1.0,1.0,1.1],gap="small")
    meta[0].metric("Model",model,help=f"Provider: {provider} · route: {route}" + ("" if actual else " · actual fallback route was not persisted by this journal entry"))
    meta[1].metric("Input",_fmt_tokens(usage.get("input_tokens")),help="Provider usage when persisted; legacy journal without prompt usage remains unavailable.")
    meta[2].metric("Output",_fmt_tokens(usage.get("output_tokens")),help="Provider-reported when available; legacy report may use UI-side output estimate.")
    meta[3].metric("Total",total_display,help=f"Source: {usage.get('source') or 'UNAVAILABLE'}. >= means output-only reconstruction.")
    meta[4].metric("API cost",cost_display,help="+ means partial estimate because input usage is unavailable.")
    st.caption(f"{provider} · {route} · token source {usage.get('source') or 'UNAVAILABLE'}" + (" · fallback used" if prov.get("fallback_used") is True else ""))
    _ca=entry.get("compiled_authority") if isinstance(entry.get("compiled_authority"),dict) else {}
    if _ca:
        _bounds=_ca.get("parameter_bounds") if isinstance(_ca.get("parameter_bounds"),dict) else {}
        _pri=_ca.get("family_size_priorities") if isinstance(_ca.get("family_size_priorities"),dict) else {}
        _used=[]
        for _fam in _bounds:
            _parts=str(_fam).split("::")
            for _x in (_parts[1:] if len(_parts)>2 and _parts[0]=="hybrid" else [_fam]):
                if _x in _pri and _x not in _used: _used.append(_x)
        _size=" · ".join(f"{_family_display_name(x)} {float(_pri[x]):.2f}" for x in _used[:6])
        st.caption("Compiled authority · deterministic effective bounds" + ((" · frozen size " + _size) if _size else ""))
    attempts=prov.get("attempts") if isinstance(prov.get("attempts"),list) else []
    if attempts and prov.get("fallback_used"):
        with st.expander("LLM call provenance",expanded=False):
            rows=[]
            for a in attempts:
                au=a.get("usage") if isinstance(a.get("usage"),dict) else {}; ac=a.get("cost") if isinstance(a.get("cost"),dict) else {}
                rows.append({"#":a.get("priority"),"Provider":a.get("provider"),"Model":a.get("model"),"Status":a.get("status"),"Reason":a.get("category") or "—","Input":au.get("input_tokens"),"Output":au.get("output_tokens"),"Total":au.get("total_tokens"),"Cost USD":ac.get("estimated_cost_usd") if ac.get("configured") else None})
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

    method=entry.get("scientific_method") if isinstance(entry.get("scientific_method"),dict) else {}
    if method:
        # Acceptance authority markers kept explicit: **OBSERVATION** **HYPOTHESIS** **EXPERIMENT** **FALSIFICATION** **CONCLUSION**
        cards=[("OBSERVATION",method.get("observation") or "—",False),("HYPOTHESIS",method.get("hypothesis") or "—",False),("EXPERIMENT",method.get("experiment") or "—",False),("FALSIFICATION",method.get("falsification") or "—",False),("CONCLUSION",method.get("conclusion") or "—",True)]
        body=[]
        for lbl,txt,wide in cards:
            body.append(f'<div class="cp-insight-card{" wide" if wide else ""}"><div class="label">{html.escape(lbl)}</div><div class="body">{html.escape(str(txt))}</div></div>')
        st.markdown('<div class="cp-method-grid">'+''.join(body)+'</div>',unsafe_allow_html=True)

    vals=[("Condition",condition),("Interpretation",interpretation or "—"),("Next action",next_action or "—")]; seen=set(); cards=[]
    for lbl,txt in vals:
        norm=" ".join(str(txt).split()).strip().lower()
        if norm in seen and norm not in {"","—"}: continue
        seen.add(norm); cards.append(f'<div class="cp-insight-card"><div class="label">{html.escape(lbl)}</div><div class="body">{html.escape(str(txt))}</div></div>')
    if cards: st.markdown('<div class="cp-insight-grid">'+''.join(cards)+'</div>',unsafe_allow_html=True)

    if strategy:
        ex=strategy.get("exploration_ratio"); pri=strategy.get("family_priorities") or {}; bits=[]
        if ex is not None: bits.append(f"Exploration {float(ex)*100:.0f}%")
        if pri: bits.append(_priority_text(pri))
        if confidence is not None:
            try: bits.append(f"Confidence {float(confidence)*100:.0f}%")
            except Exception: pass
        if bits: st.caption(" · ".join(bits))
    plan=entry.get("next_discovery_plan") if isinstance(entry.get("next_discovery_plan"),dict) else {}
    if plan:
        with st.expander("Next Discovery Plan",expanded=False):
            if plan.get("objective"): st.markdown(f"**Objective**  \n{plan.get('objective')}")
            if plan.get("freeze"): st.markdown("**Freeze:** "+" · ".join(str(x) for x in plan.get("freeze") or []))
            if plan.get("change"): st.markdown("**Change:** "+" · ".join(str(x) for x in plan.get("change") or []))
            if plan.get("falsification"): st.markdown(f"**Falsification:** {plan.get('falsification')}")
            if plan.get("do_not_do"): st.caption("Do not: "+str(plan.get("do_not_do")))
    if entry.get("next_cycle_summary_feedback_requested"):
        if entry.get("learning_ready"): st.success(f"Next Discovery learning READY · exposure {entry.get('feedback_exposure')}/{entry.get('feedback_limit') or '∞'}")
        elif entry.get("feedback_exhausted"): st.warning("Research feedback budget exhausted for this stage/dataset contract.")
        else: st.warning("Next Discovery blocked until an actionable Scientist plan is committed.")
    proposals=entry.get("proposals") or []
    if proposals:
        with st.expander(f"Proposals · {len(proposals)}",expanded=False): st.dataframe(pd.DataFrame([_scientist_proposal_row(p) for p in proposals]),use_container_width=True,hide_index=True)

def progress_ui():
    """Live monitor with an operator-facing Scientist report beside research progress."""
    left,right=st.columns([3.2,1.25],gap="large")
    with left:
        bar = st.progress(0)
        status = st.empty()
        table_slot = st.empty()
        policy_slot = st.empty()
    with right:
        st.markdown('<div class="cp-scientist-title">LLM Scientist · live report</div>',unsafe_allow_html=True)
        scientist_slot=st.empty()
        scientist_slot.info("Scientist akan melaporkan kondisi research setelah setiap round. Tidak perlu mengetik chat.")
    result_rows=[]
    policy_rows=[]
    scientist_reports=[]

    def render_table():
        if not result_rows:
            table_slot.caption("Hasil model akan muncul di sini setelah tiap experiment selesai.")
            return
        df=pd.DataFrame(result_rows)
        preferred=["Exp","Round","Model","PASS","DD R","Worst DD","Recovery","Worst RF","PF","Exp R","Worst R","Positive folds","Stress 1.50","Plateau","Trades","Score","Fit s"]
        cols=[c for c in preferred if c in df.columns]
        table_slot.dataframe(df[cols],use_container_width=True,hide_index=True,height=min(520,82+35*len(df)))


    def render_policy_table():
        if not policy_rows:
            policy_slot.empty()
            return
        with policy_slot.container():
            st.markdown("**Policy Discovery · OOF selectivity search**")
            pdf=pd.DataFrame(policy_rows)
            preferred=["Policy #","PASS","DD R","Worst DD","Recovery","Worst RF","PF","Exp R","Worst R","Positive folds","Trades","Regime","Take","BUY","SELL","Margin","Entropy","Score"]
            cols=[c for c in preferred if c in pdf.columns]
            st.dataframe(pdf[cols],use_container_width=True,hide_index=True,height=min(430,82+35*len(pdf)))

    def render_scientist():
        if not scientist_reports:
            scientist_slot.info("Scientist sedang menunggu evidence walk-forward pertama.")
            return
        latest=scientist_reports[-1]
        with scientist_slot.container():
            _render_scientist_entry(latest,compact=True)

    def cb(p):
        msg=str(p.get("message","") or "")
        stage=p.get("stage")
        if stage in {"load","label"}: frac=.05 if stage=="load" else .10
        elif stage in {"agent_round","cv"}:
            cur=int(p.get("candidate_index",p.get("current",0))); total=int(p.get("candidate_total",p.get("total",1)))
            frac=.12+.68*min(1,cur/max(1,total))
        elif stage=="scientist": frac=.75
        elif stage in {"policy_start","policy_oof"}: frac=.80
        elif stage=="policy_discovery":
            cur=int(p.get("current",0)); total=int(p.get("total",1)); frac=.80+.08*min(1,cur/max(1,total))
        elif stage=="winner": frac=.89
        elif stage=="onnx": frac=.92
        elif stage=="done": frac=1.0
        else: frac=.03
        bar.progress(min(100,int(frac*100)))
        status.markdown(f"**{msg or 'Menyiapkan…'}**")
        row=p.get("result_row")
        if isinstance(row,dict):
            key=(row.get("Exp"),row.get("Model")); existing={(r.get("Exp"),r.get("Model")) for r in result_rows}
            if key not in existing:
                result_rows.append(row); render_table()
        prow=p.get("policy_row")
        if isinstance(prow,dict):
            policy_rows.append(prow); render_policy_table()
        sci=p.get("scientist_update")
        if isinstance(sci,dict):
            scientist_reports.append(sci); render_scientist()

    status.markdown("**Menyiapkan…**"); render_table(); render_policy_table(); render_scientist()
    return bar,status,table_slot,cb


def _scorecard_row(stage,category,kpi,actual,target="—",direction="",role="Diagnostic",status="INFO",kind="num"):
    return {"Stage":stage,"Category":category,"KPI":kpi,"Actual":_fmt(actual,kind) if actual is not None else "—","Target":target,"Direction":direction,"Role":role,"Status":status}


def _gate_status(actual, target, direction):
    try:
        a=float(actual); t=float(target)
        return "PASS" if (a>=t if direction==">=" else a<=t) else "FAIL"
    except Exception:
        return "INFO"


def _build_complete_kpi_rows(m: dict, cfg: dict) -> list[dict]:
    """Complete audit table. Acceptance roles are derived from current authority, never stale run score."""
    a=cfg.get("acceptance",{}); cv=m.get("cv_selection") or {}; rows=[]
    cv_acc=walk_forward_acceptance(cv,cfg) if cv else {"gates":[]}
    cv_map={g.get("name"):g for g in cv_acc.get("gates",[])}

    def add_cv(cat,label,key,gate_name=None,kind="num",role="Diagnostic / ranking"):
        actual=cv.get(key)
        g=cv_map.get(gate_name) if gate_name else None
        if g:
            target=g.get("threshold"); status="PASS" if g.get("passed") else "FAIL"; authority="CRITICAL" if g.get("severity")=="CRITICAL" else "MANDATORY"
            direction="<=" if "DD" in str(gate_name) or "CONCENTRATION" in str(gate_name) else ">="
            rows.append(_scorecard_row("Walk-forward",cat,label,actual,_fmt(target,kind),direction,authority,status,kind))
        else:
            rows.append(_scorecard_row("Walk-forward",cat,label,actual,"reference","",role,"INFO",kind))

    # Survival first, exactly as authority evaluates it.
    add_cv("1 · Survival","Median Max Drawdown","median_max_drawdown_r","CV_MEDIAN_MAX_DD","r2")
    add_cv("1 · Survival","Worst-fold Max Drawdown","worst_fold_max_drawdown_r","CV_WORST_FOLD_MAX_DD","r2")
    add_cv("1 · Survival","Median Recovery Factor","median_recovery_factor","CV_MEDIAN_RECOVERY")
    add_cv("1 · Survival","Worst-fold Recovery Factor","worst_fold_recovery_factor","CV_WORST_FOLD_RECOVERY")
    add_cv("2 · Economic","Median Profit Factor","median_profit_factor","CV_MEDIAN_PF")
    add_cv("2 · Economic","Overall Mean R","overall_expectancy_r","CV_OVERALL_EXPECTANCY","r")
    add_cv("2 · Economic","Median Mean R","median_expectancy_r","CV_MEDIAN_EXPECTANCY","r")
    add_cv("2 · Economic","Worst-fold Expectancy","worst_expectancy_r","CV_WORST_EXPECTANCY","r")
    add_cv("2 · Economic","Validation trades","total_validation_trades","CV_MIN_TRADES","int")
    add_cv("3 · Robustness","Positive folds","positive_fold_ratio","CV_POSITIVE_FOLD_RATIO","pct")
    add_cv("3 · Robustness","Positive months","median_positive_month_ratio","CV_POSITIVE_MONTH_RATIO","pct")
    add_cv("3 · Robustness","Positive quarters","median_positive_quarter_ratio","CV_POSITIVE_QUARTER_RATIO","pct")
    add_cv("3 · Robustness","Regime concentration","median_regime_concentration","CV_REGIME_CONCENTRATION","pct")
    add_cv("3 · Robustness","Top-10% win concentration","median_top10_win_profit_share","CV_TOP10_WIN_CONCENTRATION","pct")
    add_cv("4 · Stress","Spread ×1.25 Expectancy","median_stress_x1_25_expectancy_r","CV_STRESS_SPREAD_X1.25_EXPECTANCY","r")
    add_cv("4 · Stress","Spread ×1.50 Expectancy","median_stress_x1_50_expectancy_r","CV_STRESS_SPREAD_X1.50_EXPECTANCY","r")
    add_cv("4 · Stress","Threshold plateau","median_threshold_plateau","CV_TAKE_THRESHOLD_PLATEAU","pct")

    for cat,label,key,kind in [
        ("5 · Diagnostics","Total validation R","total_validation_r","r2"),
        ("5 · Diagnostics","Expectancy dispersion","expectancy_std_r","r"),
        ("5 · Diagnostics","PF dispersion","profit_factor_std","num"),
        ("5 · Diagnostics","Win rate","median_win_rate","pct"),
        ("5 · Diagnostics","Payoff ratio","median_payoff_ratio","num"),
        ("5 · Diagnostics","Median trade","median_trade_r","r"),
        ("5 · Diagnostics","Daily CVaR / Expected Shortfall 95% (gate)","median_daily_cvar95_r","r"),
        ("5 · Diagnostics","Per-trade CVaR 95% (legacy diagnostic)","median_cvar95_r","r"),
        ("5 · Diagnostics","Sharpe Ratio","median_sharpe_ratio","num"),
        ("5 · Diagnostics","Sortino Ratio","median_sortino_ratio","num"),
        ("5 · Diagnostics","Calmar / MAR","median_calmar_mar_ratio","num"),
        ("5 · Diagnostics","PSR","median_probabilistic_sharpe_ratio","pct"),
        ("5 · Diagnostics","DSR","median_deflated_sharpe_ratio","pct"),
        ("5 · Diagnostics","Ulcer Index","median_ulcer_index_r","r2"),
        ("5 · Diagnostics","Max losing streak","median_max_losing_streak","int"),
        ("5 · Diagnostics","Underwater trades","median_max_underwater_trades","int"),
        ("6 · Classification","Balanced accuracy","mean_balanced_accuracy","pct"),
        ("6 · Classification","Macro F1","mean_macro_f1","pct"),
        ("6 · Classification","Log loss","mean_log_loss","num"),
        ("6 · Classification","Brier score","mean_brier_score","num"),
        ("6 · Classification","Calibration error","mean_expected_calibration_error","pct"),
    ]:
        add_cv(cat,label,key,None,kind)

    # Locked/fresh holdout: re-evaluate against CURRENT hierarchy.
    rep=m.get("kpi_report") or {}; tm=rep.get("locked_test") or {}
    if tm:
        lock_acc=locked_test_acceptance(rep,cfg)
        gate_map={g.get("name"):g for g in lock_acc.get("gates",[])}
        def locked(cat,label,actual,gate_name=None,kind="num"):
            g=gate_map.get(gate_name) if gate_name else None
            if g:
                rows.append(_scorecard_row("Locked / fresh holdout",cat,label,actual,_fmt(g.get("threshold"),kind),"",g.get("severity") or "MANDATORY","PASS" if g.get("passed") else "FAIL",kind))
            else:
                rows.append(_scorecard_row("Locked / fresh holdout",cat,label,actual,"reference","","Diagnostic","INFO",kind))
        locked("1 · Survival","Max Drawdown",tm.get("max_drawdown_r"),"TEST_MAX_DRAWDOWN","r2")
        locked("1 · Survival","Recovery Factor",tm.get("recovery_factor"),"TEST_RECOVERY_FACTOR")
        locked("2 · Economic","Profit Factor",tm.get("profit_factor"),"TEST_PROFIT_FACTOR")
        locked("2 · Economic","Expectancy",tm.get("expectancy_r"),"TEST_EXPECTANCY","r")
        locked("2 · Economic","Trades",tm.get("trades"),"TEST_MIN_TRADES","int")
        temporal=rep.get("temporal_stability") or {}; regime=rep.get("regime") or {}; stress=rep.get("stress") or {}; cls=rep.get("classification") or {}; parity=rep.get("onnx_parity") or {}
        locked("3 · Robustness","Positive months",temporal.get("positive_month_ratio"),"TEST_POSITIVE_MONTH_RATIO","pct")
        locked("3 · Robustness","Positive quarters",temporal.get("positive_quarter_ratio"),"TEST_POSITIVE_QUARTER_RATIO","pct")
        locked("3 · Robustness","Regime concentration",regime.get("dominant_positive_regime_share"),"TEST_REGIME_CONCENTRATION","pct")
        locked("3 · Robustness","Top-10% win concentration",tm.get("top10_win_profit_share"),"TEST_TOP10_WIN_CONCENTRATION","pct")
        sp=stress.get("spread") or {}
        locked("4 · Stress","Spread ×1.25 Expectancy",(sp.get("spread_x1.25") or {}).get("expectancy_r"),"STRESS_SPREAD_X1.25_EXPECTANCY","r")
        locked("4 · Stress","Spread ×1.50 Expectancy",(sp.get("spread_x1.50") or {}).get("expectancy_r"),"STRESS_SPREAD_X1.50_EXPECTANCY","r")
        locked("4 · Stress","Threshold plateau",stress.get("profitable_threshold_variant_ratio"),"TAKE_THRESHOLD_PLATEAU","pct")
        locked("5 · Deployment","Python ↔ ONNX max abs error",parity.get("max_abs_error"),"ONNX_PARITY","sci")
        for label,key,kind in [("Balanced accuracy","balanced_accuracy","pct"),("Macro F1","macro_f1","pct"),("Log loss","log_loss","num"),("Brier score","brier_score","num"),("Calibration error","expected_calibration_error","pct")]:
            locked("6 · Classification",label,cls.get(key),None,kind)
    return rows

def _render_human_kpi_diagnostics(report: dict):
    tq=report.get("locked_test") or {}; ts=report.get("temporal_stability") or {}; rg=report.get("regime") or {}; cls=report.get("classification") or {}; stress=report.get("stress") or {}
    t1,t2,t3,t4,t5=st.tabs(["Trade quality","Time stability","Regime","Calibration","Stress"])
    with t1:
        data=[("Win rate",_fmt(tq.get("win_rate"),"pct")),("Average win",_fmt(tq.get("avg_win_r"),"r")),("Average loss",_fmt(tq.get("avg_loss_r"),"r")),("Payoff ratio",_fmt(tq.get("payoff_ratio"))),("Median trade",_fmt(tq.get("median_trade_r"),"r")),("Max losing streak",_fmt(tq.get("max_losing_streak"),"int")),("Max underwater trades",_fmt(tq.get("max_underwater_trades"),"int")),("Daily CVaR / ES 95%",_fmt(tq.get("daily_cvar95_r"),"r")),("Per-trade CVaR 95%",_fmt(tq.get("cvar95_r"),"r")),("Downside deviation",_fmt(tq.get("downside_deviation_r"),"r")),("Top-10% win share",_fmt(tq.get("top10_win_profit_share"),"pct"))]
        st.dataframe(pd.DataFrame(data,columns=["KPI","Value"]),use_container_width=True,hide_index=True)
    with t2:
        data=[("Active months",_fmt(ts.get("active_months"),"int")),("Positive months",_fmt(ts.get("positive_month_ratio"),"pct")),("Median month",_fmt(ts.get("median_month_r"),"r2")),("Worst month",_fmt(ts.get("worst_month_r"),"r2")),("Longest negative-month streak",_fmt(ts.get("longest_negative_month_streak"),"int")),("Active quarters",_fmt(ts.get("active_quarters"),"int")),("Positive quarters",_fmt(ts.get("positive_quarter_ratio"),"pct")),("Median quarter",_fmt(ts.get("median_quarter_r"),"r2")),("Worst quarter",_fmt(ts.get("worst_quarter_r"),"r2"))]
        st.dataframe(pd.DataFrame(data,columns=["KPI","Value"]),use_container_width=True,hide_index=True)
    with t3:
        regime_rows=[]
        for name in ("TREND","RANGE","SHOCK","TRANSITION"):
            rr=rg.get(name) or {}; regime_rows.append({"Regime":name,"Trades":rr.get("trades"),"PF":round(float(rr.get("profit_factor",0)),3),"Exp R":round(float(rr.get("expectancy_r",0)),4),"Total R":round(float(rr.get("total_r",0)),2),"DD R":round(float(rr.get("max_drawdown_r",0)),2),"Recovery":round(float(rr.get("recovery_factor",0)),2)})
        st.dataframe(pd.DataFrame(regime_rows),use_container_width=True,hide_index=True)
        st.caption(f"Dominant positive-regime share: {_fmt(rg.get('dominant_positive_regime_share'),'pct')}")
    with t4:
        data=[("Balanced accuracy",_fmt(cls.get("balanced_accuracy"),"pct")),("Macro F1",_fmt(cls.get("macro_f1"),"pct")),("Log loss",_fmt(cls.get("log_loss"))),("Brier score",_fmt(cls.get("brier_score"))),("Calibration error",_fmt(cls.get("expected_calibration_error"),"pct"))]
        st.dataframe(pd.DataFrame(data,columns=["KPI","Value"]),use_container_width=True,hide_index=True)
        cb=report.get("confidence_buckets") or []
        if cb:
            view=[]
            for r in cb: view.append({"Confidence":f"{float(r.get('confidence_min',0))*100:.0f}–{float(r.get('confidence_max',0))*100:.0f}%","Trades":r.get("trades"),"PF":round(float(r.get("profit_factor",0)),3),"Exp R":round(float(r.get("expectancy_r",0)),4),"Win rate":f"{float(r.get('win_rate',0))*100:.1f}%"})
            st.caption("Trading quality by model confidence")
            st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True)
    with t5:
        sp=stress.get("spread") or {}; rows=[]
        for key,val in sp.items(): rows.append({"Scenario":key.replace("spread_x","Spread ×"),"PF":round(float(val.get("profit_factor",0)),3),"Exp R":round(float(val.get("expectancy_r",0)),4),"DD R":round(float(val.get("max_drawdown_r",0)),2),"Recovery":round(float(val.get("recovery_factor",0)),2),"Trades":int(val.get("trades",0))})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        sens=stress.get("take_threshold_sensitivity") or []
        if sens:
            st.caption("Take-threshold sensitivity")
            st.dataframe(pd.DataFrame([{ "Threshold":r.get("take_threshold"),"PF":round(float(r.get("profit_factor",0)),3),"Exp R":round(float(r.get("expectancy_r",0)),4),"DD R":round(float(r.get("max_drawdown_r",0)),2),"Trades":int(r.get("trades",0))} for r in sens]),use_container_width=True,hide_index=True)
        st.caption(f"Profitable threshold plateau: {_fmt(stress.get('profitable_threshold_variant_ratio'),'pct')}")


def _run_identity(run_dir: Path, m: dict) -> dict:
    dp=dict(m.get("dataset_provenance") or {})
    if dp.get("period") is None:
        lp=run_dir/"labeled_dataset.csv"
        if lp.exists():
            try:
                h=read_csv_auto(lp,usecols=["symbol","period","signal_time"])
                if not h.empty:
                    dp={"symbol":str(h["symbol"].iloc[0]),"period":int(h["period"].iloc[0]),"timeframe":period_label(h["period"].iloc[0]),"source_start":str(h["signal_time"].iloc[0]),"source_end":str(h["signal_time"].iloc[-1])}
            except Exception:
                pass
    period=dp.get("period",m.get("period")); tf=dp.get("timeframe") or m.get("timeframe") or (period_label(period) if period is not None else "?")
    return {"symbol":dp.get("symbol") or m.get("symbol") or "?","period":period,"timeframe":tf,"start":dp.get("source_start") or m.get("source_start"),"end":dp.get("source_end") or m.get("source_end")}


def _run_label(run_dir: Path) -> str:
    try:
        m=load_manifest(run_dir); ident=_run_identity(run_dir,m); status=str(m.get("status","?")); model=str(m.get("model_name") or "?")
        return f"{ident['symbol']} {ident['timeframe']}  ·  {status}  ·  {model}  ·  {run_dir.name}"
    except Exception:
        return run_dir.name


def _route_steps(m: dict) -> list[tuple[str,str]]:
    return route_steps(m)


def _render_route(m: dict):
    state_class={"done":"done","active":"active","fail":"fail","todo":""}
    icon={"done":"✓","active":"→","fail":"✕","todo":"·"}
    parts=[]
    for label,state in _route_steps(m):
        cls=state_class[state]
        parts.append(f'<span class="cp-route-step {cls}">{icon[state]} {label}</span>')
    st.markdown('<div class="cp-route">'+''.join(parts)+'</div>',unsafe_allow_html=True)

def _gate_map(acc: dict) -> dict:
    return {str(g.get("name")):bool(g.get("passed")) for g in (acc.get("gates") or [])}


def _status_for(gm: dict, names: list[str]) -> bool:
    present=[gm[n] for n in names if n in gm]
    return all(present) if present else True


def _kpi_item(label,value,good=True):
    cls="good" if good else "bad"
    return f'<div class="cp-kpi-item {cls}"><div class="v">{value}</div><div class="l">{label}</div></div>'


def _kpi_group(title,kind,state,items):
    ss="pass" if state else "fail"; state_text="PASS" if state else "FAIL"
    return f'<div class="cp-kpi-group {kind}"><div class="cp-kpi-head"><span class="cp-kpi-title">{title}</span><span class="cp-kpi-state {ss}">{state_text}</span></div><div class="cp-kpi-grid">{"".join(items)}</div></div>'


def render_kpi_authority(m: dict,cfg: dict):
    cv=m.get("cv_selection") or {}; report=m.get("kpi_report") or {}; locked=bool(report and m.get("locked_test_trading"))
    acc=locked_test_acceptance(report,cfg) if locked else walk_forward_acceptance(cv,cfg)
    gm=_gate_map(acc); passed=bool(acc.get("passed")); first=acc.get("first_failed_gate") or "—"; score=cv.get("selection_score")
    score_txt=f"{float(score):+.1f}" if score is not None else "—"
    stage="Locked/Fresh Holdout" if locked else "Walk-forward"
    st.markdown(f'<div class="cp-verdict {"pass" if passed else "fail"}"><div><strong>{"PASS" if passed else "FAIL"} · {stage} KPI authority</strong><div class="cp-subtle">First failed gate: {first}</div></div><div class="cp-rank">Ranking score: {score_txt} · score tidak punya authority PASS</div></div>',unsafe_allow_html=True)
    tm=m.get("locked_test_trading") or {}; temporal=(report.get("temporal_stability") or {}); regime=(report.get("regime") or {}); stress=(report.get("stress") or {})
    if locked:
        dd=tm.get("max_drawdown_r"); rec=tm.get("recovery_factor"); pf=tm.get("profit_factor"); exp=tm.get("expectancy_r"); trades=tm.get("trades")
        pm=temporal.get("positive_month_ratio"); pq=temporal.get("positive_quarter_ratio"); rg=regime.get("dominant_positive_regime_share")
        s125=((stress.get("spread") or {}).get("spread_x1.25") or {}).get("expectancy_r"); s150=((stress.get("spread") or {}).get("spread_x1.50") or {}).get("expectancy_r"); plateau=stress.get("profitable_threshold_variant_ratio")
        surv_names=["TEST_MAX_DRAWDOWN","TEST_RECOVERY_FACTOR"]; econ_names=["TEST_PROFIT_FACTOR","TEST_EXPECTANCY","TEST_MIN_TRADES"]; rob_names=["TEST_POSITIVE_MONTH_RATIO","TEST_POSITIVE_QUARTER_RATIO","TEST_REGIME_CONCENTRATION","TEST_TOP10_WIN_CONCENTRATION"]; stress_names=["STRESS_SPREAD_X1.25_EXPECTANCY","STRESS_SPREAD_X1.50_EXPECTANCY","TAKE_THRESHOLD_PLATEAU"]
    else:
        dd=cv.get("median_max_drawdown_r"); rec=cv.get("median_recovery_factor"); pf=cv.get("median_profit_factor"); exp=cv.get("median_expectancy_r"); trades=cv.get("total_validation_trades")
        pm=cv.get("median_positive_month_ratio"); pq=cv.get("median_positive_quarter_ratio"); rg=cv.get("median_regime_concentration"); s125=cv.get("median_stress_x1_25_expectancy_r"); s150=cv.get("median_stress_x1_50_expectancy_r"); plateau=cv.get("median_threshold_plateau")
        surv_names=["CV_MEDIAN_MAX_DD","CV_WORST_FOLD_MAX_DD","CV_MEDIAN_RECOVERY","CV_WORST_FOLD_RECOVERY"]; econ_names=["CV_MEDIAN_PF","CV_MEDIAN_EXPECTANCY","CV_WORST_EXPECTANCY","CV_MIN_TRADES"]; rob_names=["CV_POSITIVE_FOLD_RATIO","CV_POSITIVE_MONTH_RATIO","CV_POSITIVE_QUARTER_RATIO","CV_REGIME_CONCENTRATION","CV_TOP10_WIN_CONCENTRATION"]; stress_names=["CV_STRESS_SPREAD_X1.25_EXPECTANCY","CV_STRESS_SPREAD_X1.50_EXPECTANCY","CV_TAKE_THRESHOLD_PLATEAU"]
    a,b=st.columns(2)
    with a:
        surv_items=[_kpi_item("Max DD",_fmt(dd,"r2"),_status_for(gm,[surv_names[0]])),_kpi_item("Recovery Factor",_fmt(rec),_status_for(gm,["TEST_RECOVERY_FACTOR" if locked else "CV_MEDIAN_RECOVERY"]))]
        if locked:
            surv_items += [_kpi_item("Risk order","DD → RF → PF",True),_kpi_item("Compensation","PF tidak bisa menutup risk FAIL",True)]
        else:
            surv_items += [_kpi_item("Worst fold DD",_fmt(cv.get("worst_fold_max_drawdown_r"),"r2"),_status_for(gm,["CV_WORST_FOLD_MAX_DD"])),_kpi_item("Worst fold RF",_fmt(cv.get("worst_fold_recovery_factor")),_status_for(gm,["CV_WORST_FOLD_RECOVERY"]))]
        st.markdown(_kpi_group("1 · SURVIVAL · PRIORITAS TERTINGGI","survival",_status_for(gm,surv_names),surv_items),unsafe_allow_html=True)
        rob_items=[]
        if not locked:
            rob_items.append(_kpi_item("Positive folds",_fmt(cv.get("positive_fold_ratio"),"pct"),_status_for(gm,["CV_POSITIVE_FOLD_RATIO"])))
        rob_items += [_kpi_item("Positive months",_fmt(pm,"pct"),_status_for(gm,["TEST_POSITIVE_MONTH_RATIO" if locked else "CV_POSITIVE_MONTH_RATIO"])),_kpi_item("Positive quarters",_fmt(pq,"pct"),_status_for(gm,["TEST_POSITIVE_QUARTER_RATIO" if locked else "CV_POSITIVE_QUARTER_RATIO"])),_kpi_item("Regime concentration",_fmt(rg,"pct"),_status_for(gm,["TEST_REGIME_CONCENTRATION" if locked else "CV_REGIME_CONCENTRATION"]))]
        st.markdown(_kpi_group("3 · ROBUSTNESS","robustness",_status_for(gm,rob_names),rob_items),unsafe_allow_html=True)
    with b:
        econ_items=[_kpi_item("Profit Factor",_fmt(pf),_status_for(gm,["TEST_PROFIT_FACTOR" if locked else "CV_MEDIAN_PF"])),_kpi_item("Expectancy",_fmt(exp,"r"),_status_for(gm,["TEST_EXPECTANCY" if locked else "CV_MEDIAN_EXPECTANCY"])),_kpi_item("Trades",_fmt(trades,"int"),_status_for(gm,["TEST_MIN_TRADES" if locked else "CV_MIN_TRADES"]))]
        if not locked:
            econ_items.append(_kpi_item("Worst-fold Exp",_fmt(cv.get("worst_expectancy_r"),"r"),_status_for(gm,["CV_WORST_EXPECTANCY"])))
        else:
            econ_items.append(_kpi_item("PF rule","Tetap wajib tinggi",True))
        st.markdown(_kpi_group("2 · ECONOMIC EDGE","economic",_status_for(gm,econ_names),econ_items),unsafe_allow_html=True)
        stress_items=[_kpi_item("Spread ×1.25 Exp",_fmt(s125,"r"),_status_for(gm,[stress_names[0]])),_kpi_item("Spread ×1.50 Exp",_fmt(s150,"r"),_status_for(gm,[stress_names[1]])),_kpi_item("Threshold plateau",_fmt(plateau,"pct"),_status_for(gm,[stress_names[2]])),_kpi_item("Authority","Semua gate wajib PASS",True)]
        st.markdown(_kpi_group("4 · EXECUTION / STRESS","stress",_status_for(gm,stress_names),stress_items),unsafe_allow_html=True)
    return acc


def render_run(run_dir: Path, cfg: dict):
    mp=run_dir/"model_manifest.json"
    if not mp.exists():
        st.warning("Manifest belum ada."); return
    m=load_manifest(run_dir); status=str(m.get("status","UNKNOWN"))
    if status=="FEATURE_LABEL_AUDIT_READY":
        rp=run_dir/"feature_label_audit.json"
        if rp.exists():
            audit=json.loads(rp.read_text(encoding="utf-8")); ov=audit.get("policy_overselection") or {}; base=audit.get("label_base") or {}
            a,b,c,d=st.columns(4); a.metric("OOF policy trades",int(ov.get("policy_total_validation_trades",0))); b.metric("Regime concentration",_fmt(ov.get("policy_regime_concentration"),"pct")); c.metric("Base labeled rows",int(base.get("rows",0))); d.metric("Hypotheses",len(audit.get("guided_hypotheses") or []))
            st.warning("Over-selection risk terdeteksi." if ov.get("suspected_overselection") else "Tidak ada over-selection flag utama, tetapi audit tetap wajib dibaca sebagai OOF diagnosis.")
            with st.expander("Feature drift / importance / label sensitivity",expanded=False):
                tabs=st.tabs(["Feature drift","Feature importance","Label sensitivity","Redundancy"])
                with tabs[0]: st.dataframe(pd.DataFrame(audit.get("feature_drift") or []),use_container_width=True,hide_index=True)
                with tabs[1]: st.dataframe(pd.DataFrame(audit.get("feature_importance_stability") or []),use_container_width=True,hide_index=True)
                with tabs[2]: st.dataframe(pd.DataFrame(audit.get("label_sensitivity") or []),use_container_width=True,hide_index=True)
                with tabs[3]: st.dataframe(pd.DataFrame(audit.get("feature_redundancy") or []),use_container_width=True,hide_index=True)
        with st.expander("Artifacts",expanded=False):
            for name in ["REPORT.md","model_manifest.json","feature_label_audit.json","guided_hypotheses.json"]:
                fp=run_dir/name
                if fp.exists(): st.download_button(name,data=fp.read_bytes(),file_name=name,use_container_width=True,key=f"audit_dl_{run_dir.name}_{name}")
        return
    render_kpi_authority(m,cfg)

    decision_policy=m.get("decision_policy") or {}
    if decision_policy:
        with st.expander("Decision Policy · CP_POLICY_V1",expanded=False):
            pcols=st.columns(6); pcols[0].metric("Take",_fmt(decision_policy.get("take_threshold"))); pcols[1].metric("BUY",_fmt(decision_policy.get("buy_threshold"))); pcols[2].metric("SELL",_fmt(decision_policy.get("sell_threshold"))); pcols[3].metric("Margin",_fmt(decision_policy.get("directional_margin"))); pcols[4].metric("Entropy",_fmt(decision_policy.get("max_entropy"))); pcols[5].metric("Regime",str(decision_policy.get("regime_mode","ALL")))

    with st.expander("KPI detail · full scorecard",expanded=False):
        rows=_build_complete_kpi_rows(m,cfg)
        if rows:
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(640,90+31*len(rows)))
        st.caption("Composite Score hanya ranking. PASS/FAIL berasal dari hierarchical KPI authority di atas.")
        report=m.get("kpi_report") or {}
        if report and m.get("locked_test_trading"):
            _render_human_kpi_diagnostics(report)

    board_path=run_dir/"cv_leaderboard.json"
    if board_path.exists():
        with st.expander("Research leaderboard",expanded=False):
            board=pd.read_json(board_path); preferred=["round","name","family","cv_gate_pass","cv_first_failed_gate","median_max_drawdown_r","worst_fold_max_drawdown_r","median_recovery_factor","worst_fold_recovery_factor","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","positive_fold_ratio","median_stress_x1_50_expectancy_r","total_validation_trades","selection_score","total_fit_seconds","take_threshold"]
            if "family" in board.columns:
                board["family"]=board["family"].map(_family_display_name)
            cols=[x for x in preferred if x in board.columns]; st.dataframe(board[cols],use_container_width=True,hide_index=True,height=480)

    policy_board=run_dir/"policy_leaderboard.json"
    if policy_board.exists():
        with st.expander("Policy Discovery leaderboard",expanded=False):
            try:
                pdata=json.loads(policy_board.read_text(encoding="utf-8")); rows=[]
                for r in pdata:
                    pol=r.get("policy") or {}; rows.append({"PASS":r.get("cv_gate_pass"),"First fail":(r.get("cv_acceptance") or {}).get("first_failed_gate"),"DD":r.get("median_max_drawdown_r"),"Worst DD":r.get("worst_fold_max_drawdown_r"),"Recovery":r.get("median_recovery_factor"),"PF":r.get("median_profit_factor"),"Overall R":r.get("overall_expectancy_r"),"Median R":r.get("median_expectancy_r"),"Worst R":r.get("worst_expectancy_r"),"Score":r.get("selection_score"),"Regime":pol.get("regime_mode"),"Take":pol.get("take_threshold")})
                st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(500,90+32*len(rows)))
            except Exception as e:
                st.warning(str(e))

    journal=run_dir/"scientist_journal.json"
    if journal.exists():
        entries=json.loads(journal.read_text(encoding="utf-8"))
        if entries:
            with st.expander("LLM Scientist · research journal",expanded=False):
                for i,e in enumerate(entries):
                    if i: st.divider()
                    _render_scientist_entry(e,compact=False)

    with st.expander("Artifacts",expanded=False):
        cols=st.columns(6)
        for col,(name,label) in zip(cols,[("challenger.onnx","ONNX"),("REPORT.md","Report"),("model_manifest.json","Manifest"),("cv_leaderboard.json","Leaderboard"),("kpi_report.json","KPI report"),("kpi_acceptance.json","KPI acceptance")]):
            fp=run_dir/name
            if fp.exists(): col.download_button(label,data=fp.read_bytes(),file_name=name,use_container_width=True,key=f"dl_{run_dir.name}_{name}")
            else: col.button(label,disabled=True,use_container_width=True,key=f"missing_{run_dir.name}_{name}")

    if status=="ELIGIBLE_CHALLENGER":
        with st.expander("Install Challenger shadow",expanded=False):
            art=m.get("challenger_artifact") or {}
            st.caption("Research releases immutable human-readable Challenger files. Publishing copies those files to MT5 models only; Python never changes the EA Challenger input for you.")
            if art:
                st.code("\n".join(f"{k}: {v}" for k,v in (art.get("manual_ea_parameters") or {}).items() if v),language=None)
            terminals=detect_terminal_files_dirs(); target=None
            if terminals:
                sel=st.selectbox("Terminal target",[str(x) for x in terminals],key=f"shadow_target_{run_dir.name}"); target=Path(sel)
            else:
                text=st.text_input("MQL5 Files folder",key=f"shadow_manual_{run_dir.name}"); target=Path(text) if text.strip() else None
            if st.button("PUBLISH CHALLENGER FILES TO MT5",disabled=target is None,use_container_width=True,key=f"install_shadow_{run_dir.name}"):
                try:
                    res=publish_challenger_to_terminal(run_dir,target,m)
                    st.success(f"{res.get('challenger_id')} published. EA inputs were not modified.")
                    params=res.get("manual_ea_parameters") or {}
                    if params: st.code("\n".join(f"{k}: {v}" for k,v in params.items() if v),language=None)
                except Exception as e:
                    st.error(str(e))

def evidence_editor(run_dir: Path, cfg: dict):
    old=load_evidence(run_dir); mt=old.get("mt5_parity",{}); stt=old.get("strategy_tester",{}); sh=old.get("shadow_forward",{}); comp=sh.get("champion",{})
    st.markdown("#### Evidence yang dibaca Supervisor")
    a,b,c=st.columns(3)
    mt_pass=a.checkbox("MT5 parity PASS",value=str(mt.get("status","")).upper()=="PASS")
    mt_rows=int(b.number_input("Parity rows",0,10000000,int(mt.get("rows",0)),100))
    mt_err=float(c.number_input("MT5 max abs error",0.0,1.0,float(mt.get("max_abs_error",0.0)),format="%.8f"))
    tester_pass=st.checkbox("Strategy Tester integration PASS",value=str(stt.get("status","")).upper()=="PASS")
    st.caption("Fresh shadow-forward Challenger")
    a,b,c,d,e=st.columns(5)
    sh_trades=int(a.number_input("Shadow trades",0,1000000,int(sh.get("trades",0)),10))
    sh_pf=float(b.number_input("Shadow PF",0.0,20.0,float(sh.get("profit_factor",0.0)),.05))
    sh_exp=float(c.number_input("Shadow expectancy R",-10.0,10.0,float(sh.get("expectancy_r",0.0)),.01))
    sh_dd=float(d.number_input("Shadow max DD R",0.0,10000.0,float(sh.get("max_drawdown_r",0.0)),1.0))
    sh_total=float(e.number_input("Shadow total R",-100000.0,100000.0,float(sh.get("total_r",0.0)),1.0))
    sh_rec=shadow_recovery_factor(sh_total,sh_dd)
    st.caption(f"Challenger Recovery Factor: {sh_rec:.3f}")
    registry=load_registry(APP_DIR)
    if registry.get("current"):
        st.caption("Same-window current Champion comparison")
        a,b,c,d=st.columns(4)
        cp=float(a.number_input("Champion shadow PF",0.0,20.0,float(comp.get("profit_factor",0.0)),.05))
        ce=float(b.number_input("Champion expectancy R",-10.0,10.0,float(comp.get("expectancy_r",0.0)),.01))
        cd=float(c.number_input("Champion max DD R",0.0,10000.0,float(comp.get("max_drawdown_r",0.0)),1.0))
        ct=float(d.number_input("Champion total R",-100000.0,100000.0,float(comp.get("total_r",0.0)),1.0))
        cr=shadow_recovery_factor(ct,cd)
        st.caption(f"Champion Recovery Factor: {cr:.3f}")
        champion_ev={"profit_factor":cp,"expectancy_r":ce,"max_drawdown_r":cd,"total_r":ct,"recovery_factor":cr}
    else: champion_ev=None
    shadow_preview={"trades":sh_trades,"profit_factor":sh_pf,"expectancy_r":sh_exp,"max_drawdown_r":sh_dd,"total_r":sh_total,"recovery_factor":sh_rec}
    sh_gate=shadow_acceptance(shadow_preview,cfg)
    sh_status=bool(sh_gate.get("passed"))
    if sh_gate.get("reasons"):
        st.caption("Shadow KPI pending: " + ", ".join(sh_gate["reasons"]))
    evidence={
        "mt5_parity":{"status":"PASS" if mt_pass else "PENDING","rows":mt_rows,"max_abs_error":mt_err},
        "strategy_tester":{"status":"PASS" if tester_pass else "PENDING"},
        "shadow_forward":{"status":"PASS" if sh_status else "PENDING","trades":sh_trades,"profit_factor":sh_pf,"expectancy_r":sh_exp,"max_drawdown_r":sh_dd,"total_r":sh_total,"recovery_factor":sh_rec},
    }
    if champion_ev: evidence["shadow_forward"]["champion"]=champion_ev
    if st.button("Save evidence + run Supervisor gates",type="primary",use_container_width=True):
        save_evidence(run_dir,evidence); state=assess_promotion(run_dir,cfg,APP_DIR); st.session_state.gov_state=state; st.rerun()


def governance_panel(run_dir: Path, cfg: dict):
    state=assess_promotion(run_dir,cfg,APP_DIR)
    st.markdown(f'<div class="cp-stage">Supervisor stage: {state["stage"]}</div>',unsafe_allow_html=True)
    for g in state["gates"]:
        (st.success if g["passed"] else st.warning)(f"{'PASS' if g['passed'] else 'WAIT'} · {g['name']} · {g['detail']}")
    promo_assessment=run_dir/"promotion_kpi_assessment.json"
    if promo_assessment.exists():
        st.download_button("Download promotion KPI assessment",data=promo_assessment.read_bytes(),file_name="promotion_kpi_assessment.json",use_container_width=True,key=f"promo_kpi_{run_dir.name}")
    evidence_editor(run_dir,cfg)
    state=assess_promotion(run_dir,cfg,APP_DIR)
    st.divider(); st.markdown("#### Champion promotion")
    if state.get("promotion_ready"):
        st.success("Promotion gates PASS. Open the Champion page, select this Challenger, and use PROMOTE SELECTED CHALLENGER.")
    else:
        st.caption("Promotion remains blocked until all deterministic gates PASS. Promotion action is centralized on the Champion page to avoid duplicate authority.")



def apply_h1_survival_profile(cfg: dict):
    a=cfg.setdefault("acceptance",{})
    a.update({
        "profile":"SURVIVAL_H1_V1",
        "min_test_trades":50,
        "min_profit_factor":1.35,
        "min_expectancy_r":0.15,
        "max_drawdown_r":12.0,
        "min_recovery_factor":2.0,
        "cv_min_validation_trades":90,
        "cv_min_median_profit_factor":1.25,
        "cv_min_median_expectancy_r":0.10,
        "cv_min_worst_expectancy_r":0.0,
        "cpcv_min_worst_expectancy_r":0.0,
        "worst_expectancy_epsilon":1e-9,
        "cpcv_worst_expectancy_epsilon":1e-9,
        "cv_min_positive_fold_ratio":0.66,
        "cv_min_median_recovery_factor":1.50,
        "cv_max_worst_fold_drawdown_r":18.0,
        "cv_min_worst_fold_recovery_factor":1.0,
        "schema":"KPI_V5_HIERARCHICAL",
        "min_positive_month_ratio":0.55,
        "min_positive_quarter_ratio":0.60,
        "max_dominant_positive_regime_share":0.75,
        "max_top10_win_profit_share":0.55,
        "sensitivity_min_profitable_ratio":0.66,
    })
    a.setdefault("stress_min_expectancy_r",{}).update({"spread_x1.25":0.08,"spread_x1.50":0.05})
    pc=cfg.setdefault("agent",{}).setdefault("promotion",{})
    pc.update({"min_shadow_trades":50,"min_shadow_profit_factor":1.35,"min_shadow_expectancy_r":0.15,"max_shadow_drawdown_r":12.0,"min_shadow_recovery_factor":2.0})
    return cfg


def _profile_summary(cfg: dict) -> str:
    a=cfg.get("acceptance",{})
    return (f"{a.get('profile','CUSTOM')} · CV PF ≥ {float(a.get('cv_min_median_profit_factor',0)):.2f} · "
            f"CV Exp ≥ {float(a.get('cv_min_median_expectancy_r',0)):.2f}R · Locked PF ≥ {float(a.get('min_profit_factor',0)):.2f} · "
            f"Locked Exp ≥ {float(a.get('min_expectancy_r',0)):.2f}R")


def _action_progress():
    bar=st.progress(0); status=st.empty(); table=st.empty(); rows=[]
    def cb(p):
        stage=str(p.get("stage", "")); msg=str(p.get("message", "") or "Working…")
        cur=float(p.get("current",0) or 0); total=max(1.0,float(p.get("total",1) or 1))
        if stage in {"load","policy_start"}: frac=.08
        elif stage=="policy_oof": frac=.15+.25*min(1,cur/total)
        elif stage=="policy_discovery": frac=.40+.45*min(1,cur/total)
        elif stage in {"audit","guided"}: frac=.08+.84*min(1,cur/total)
        elif stage=="onnx": frac=.92
        elif stage=="done": frac=1.0
        else: frac=.05
        bar.progress(min(100,int(frac*100))); status.markdown(f"**{msg}**")
        prow=p.get("policy_row") or p.get("guided_row")
        if isinstance(prow,dict):
            rows.append(prow); table.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(430,90+32*len(rows)))
    return bar,status,cb


def render_next_action(run_dir: Path, cfg: dict):
    m=load_manifest(run_dir); ident=_run_identity(run_dir,m); route=route_for_manifest(m)
    action=route.get("action")
    def head(title,sub=""):
        st.markdown(f'<div class="cp-next"><div class="cp-next-title">Next action · {ident["symbol"]} {ident["timeframe"]}</div><div class="cp-next-main">{title}</div><div class="cp-next-sub">{sub}</div></div>',unsafe_allow_html=True)

    if action=="VALIDATE_FROZEN_MODEL_FRESH":
        auth=authority_research_meta(run_dir); cutoff=auth.get("cutoff") or m.get("source_raw_end") or m.get("source_end")
        rw=auth.get("window") or {}
        range_note=f" Research authority {rw.get('research_from','?')} → {rw.get('research_to','?')}; fresh strictly > {cutoff}." if rw else ""
        head("VALIDATE FROZEN MODEL ON NEWER DATA","CV PASS. Historical/retired holdout tidak boleh dipakai lagi."+range_note)
        fresh=resolve_dataset(f"fresh_model_{run_dir.name}")
        render_fresh_readiness(fresh,cutoff,cfg)
        if st.button("VALIDATE FROZEN MODEL · FRESH DATA",type="primary",disabled=fresh is None,use_container_width=True,key=f"fresh_model_btn_{run_dir.name}"):
            runtime=write_runtime_cfg(cfg,f"fresh_model_{run_dir.name}.json"); bar,slot,cb=_action_progress()
            try:
                res=validate_frozen_model_on_fresh_data(run_dir,fresh,runtime,RUNS_DIR,progress=cb); st.session_state.last_run=res["run"]; st.session_state.pending_run_select=Path(res["run"]).name; st.session_state.pending_nav="Pipeline"; bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e: slot.error(str(e))
        return

    if action=="RUN_OOF_POLICY":
        head("RUN OOF POLICY DISCOVERY","Locked test gagal. Model dibekukan; policy dicari hanya dari upstream OOF. Locked test lama tidak dibuka ulang.")
        src=authority_source_csv(run_dir)
        if src: st.caption(f"Immutable research source: `{src}`")
        else: st.error("source_window.csv authority tidak ditemukan; fail-closed.")
        if st.button("RUN OOF POLICY DISCOVERY",type="primary",disabled=src is None,use_container_width=True,key=f"post_policy_btn_{run_dir.name}"):
            runtime=write_runtime_cfg(cfg,f"post_policy_{run_dir.name}.json"); bar,slot,cb=_action_progress()
            try:
                res=run_post_locked_policy_discovery(run_dir,src,runtime,RUNS_DIR,progress=cb,llm_api_key=st.session_state.llm_api_key); st.session_state.last_run=res["run"]; st.session_state.pending_run_select=Path(res["run"]).name; st.session_state.pending_nav="Pipeline"; bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e: slot.error(str(e))
        return

    if action=="VALIDATE_FROZEN_POLICY_FRESH":
        auth=authority_research_meta(run_dir); cutoff=auth.get("cutoff") or m.get("source_raw_end") or m.get("source_end")
        rw=auth.get("window") or {}
        range_note=f"Research authority {rw.get('research_from','?')} → {rw.get('research_to','?')} · " if rw else ""
        head("VALIDATE FROZEN MODEL + POLICY ON NEWER DATA",f"OOF policy PASS. {range_note}fresh harus strictly > {cutoff}.")
        fresh=resolve_dataset(f"fresh_{run_dir.name}")
        render_fresh_readiness(fresh,cutoff,cfg)
        if st.button("VALIDATE POLICY · FRESH DATA",type="primary",disabled=fresh is None,use_container_width=True,key=f"fresh_btn_{run_dir.name}"):
            runtime=write_runtime_cfg(cfg,f"fresh_{run_dir.name}.json"); bar,slot,cb=_action_progress()
            try:
                res=validate_frozen_policy_on_fresh_data(run_dir,fresh,runtime,RUNS_DIR,progress=cb); st.session_state.last_run=res["run"]; st.session_state.pending_run_select=Path(res["run"]).name; st.session_state.pending_nav="Pipeline"; bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e: slot.error(str(e))
        return

    if action=="RUN_FEATURE_LABEL_AUDIT":
        head("RUN FEATURE + LABEL AUDIT","Ini stage nyata, bukan report mati. Audit hanya memakai upstream pre-holdout/OOF untuk feature drift, redundancy, label sensitivity, dan policy over-selection.")
        src=authority_source_csv(run_dir)
        if src: st.caption(f"Immutable research source: `{src}`")
        else: st.error("source_window.csv authority tidak ditemukan; fail-closed.")
        if st.button("RUN FEATURE + LABEL AUDIT",type="primary",disabled=src is None,use_container_width=True,key=f"audit_btn_{run_dir.name}"):
            bar,slot,cb=_action_progress()
            try:
                runtime=write_runtime_cfg(cfg,f"audit_authority_{run_dir.name}.json"); res=run_feature_label_audit(run_dir,src,runtime,RUNS_DIR,progress=cb); st.session_state.last_run=res["run"]; st.session_state.pending_run_select=Path(res["run"]).name; st.session_state.pending_guided_run=Path(res["run"]).name; st.session_state.pending_nav="Guided Research"; bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e: slot.error(str(e))
        return

    if action=="OPEN_GUIDED_RESEARCH":
        head("OPEN GUIDED RESEARCH","Audit selesai. Guided Research punya halaman sendiri dan tidak lagi mengirim operator ke form Label/Advanced.")
        if st.button("OPEN GUIDED RESEARCH",type="primary",use_container_width=True,key=f"open_guided_{run_dir.name}"):
            st.session_state.pending_guided_run=run_dir.name; st.session_state.pending_nav="Guided Research"; st.rerun()
        return

    if action=="START_NEW_GENERATION":
        head("START NEW GENERATION RESEARCH","Guided OOF menemukan hypothesis yang lolos authority. Full model research berikutnya akan memakai config itu dan sengaja SKIP historical locked test; next validation wajib fresh data.")
        if st.button("OPEN GUIDED RESEARCH",type="primary",use_container_width=True,key=f"open_guided_ready_{run_dir.name}"):
            st.session_state.pending_guided_run=run_dir.name; st.session_state.pending_nav="Guided Research"; st.rerun()
        return

    if action=="MT5_VALIDATION":
        head("CONTINUE TO MT5 VALIDATION","Historical/fresh KPI PASS. Lanjut MT5 parity → Strategy Tester → fresh shadow → promotion.")
        return

    if action=="STOP_NEW_HYPOTHESIS":
        head("STOP · NEW HYPOTHESIS REQUIRED","Guided Feature/Label hypotheses juga gagal. Jangan memperbesar budget atau membuka holdout lama.")
        return

    head("NO AUTOMATIC ACTION","Status ini tidak punya route legal otomatis. Jangan improvisasi dari Advanced.")

def _strategy_optimizer_install_from_session():
    """Resolve the MT5 installation selected on Strategy Optimizer without sharing Research state."""
    installs=discover_mt5_installations()
    if installs:
        chosen=str(st.session_state.get("strategy_opt_mt5_installation") or "")
        for item in installs:
            if item.label==chosen:
                return item
        return installs[0]
    terminal=str(st.session_state.get("strategy_opt_terminal") or "").strip()
    meta=str(st.session_state.get("strategy_opt_metaeditor") or "").strip()
    data_dir=str(st.session_state.get("strategy_opt_data_dir") or "").strip()
    if terminal and meta and data_dir:
        from strategy.strategy_optimizer import MT5Installation
        return MT5Installation(terminal=terminal,metaeditor=meta,data_dir=data_dir,label="Manual")
    return None


def _strategy_optimizer_request_from_session(cfg: dict) -> dict:
    """Freeze one Strategy Optimizer request from Optimizer-only UI state."""
    install=_strategy_optimizer_install_from_session()
    if install is None:
        raise RuntimeError("MT5 installation is not ready")
    from_value=st.session_state.get("strategy_opt_from") or datetime(2021,1,1).date()
    to_value=st.session_state.get("strategy_opt_to") or datetime(2024,12,31).date()
    tick_label=str(st.session_state.get("strategy_opt_tick_model") or "1 minute OHLC")
    model_map={"Every tick":0,"1 minute OHLC":1,"Open prices only":2,"Every tick based on real ticks":4}
    optimizer_label=str(st.session_state.get("strategy_opt_method") or "Fast genetic")
    return {
        "installation":{"terminal":install.terminal,"metaeditor":install.metaeditor,"data_dir":install.data_dir},
        "symbol":str(st.session_state.get("strategy_opt_symbol") or "XAUUSD").strip(),
        "confirm_symbol":str(st.session_state.get("strategy_opt_confirm_symbol") or "").strip(),
        "period":str(st.session_state.get("strategy_opt_period") or "H1"),
        "from_date":from_value.strftime("%Y.%m.%d"),
        "to_date":to_value.strftime("%Y.%m.%d"),
        "deposit":10000.0,
        "leverage":100,
        "model":model_map.get(tick_label,1),
        "optimization":2 if optimizer_label=="Fast genetic" else 1,
        "max_rounds":int(st.session_state.get("strategy_opt_rounds") or 3),
        "scientist_assist":bool(st.session_state.get("strategy_opt_scientist",bool(((cfg.get("agent") or {}).get("llm") or {}).get("enabled",False)))),
        "scientist_llm":sanitize_scientist_llm_config(((cfg.get("agent") or {}).get("llm") or {})),
        "search_space":DEFAULT_SPACE,
        "optimize_params":list(st.session_state.get("strategy_opt_params") or list(DEFAULT_SPACE)),
        # Freeze the exact live Optimizer form KPI, not a possibly stale cfg snapshot.
        "optimizer_kpi":optimizer_kpi_policy({"strategy_optimizer":{"kpi":{
            "min_profit_factor":float(st.session_state.get("strategy_opt_kpi_pf",((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("min_profit_factor",1.0))),
            "min_recovery_factor":float(st.session_state.get("strategy_opt_kpi_rf",((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("min_recovery_factor",0.0))),
            "min_expectancy_r":float(st.session_state.get("strategy_opt_kpi_exp",((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("min_expectancy_r",0.0))),
            "min_weighted_r":float(st.session_state.get("strategy_opt_kpi_weighted_r",((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("min_weighted_r",0.0))),
            "base_h1_trades_per_month":int(st.session_state.get("strategy_opt_kpi_h1_trades",((cfg.get("strategy_optimizer") or {}).get("kpi") or {}).get("base_h1_trades_per_month",20))),
        }}}),
    }


def _start_global_optimizer_clicked(cfg: dict):
    """One interaction owns start + immediate lifecycle/workspace refresh.

    This callback is deliberately synchronous only through job creation; the heavy
    MT5 optimizer stays in its detached worker.  Rerunning both named fragments in
    the same callback prevents the old two-click/stale-footer race after navigation.
    """
    st.session_state["optimizer_starting"]=True
    try:
        request=_strategy_optimizer_request_from_session(cfg)
        job=start_strategy_optimizer_job(request)
        st.session_state["strategy_optimizer_job_id"]=job.get("job_id")
        st.session_state.pop("strategy_optimizer_lifecycle_error",None)
    except Exception as exc:
        st.session_state["strategy_optimizer_lifecycle_error"]=str(exc)
    finally:
        st.session_state["optimizer_starting"]=False
    # Streamlit 1.63 keyed fragment rerun: refresh both surfaces atomically while
    # leaving Scientist mounted, so one click is sufficient and the draft survives.
    st.rerun(["contextual_lifecycle","workspace"])


_MAX_MATRIX_PARAM_LABELS={
    "InpSL_ATR":"SL ATR","InpTP_ATR":"TP ATR","InpMaxHoldBars":"Max Hold",
    "InpShockHaltATR":"Shock Halt","InpEntryThreshold":"Entry Th","InpExitReverseThreshold":"Exit Reverse",
    "InpMinConsensus":"Min Consensus","InpWeightTrend":"W Trend","InpWeightRange":"W Range",
    "InpWeightBreakout":"W Breakout","InpWeightPullback":"W Pullback","InpWeightSession":"W Session",
    "InpWeightShock":"W Shock","InpWeightRelative":"W Relative","InpRelativeLookback":"Relative LB",
    "InpMinRelativeCorr":"Min Rel Corr",
}


def _optimizer_live_matrix_state(current: dict, *, max_rows: int = 300) -> dict:
    """Read-only live view of completed optimizer R-evidence frames.

    The detached optimizer worker remains the sole writer/authority.  This UI reader
    incrementally consumes only complete newline-terminated rows from Max_MTF_metrics.csv;
    a partially-written tail is left unread until the next fragment refresh.
    """
    jid=str(current.get("job_id") or "").strip()
    if not jid:
        return {"available":False,"reason":"NO_JOB_ID"}
    run_dir=APP_DIR/"runtime"/"strategy_optimizer_runs"/jid
    round_no=max(1,int(current.get("round") or 1))
    state_path=run_dir/f"round_{round_no}_state.json"
    if not state_path.is_file():
        states=sorted(run_dir.glob("round_*_state.json"),key=lambda x:x.stat().st_mtime_ns if x.exists() else 0,reverse=True)
        if not states:
            return {"available":False,"reason":"ROUND_STATE_PENDING"}
        state_path=states[0]
        try: round_no=int(state_path.stem.split("_")[1])
        except Exception: pass
    try:
        round_state=json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {"available":False,"reason":"ROUND_STATE_UNREADABLE"}
    raw_path=str(round_state.get("optimizer_metrics_path") or "").strip()
    if not raw_path:
        return {"available":False,"reason":"METRICS_PATH_PENDING"}
    metrics_path=Path(raw_path)
    if not metrics_path.is_file():
        return {"available":False,"reason":"MAX_METRICS_PENDING","path":str(metrics_path)}
    expected_nonce=int(round_state.get("optimizer_run_nonce") or 0)
    cache_key=f"_max_live_matrix::{jid}::{round_no}::{expected_nonce}"
    cache=st.session_state.get(cache_key)
    try: size=int(metrics_path.stat().st_size)
    except OSError:
        return {"available":False,"reason":"MAX_METRICS_UNREADABLE","path":str(metrics_path)}
    if not isinstance(cache,dict) or str(cache.get("path"))!=str(metrics_path) or size<int(cache.get("offset") or 0):
        cache={"path":str(metrics_path),"offset":0,"header":None,"total":0,"invalid":0,"top":[],"best_mean":None,"best_weighted":None}
    required={"frame_pass_id","frame_inputs","mean_expectancy_r","weighted_r","mt5_trades","r_accounted_trades","sum_net","sum_initial_risk","accounting_errors","run_nonce"}
    try:
        with metrics_path.open("rb") as f:
            f.seek(int(cache.get("offset") or 0))
            while True:
                row_start=f.tell(); raw=f.readline()
                if not raw: break
                # Never consume a row that may still be in the writer's buffer.
                if not (raw.endswith(b"\n") or raw.endswith(b"\r")):
                    f.seek(row_start); break
                try:
                    parsed=next(csv.reader([raw.decode("utf-8-sig",errors="replace")]))
                except Exception:
                    cache["invalid"]=int(cache.get("invalid") or 0)+1; continue
                if cache.get("header") is None:
                    header=[str(x).strip() for x in parsed]
                    if not required.issubset(set(header)):
                        return {"available":False,"reason":"MAX_METRICS_SCHEMA_MISMATCH","path":str(metrics_path)}
                    cache["header"]=header; continue
                header=list(cache.get("header") or [])
                if len(parsed)!=len(header):
                    cache["invalid"]=int(cache.get("invalid") or 0)+1; continue
                rec=dict(zip(header,parsed))
                try:
                    nonce=int(str(rec["run_nonce"]).strip(),10)
                    if expected_nonce and nonce!=expected_nonce: continue
                    frame_id=str(rec["frame_pass_id"]).strip()
                    mean_r=float(rec["mean_expectancy_r"]); weighted_r=float(rec["weighted_r"])
                    trades=int(str(rec["mt5_trades"]).strip(),10); accounted=int(str(rec["r_accounted_trades"]).strip(),10)
                    sum_net=float(rec["sum_net"]); sum_risk=float(rec["sum_initial_risk"])
                    errors=int(str(rec["accounting_errors"]).strip(),10)
                    if errors!=0 or trades!=accounted or sum_risk<=0 or not all(math.isfinite(x) for x in (mean_r,weighted_r,sum_net,sum_risk)):
                        cache["invalid"]=int(cache.get("invalid") or 0)+1; continue
                    params={}
                    for token in str(rec.get("frame_inputs") or "").split("|"):
                        if "=" not in token: continue
                        name,value=token.split("=",1); name=name.strip(); value=value.strip()
                        if name not in _MAX_MATRIX_PARAM_LABELS: continue
                        try:
                            number=float(value)
                            params[_MAX_MATRIX_PARAM_LABELS[name]]=int(round(number)) if name in {"InpMaxHoldBars","InpRelativeLookback"} else number
                        except Exception:
                            params[_MAX_MATRIX_PARAM_LABELS[name]]=value
                    display={
                        "Frame":frame_id,"Mean R":mean_r,"Weighted R":weighted_r,"Trades":trades,
                        "Net":sum_net,"Initial Risk":sum_risk,**params,
                    }
                except Exception:
                    cache["invalid"]=int(cache.get("invalid") or 0)+1; continue
                cache["total"]=int(cache.get("total") or 0)+1
                if cache.get("best_mean") is None or mean_r>float(cache["best_mean"]["Mean R"]): cache["best_mean"]=dict(display)
                if cache.get("best_weighted") is None or weighted_r>float(cache["best_weighted"]["Weighted R"]): cache["best_weighted"]=dict(display)
                top=list(cache.get("top") or []); top.append(display)
                top.sort(key=lambda x:(float(x.get("Mean R",float("-inf"))),float(x.get("Weighted R",float("-inf")))),reverse=True)
                cache["top"]=top[:max_rows]
            cache["offset"]=f.tell()
    except (OSError,PermissionError):
        # MT5 owns the writer handle. A transient Windows sharing/read race is UI-only;
        # retain the last good snapshot instead of disturbing the optimizer.
        pass
    st.session_state[cache_key]=cache
    return {
        "available":bool(cache.get("header")),"reason":"OK" if cache.get("header") else "MAX_METRICS_HEADER_PENDING",
        "round":round_no,"path":str(metrics_path),"total":int(cache.get("total") or 0),"invalid":int(cache.get("invalid") or 0),
        "top":list(cache.get("top") or []),"best_mean":cache.get("best_mean"),"best_weighted":cache.get("best_weighted"),
    }


def _render_optimizer_max_matrix(current: dict):
    live=_optimizer_live_matrix_state(current)
    _subsection_header("MAX Matrix", "Live completed-pass R evidence · read-only")
    if not live.get("available"):
        reason=str(live.get("reason") or "PENDING")
        if reason in {"ROUND_STATE_PENDING","METRICS_PATH_PENDING","MAX_METRICS_PENDING","MAX_METRICS_HEADER_PENDING"}:
            st.caption("MAX Matrix is waiting for the first completed MT5 optimization pass.")
        else:
            st.caption(f"MAX Matrix unavailable: {reason}")
        return
    best_mean=live.get("best_mean") or {}; best_weighted=live.get("best_weighted") or {}
    a,b,c,d=st.columns(4)
    a.metric("Completed evidence",f"{int(live.get('total') or 0):,}")
    b.metric("Best Mean R",f"{float(best_mean.get('Mean R') or 0):+.4f} R")
    c.metric("Its Weighted R",f"{float(best_mean.get('Weighted R') or 0):+.4f} R")
    d.metric("Best Weighted R",f"{float(best_weighted.get('Weighted R') or 0):+.4f} R")
    rows=list(live.get("top") or [])
    if rows:
        df=pd.DataFrame(rows)
        preferred=["Frame","Mean R","Weighted R","Trades","Net","Initial Risk","SL ATR","TP ATR","Max Hold","Entry Th","Exit Reverse","Min Consensus","W Trend","W Range","W Breakout","W Pullback","W Session","W Shock","W Relative","Shock Halt","Relative LB","Min Rel Corr"]
        cols=[x for x in preferred if x in df.columns]+[x for x in df.columns if x not in preferred]
        st.dataframe(df[cols],use_container_width=True,hide_index=True,height=min(520,92+30*min(len(df),14)))
        st.caption(f"Top {len(rows):,} completed frames by Mean R · Round {int(live.get('round') or 0)} · source: Max_MTF_metrics.csv. PF/RF/DD and Champion eligibility are evaluated only after the round XML is complete; this matrix cannot promote a Champion.")
    invalid=int(live.get("invalid") or 0)
    if invalid:
        st.caption(f"Live reader ignored {invalid:,} incomplete/invalid row(s); optimizer evidence was not modified.")



def _strategy_kpi_text(value, suffix=""):
    try:
        if value is None: return "—"
        return f"{float(value):.4f}{suffix}"
    except Exception:
        return "—"


def _render_strategy_champion_summary():
    try:
        reg=ensure_strategy_registry(APP_DIR)
    except Exception as exc:
        st.error(f"Strategy registry unavailable: {exc}")
        return
    current=reg.get("current_champion") if isinstance(reg.get("current_champion"),dict) else None
    _subsection_header("Strategy Champion", "Current promoted strategy authority · Max MTF")
    if not current:
        baseline=reg.get("baseline_strategy") if isinstance(reg.get("baseline_strategy"),dict) else None
        st.info("Strategy Champion: 0 · Baseline Active is not a Champion.")
        if baseline:
            _fact_grid([
                ("Baseline",baseline.get("display_name") or "Max_MTF.mq5"),
                ("Status","BASELINE ACTIVE"),
                ("EA SHA",str(baseline.get("ea_sha256") or "")[:12]),
                ("Champion","0 / null"),
            ])
            with st.expander("Baseline setup",expanded=False):
                params=baseline.get("params") or {}
                setup_rows=[{"Parameter":_MAX_MATRIX_PARAM_LABELS.get(name,name),"Value":params.get(name)} for name in DEFAULT_SPACE if name in params]
                st.dataframe(pd.DataFrame(setup_rows),use_container_width=True,hide_index=True)
        st.caption("Promote an eligible Strategy Challenger to create Strategy Champion #1. The pre-promotion baseline is archived automatically.")
        return
    k=current.get("kpi") or {}
    st.success(f"Current Strategy Champion · Max_MTF.mq5 · {current.get('strategy_id') or 'CURRENT'}")
    c1,c2,c3,c4,c5,c6=st.columns(6)
    c1.metric("PF",_strategy_kpi_text(k.get("profit_factor")))
    c2.metric("RF",_strategy_kpi_text(k.get("recovery_factor")))
    c3.metric("Mean R",_strategy_kpi_text(k.get("mean_r")," R"))
    c4.metric("Weighted R",_strategy_kpi_text(k.get("weighted_r")," R"))
    c5.metric("Profit",_strategy_kpi_text(k.get("profit")))
    try: trades="—" if k.get("trades") is None else str(int(k.get("trades")))
    except Exception: trades="—"
    c6.metric("Trades",trades)
    d1,d2,d3,d4,d5,d6=st.columns(6)
    d1.metric("Equity DD",_strategy_kpi_text(k.get("equity_dd_pct"),"%"))
    d2.metric("Sharpe",_strategy_kpi_text(k.get("sharpe_ratio")))
    d3.metric("Expected Payoff",_strategy_kpi_text(k.get("expected_payoff")))
    try: racc="—" if k.get("r_accounted_trades") is None else str(int(k.get("r_accounted_trades")))
    except Exception: racc="—"
    d4.metric("R-accounted",racc)
    try: aerr="—" if k.get("accounting_errors") is None else str(int(k.get("accounting_errors")))
    except Exception: aerr="—"
    d5.metric("Accounting Errors",aerr)
    d6.metric("Initial Risk Sum",_strategy_kpi_text(k.get("sum_initial_risk")))
    if str(current.get("kpi_status") or "").startswith("UNAVAILABLE"):
        st.caption("Champion KPI evidence unavailable: imported parameter authority has no original optimizer-result evidence; no KPI is fabricated.")
    else:
        ev=current.get("kpi_evidence") or {}
        if ev:
            st.caption(f"Verified optimizer evidence · XML Pass {ev.get('xml_display_pass','—')} · Frame {ev.get('frame_pass_id','—')} · R parity verified · Weighted R arithmetic verified")
    with st.expander("Current Champion setup",expanded=False):
        params=current.get("params") or {}
        setup_rows=[{"Parameter":_MAX_MATRIX_PARAM_LABELS.get(name,name),"Value":params.get(name)} for name in DEFAULT_SPACE if name in params]
        st.dataframe(pd.DataFrame(setup_rows),use_container_width=True,hide_index=True)

def _render_strategy_challenger_registry(cfg: dict):
    """Strategy Challengers only; current Champion is rendered on the Champion page."""
    try:
        reg=ensure_strategy_registry(APP_DIR)
    except Exception as exc:
        st.error(f"Strategy registry unavailable: {exc}")
        return
    _subsection_header("Strategy Challengers", "Optimizer winner → Challenger → explicit Owner promotion")
    entries=[e for e in (reg.get("entries") or []) if str(e.get("status") or "CHALLENGER")=="CHALLENGER"]
    if not entries:
        st.caption("No Strategy Challenger yet. The next eligible Optimizer winner will be saved without replacing the Max MTF baseline EA.")
        return
    rows=[]; raw_entries=[]; by_id={}
    for e in reversed(entries):
        cid=str(e.get("challenger_id") or "?"); by_id[cid]=e; k=e.get("kpi") or {}
        raw_entry=dict(e); raw_entry["run_dir"]=str(run); raw_entries.append(raw_entry)
        rows.append({
            "Challenger":cid,
            "Origin":e.get("role_origin") or "OPTIMIZER",
            "PF":k.get("profit_factor"),"RF":k.get("recovery_factor"),"Mean R":k.get("mean_r"),"Weighted R":k.get("weighted_r"),
            "Profit":k.get("profit"),"Trades":k.get("trades"),
            "EA":Path(str(e.get("ea_file") or "")).name,"Setup":Path(str(e.get("set_file") or "")).name,
        })
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(520,100+33*len(rows)))
    selected=st.selectbox("Selected Strategy Challenger",[r["Challenger"] for r in rows],key="strategy_registry_selected")
    e=by_id[selected]
    with st.expander("Selected Challenger setup & evidence",expanded=True):
        a,b=st.columns(2)
        a.caption(f"EA: `{Path(str(e.get('ea_file') or '')).name}`")
        b.caption(f"Setup: `{Path(str(e.get('set_file') or '')).name}`")
        params=e.get("params") or {}
        setup_rows=[{"Parameter":_MAX_MATRIX_PARAM_LABELS.get(name,name),"Value":params.get(name)} for name in DEFAULT_SPACE if name in params]
        st.dataframe(pd.DataFrame(setup_rows),use_container_width=True,hide_index=True)
        gates=e.get("hard_gates") or {}
        if gates: st.caption("Frozen optimizer hard gates · "+" · ".join(f"{k}={v}" for k,v in gates.items()))

    install=_strategy_optimizer_install_from_session()
    promote_ok=install is not None
    pc,dc=st.columns(2)
    with pc:
        confirm=st.checkbox("Confirm Strategy promotion",value=False,key=f"strategy_promote_confirm_{selected}")
        if st.button("PROMOTE TO STRATEGY CHAMPION",type="primary",disabled=(not confirm or not promote_ok),use_container_width=True,key=f"strategy_promote_{selected}"):
            try:
                inst={"terminal":install.terminal,"metaeditor":install.metaeditor,"data_dir":install.data_dir}
                res=promote_strategy_challenger(APP_DIR,selected,installation=inst)
                dem=(res.get("demoted_champion") or {}).get("challenger_id")
                st.success(f"Promoted {selected} → Max MTF Strategy Champion. Previous Champion/archive reference: {dem}.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))
        if not promote_ok: st.caption("Configure MT5 installation above before promotion; compile/deploy + Max_MTF.set parity are mandatory.")
    with dc:
        delete_confirm=st.checkbox("Confirm delete Challenger",value=False,key=f"strategy_delete_confirm_{selected}")
        if st.button("DELETE CHALLENGER",disabled=not delete_confirm,use_container_width=True,key=f"strategy_delete_{selected}"):
            try:
                delete_strategy_challenger(APP_DIR,selected)
                st.success(f"Deleted active Challenger {selected}. Audit tombstone retained.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

def render_strategy_optimizer_page(cfg: dict):
    _page_header("Strategy Optimizer", "Pre-model MT5 parameter search", "EA v2.00 · MT5 native · separate lifecycle")
    st.caption("Optimizer runs before ModelLab Research. Source authority is the Max MTF v2.0 baseline EA. START deploys only a byte-identical copy into MT5 for Strategy Tester use; no EA is generated or rewritten.")

    installs=discover_mt5_installations()
    install=None
    if installs:
        labels=[x.label for x in installs]
        saved_install=str(st.session_state.get("strategy_opt_mt5_installation") or "")
        install_index=labels.index(saved_install) if saved_install in labels else 0
        chosen=st.selectbox("MT5 installation",labels,index=install_index,key="strategy_opt_mt5_installation")
        install=next(x for x in installs if x.label==chosen)
    else:
        st.warning("MT5 installation was not auto-detected. Set these paths once for Strategy Optimizer.")
        a,b=st.columns(2)
        terminal=a.text_input("terminal64.exe",value=str(st.session_state.get("strategy_opt_terminal") or ""),key="strategy_opt_terminal")
        meta=b.text_input("metaeditor64.exe",value=str(st.session_state.get("strategy_opt_metaeditor") or ""),key="strategy_opt_metaeditor")
        data_dir=st.text_input("MT5 data directory · contains MQL5",value=str(st.session_state.get("strategy_opt_data_dir") or ""),key="strategy_opt_data_dir")
        if terminal and meta and data_dir:
            from strategy.strategy_optimizer import MT5Installation
            install=MT5Installation(terminal=terminal,metaeditor=meta,data_dir=data_dir,label="Manual")

    _subsection_header("EA & market", "Max MTF v2.0 baseline · zero-Champion bootstrap · optimizer winners become Challengers", first=True)
    try:
        ea_identity=canonical_ea_identity()
        _fact_grid([
            ("EA source",str(ea_identity.get("package_relative_path") or "EA_v2_00/baseline/Max_MTF.mq5")),
            ("Source SHA",str(ea_identity.get("sha256") or "")[:12]),
            ("Deployment","Byte-identical copy → MT5/Experts/MaxMTF"),
        ])
        st.caption("Max never synthesizes an unrelated EA. Strategy logic stays fixed; an eligible Optimizer winner is saved as a Strategy Challenger while the current Max MTF baseline/promoted strategy remains unchanged. Only explicit PROMOTE TO STRATEGY CHAMPION synchronizes canonical Max MTF baseline EA + Tester preset + compiled deployment for your manual MT5 backtest before START Research.")
    except Exception as exc:
        st.error(f"Canonical Max MTF v2.0 baseline EA is not ready: {exc}")

    c1,c2,c3=st.columns(3)
    c1.text_input("Main Symbol",value=str(st.session_state.get("strategy_opt_symbol") or "XAUUSD"),key="strategy_opt_symbol")
    c2.text_input("Relative reference symbol",value=str(st.session_state.get("strategy_opt_confirm_symbol") or ""),placeholder="e.g. XAGUSD.m",key="strategy_opt_confirm_symbol",help="Required by Strategy 7 Relative Value; it is not an entry-confirmation switch.")
    periods=["M1","M2","M3","M4","M5","M6","M10","M12","M15","M20","M30","H1","H2","H3","H4","H6","H8","H12","D1","W1","MN1"]
    current_period=str(st.session_state.get("strategy_opt_period") or "H1")
    c3.selectbox("Timeframe",periods,index=periods.index(current_period) if current_period in periods else 11,key="strategy_opt_period")

    d1,d2,d3=st.columns(3)
    from_date=d1.date_input("Optimization from",value=st.session_state.get("strategy_opt_from") or datetime(2021,1,1).date(),key="strategy_opt_from")
    to_date=d2.date_input("Optimization to",value=st.session_state.get("strategy_opt_to") or datetime(2024,12,31).date(),key="strategy_opt_to")
    tick_models=["Every tick","1 minute OHLC","Open prices only","Every tick based on real ticks"]
    saved_tick=str(st.session_state.get("strategy_opt_tick_model") or "1 minute OHLC")
    d3.selectbox("MT5 tick model",tick_models,index=tick_models.index(saved_tick) if saved_tick in tick_models else 1,key="strategy_opt_tick_model")

    _subsection_header("Optimizer KPI", "Independent from Model Research KPI · frozen when START is clicked")
    kpi=cfg.setdefault("strategy_optimizer",{}).setdefault("kpi",{})
    kc=st.columns(5,gap="medium")
    kpi["min_profit_factor"]=float(kc[0].number_input("Min PF",0.0,20.0,float(kpi.get("min_profit_factor",1.0)),0.05,key="strategy_opt_kpi_pf"))
    kpi["min_recovery_factor"]=float(kc[1].number_input("Min RF",-20.0,50.0,float(kpi.get("min_recovery_factor",0.0)),0.1,key="strategy_opt_kpi_rf"))
    kpi["min_expectancy_r"]=float(kc[2].number_input("Min Mean R",-5.0,5.0,float(kpi.get("min_expectancy_r",0.0)),0.01,key="strategy_opt_kpi_exp",help="Arithmetic mean realized R/trade. Signal/policy edge normalized by each trade's own initial risk."))
    kpi["min_weighted_r"]=float(kc[3].number_input("Min Weighted R",-5.0,5.0,float(kpi.get("min_weighted_r",0.0)),0.01,key="strategy_opt_kpi_weighted_r",help="sum(net P/L) / sum(initial risk). System/capital edge under adaptive sizing."))
    kpi["base_h1_trades_per_month"]=int(kc[4].number_input("H1 min trades / month",1,1000,int(kpi.get("base_h1_trades_per_month",20)),1,key="strategy_opt_kpi_h1_trades"))
    kpi["schema"]="MAX_STRATEGY_OPTIMIZER_KPI_V2"; kpi.setdefault("timeframe_scaling","SQRT"); kpi.setdefault("min_timeframe_factor",0.20); kpi.setdefault("max_timeframe_factor",4.00); kpi["rounding"]="CEIL_MONTHLY_RATE_AND_FINAL_REQUIREMENT"
    try:
        live_kpi=optimizer_kpi_policy(cfg)
        sample=optimizer_trade_sample(str(st.session_state.get("strategy_opt_period") or "H1"),from_date.strftime("%Y.%m.%d"),to_date.strftime("%Y.%m.%d"),kpi_profile=live_kpi)
        _fact_grid([
            ("Current TF",str(st.session_state.get("strategy_opt_period") or "H1")),
            ("Min / month",int(sample["scaled_trades_per_month"])),
            ("Exact range",f"{float(sample['effective_months']):.1f} months"),
            ("Required trades",int(sample["minimum_trades"])),
        ])
        st.caption("AUTO timeframe scaling from H1 · monthly rate ROUND UP · exact-range minimum ROUND UP once at final requirement.")
    except Exception as exc:
        st.warning(f"Optimizer sample gate unresolved: {exc}")

    _subsection_header("Adaptive search", "Round 1 deterministic broad range · later rounds may use bounded Scientist advice")
    selected_params=st.multiselect("Parameters to optimize",options=list(DEFAULT_SPACE),default=list(st.session_state.get("strategy_opt_params") or list(DEFAULT_SPACE)),key="strategy_opt_params",help="Only selected parameters receive MT5 optimization flag Y. Unselected parameters are frozen at the current EA default and Scientist cannot activate them.")
    if not selected_params:
        st.warning("Select at least one parameter to optimize.")
    x1,x2,x3=st.columns(3)
    llm_enabled=bool(((cfg.get("agent") or {}).get("llm") or {}).get("enabled",False))
    x1.toggle("Scientist proposes next ranges",value=bool(st.session_state.get("strategy_opt_scientist",llm_enabled)),key="strategy_opt_scientist",help="Advisory only. Scientist cannot change KPI, EA, date range, strategy count or parameter universe.")
    x2.number_input("Maximum MT5 rounds",1,5,int(st.session_state.get("strategy_opt_rounds") or 3),1,key="strategy_opt_rounds")
    optimizer_modes=["Fast genetic","Slow complete"]
    saved_method=str(st.session_state.get("strategy_opt_method") or "Fast genetic")
    x3.selectbox("Native optimizer",optimizer_modes,index=optimizer_modes.index(saved_method) if saved_method in optimizer_modes else 0,key="strategy_opt_method")
    st.caption("MT5 fitness = Custom max (Mean R) · Result column = Mean R. Weighted R is captured per pass through MT5 optimization-frame evidence. PF, RF, Mean R, Weighted R and minimum trades are independent hard gates.")
    try:
        card=search_space_cardinality(DEFAULT_SPACE,selected_params or list(DEFAULT_SPACE))
        raw=int(card.get("raw_complete_grid_combinations") or 0)
        method=str(st.session_state.get("strategy_opt_method") or "Fast genetic")
        if method=="Fast genetic":
            st.caption(f"Round 1 · {int(card.get('optimized_inputs') or 0)} optimized inputs · raw full grid {raw:,} combinations. MT5 owns genetic population/job scheduling; Tasks/Passed in the MT5 Agents tab are native passes inside this one Max round, not extra Max rounds.")
        else:
            st.warning(f"Slow complete requests the raw Cartesian grid ({raw:,} combinations). For this space it is not a practical search mode; use Fast genetic unless you intentionally narrow the ranges first.")
    except Exception:
        pass

    _subsection_header("Scientist Optimizer Report", "Read-only explanation of the latest range proposal")
    @st.fragment(run_every=2.0)
    def _strategy_optimizer_scientist_report():
        current=latest_strategy_optimizer_job()
        frozen_request=(current or {}).get("request") if isinstance((current or {}).get("request"),dict) else {}
        assist=bool(frozen_request.get("scientist_assist", st.session_state.get("strategy_opt_scientist",False)))
        report_mode="DETERMINISTIC_ONLY" if not assist else "SCIENTIST ON · NOT CALLED"
        report_reason=(
            "Scientist is OFF in the frozen Optimizer request. After any no-winner round, deterministic bounded refinement runs automatically for the next round while budget remains."
            if not assist else
            "Scientist is ON in the frozen Optimizer request and is called automatically only after a completed no-winner round, before the next round. It is never called after a Champion exists."
        )
        report_model="—"
        if current:
            rounds=list(current.get("rounds") or [])
            latest_prop=next((r.get("next_space_proposal") for r in reversed(rounds) if isinstance(r,dict) and r.get("next_space_proposal")),None)
            if isinstance(latest_prop,dict):
                report_mode=str(latest_prop.get("mode") or "UNKNOWN")
                meta=latest_prop.get("meta") if isinstance(latest_prop.get("meta"),dict) else {}
                report_reason=str(
                    meta.get("reason")
                    or latest_prop.get("reason")
                    or latest_prop.get("scientist_error")
                    or ("Scientist OFF: deterministic bounded refinement." if not assist else "Scientist path completed without an explicit provider narrative; see proposal evidence.")
                )
                prov=(latest_prop.get("llm_provenance") if isinstance(latest_prop.get("llm_provenance"),dict) else {}) or (meta.get("llm_provenance") if isinstance(meta.get("llm_provenance"),dict) else {})
                report_model=str(prov.get("selected_model") or prov.get("model") or "—")
        _fact_grid([("Scientist",report_mode),("Model",report_model),("KPI authority","Optimizer-only · frozen request")])
        st.caption(report_reason)
    _strategy_optimizer_scientist_report()

    @st.fragment(run_every=2.0)
    def _strategy_optimizer_status():
        current=latest_strategy_optimizer_job()
        if not current:
            st.caption("No optimizer run yet."); return
        status=str(current.get("status") or "UNKNOWN")
        terminal_statuses={"STRATEGY_CHALLENGER_FOUND","CHAMPION_FOUND","NO_CHAMPION_MAX_ROUNDS","FAILED","STOPPED"}
        terminal_key=f"_optimizer_terminal_lifecycle_seen_{current.get('job_id')}"
        if status in terminal_statuses and str(st.session_state.get(terminal_key) or "")!=status:
            st.session_state[terminal_key]=status
            # Wake the fixed sidebar lifecycle immediately on terminal transition;
            # its normal 2s heartbeat remains the fallback if this fragment is not mounted.
            st.rerun(["contextual_lifecycle"])
        st.markdown(f"**{html.escape(status)}** · {html.escape(str(current.get('message') or ''))}")
        if current.get("round"):
            st.progress(min(1.0,float(current.get("round") or 0)/max(1,float((current.get("request") or {}).get("max_rounds") or 1))),text=f"MT5 round {current.get('round')} / {(current.get('request') or {}).get('max_rounds')}")
        rounds=list(current.get("rounds") or [])
        last_round=next((r for r in reversed(rounds) if isinstance(r,dict) and r.get("report")),None)
        if isinstance(last_round,dict):
            audit=last_round.get("eligibility_audit") if isinstance(last_round.get("eligibility_audit"),dict) else {}
            _fact_grid([
                ("Evidence report",Path(str(last_round.get("report") or "—")).name),
                ("Parsed passes",int(audit.get("parsed_passes") or last_round.get("passes") or 0)),
                ("Eligible",int(audit.get("eligible_passes") or last_round.get("pass_count") or 0)),
                ("Report SHA",str(last_round.get("report_sha256") or "—")[:12]),
                ("R evidence SHA",str(last_round.get("optimizer_metrics_sha256") or "—")[:12]),
            ])
            mode=str(last_round.get("report_selection_mode") or "").strip()
            if mode: st.caption(f"Report provenance: {mode}")
        _render_optimizer_max_matrix(current)
        if status=="STRATEGY_CHALLENGER_FOUND":
            ch=current.get("strategy_challenger") or {}; entry=current.get("strategy_challenger_entry") or {}; m1,m2,m3,m4=st.columns(4)
            m1.metric("Profit Factor",f"{float(ch.get('profit_factor') or 0):.3f}")
            m2.metric("Recovery Factor",f"{float(ch.get('recovery_factor') or 0):.3f}")
            m3.metric("Mean R",f"{float(ch.get('expectancy_r') or 0):.3f} R")
            m4.metric("Weighted R",f"{float(ch.get('weighted_r') or 0):.3f} R")
            st.success(f"Strategy Challenger saved: {entry.get('challenger_id') or '—'}. Current Max MTF baseline/promoted strategy is unchanged. Review the registry below and promote explicitly if desired.")
        elif status=="CHAMPION_FOUND":
            st.warning("Legacy optimizer run status: CHAMPION_FOUND. v0.11.0 no longer auto-promotes optimizer winners; new runs create Strategy Challengers instead.")
        elif status=="ROUND_COMPLETE_NO_CHAMPION":
            st.info("This round has no eligible winner. Optimizer is automatically refining the bounded search range and continuing to the next MT5 round.")
        elif status=="NO_CHAMPION_MAX_ROUNDS":
            st.warning("No eligible Champion was found before the frozen maximum-round budget was exhausted. Optimizer stopped.")
        elif status=="WAITING_FOR_REPORT":
            st.warning("MT5 round is checkpointed and waiting for a compatible XML report. Use RESUME AUTO OPTIMIZER; Resume never reruns the checkpointed round, and if that evidence has no Champion the remaining rounds continue automatically.")
        elif status=="FAILED":
            st.error(str(current.get("message") or "Optimizer failed"))
            evidence=Path(str(current.get("evidence_dir") or (Path(__file__).resolve().parent.parent/"owner_acceptance"/"evidence"/"strategy_optimizer"/str(current.get("job_id")))))
            diag_path=evidence/"diagnostic.json"
            if diag_path.exists():
                try:
                    diag=json.loads(diag_path.read_text(encoding="utf-8")); excerpt=diag.get("compile_error_excerpt") or []
                    st.markdown("**Automatic diagnostic**")
                    st.code("\n".join(excerpt) if excerpt else f"{diag.get('error_type','Error')}: {diag.get('error','Unknown error')}",language="text")
                except Exception:
                    pass
            st.caption(f"Evidence: `{evidence}`")
            bundle=Path(str(current.get("diagnostic_bundle") or "")) if current.get("diagnostic_bundle") else None
            copen,cdownload=st.columns(2)
            if os.name=="nt" and copen.button("OPEN EVIDENCE FOLDER",use_container_width=True,key=f"strategy_opt_open_evidence_{current.get('job_id')}"):
                try: os.startfile(str(evidence))
                except Exception as exc: st.error(f"Could not open evidence folder: {exc}")
            if bundle is not None and bundle.exists():
                cdownload.download_button("DOWNLOAD DIAGNOSTIC ZIP",data=bundle.read_bytes(),file_name=bundle.name,mime="application/zip",use_container_width=True,key=f"strategy_opt_download_diag_{current.get('job_id')}")
    _strategy_optimizer_status()
    _render_strategy_challenger_registry(cfg)


def render_guided_page(cfg: dict):
    _page_header("Guided Research", "Research stage")
    candidates=[]
    for p in list_runs(RUNS_DIR):
        mp=p/"model_manifest.json"
        if not mp.exists():
            continue
        try:
            status=str(load_manifest(p).get("status"))
        except Exception:
            continue
        if status in {"FEATURE_LABEL_AUDIT_READY","GUIDED_RESEARCH_READY","GUIDED_RESEARCH_REJECTED"}:
            candidates.append(p)
    if not candidates:
        st.info("Belum ada audit/guided run. Kembali ke Pipeline dan jalankan FEATURE + LABEL AUDIT pada lineage yang memang membutuhkan audit.")
        return
    names=[p.name for p in candidates]
    pending=st.session_state.pop("pending_guided_run",None)
    if pending in names:
        st.session_state["guided_run_select"]=pending
    default=st.session_state.get("guided_run_select") or names[0]
    if default not in names:
        default=names[0]
    name=st.selectbox("Audit / Guided lineage",names,index=names.index(default),key="guided_run_select",format_func=lambda x:_run_label(next(p for p in candidates if p.name==x)))
    run_dir=next(p for p in candidates if p.name==name)
    m=load_manifest(run_dir)
    status=str(m.get("status"))
    ident=_run_identity(run_dir,m)
    panel=("<div class='cp-panel'><div class='cp-panel-title'>Guided lineage</div>"
           "<div style='display:flex;gap:1.3rem;flex-wrap:wrap'>"
           f"<strong>{ident['symbol']} · {ident['timeframe']}</strong><span>{status}</span>"
           f"<span>{html.escape(_family_display_name(m.get('model_family','?')))} · {html.escape(str(m.get('model_name','?')))}</span>"
           f"<span style='opacity:.62'>{run_dir.name}</span></div></div>")
    st.markdown(panel,unsafe_allow_html=True)
    _render_route(m)

    if status=="FEATURE_LABEL_AUDIT_READY":
        rp=run_dir/"feature_label_audit.json"
        audit=json.loads(rp.read_text(encoding="utf-8")) if rp.exists() else {}
        ov=audit.get("policy_overselection") or {}
        with st.container(border=True,key="guided_audit_summary"):
            st.markdown("#### 1 · Audit conclusion")
            a,b,c,d=st.columns(4)
            a.metric("Policy OOF trades",int(ov.get("policy_total_validation_trades",0)))
            b.metric("Regime concentration",_fmt(ov.get("policy_regime_concentration"),"pct"))
            c.metric("Hypotheses",len(audit.get("guided_hypotheses") or []))
            d.metric("Locked reopened","NO")
            st.caption("Hypotheses berasal dari bounded label sensitivity + feature ablation. Composite Score tidak dapat meloloskan hypothesis yang gagal mandatory gates.")
        with st.container(border=True,key="guided_dataset"):
            st.markdown("#### 2 · Source dataset")
            src=authority_source_csv(run_dir)
            if src: st.caption(f"Immutable research source: `{src}`")
            ok=dataset_card(src)
        with st.container(border=True,key="guided_runbox"):
            st.markdown("#### 3 · Run bounded Guided Research")
            st.caption("Frozen source model diuji ulang hanya pada upstream OOF untuk setiap hypothesis. Historical locked test tidak dihitung atau dibaca.")
            if st.button("RUN BOUNDED GUIDED RESEARCH",type="primary",disabled=(src is None or not ok),use_container_width=True,key=f"guided_btn_{run_dir.name}"):
                bar,slot,cb=_action_progress()
                try:
                    runtime=write_runtime_cfg(cfg,f"guided_authority_{run_dir.name}.json"); res=run_guided_research(run_dir,src,runtime,RUNS_DIR,progress=cb)
                    st.session_state.last_run=res["run"]
                    st.session_state.pending_guided_run=Path(res["run"]).name
                    st.session_state.pending_run_select=Path(res["run"]).name
                    st.session_state.pending_nav="Guided Research"
                    bar.progress(100)
                    slot.success(res["status"])
                    st.rerun()
                except Exception as e:
                    slot.error(str(e))
                    with st.expander("Technical traceback"):
                        st.code(traceback.format_exc())
        return

    if status=="GUIDED_RESEARCH_READY":
        cv=m.get("cv_selection") or {}
        with st.container(border=True,key="guided_winner"):
            st.markdown("#### 1 · Guided hypothesis PASS")
            a,b,c,d=st.columns(4)
            a.metric("Max DD",_fmt(cv.get("median_max_drawdown_r"),"r2"))
            b.metric("Recovery",_fmt(cv.get("median_recovery_factor")))
            c.metric("PF",_fmt(cv.get("median_profit_factor")))
            d.metric("Trades",_fmt(cv.get("total_validation_trades"),"int"))
            mask=", ".join(m.get("feature_research",{}).get("zero_features") or []) or "NONE"
            st.caption(f"Hypothesis: {cv.get('name','?')} · feature mask: {mask}")
        with st.container(border=True,key="guided_newgen_data"):
            st.markdown("#### 2 · Source dataset")
            src=authority_source_csv(run_dir)
            if src: st.caption(f"Immutable research source: `{src}`")
            ok=dataset_card(src)
        with st.container(border=True,key="guided_newgen_run"):
            st.markdown("#### 3 · Start new generation")
            st.caption("Learning generation: re-check elite lineage + failure-targeted refinement + exploration reserve. Historical locked test tetap sealed; generasi baru belajar dari OOF evidence sebelumnya, bukan reset board secara buta.")
            rec=run_dir/"recommended_config.json"
            if not rec.exists():
                st.error("recommended_config.json tidak ada. New generation fail-closed.")
            elif st.button("START NEW GENERATION RESEARCH",type="primary",disabled=(src is None or not ok),use_container_width=True,key=f"guided_newgen_btn_{run_dir.name}"):
                try:
                    guided_cfg=json.loads(rec.read_text(encoding="utf-8"))
                    memory=build_research_memory(run_dir,RUNS_DIR,guided_cfg)
                    guided_cfg.setdefault("agent",{})["generation_memory"]=memory
                    guided_cfg["agent"]["generation_parent_run_id"]=run_dir.name
                    runtime=write_runtime_cfg(guided_cfg,f"guided_newgen_{run_dir.name}.json")
                    bar,status_slot,table_slot,cb=progress_ui()
                    result=run_supervisor_agent(src,runtime,RUNS_DIR,progress=cb,llm_api_key=st.session_state.llm_api_key)
                    st.session_state.last_run=result["run"]
                    st.session_state.pending_run_select=Path(result["run"]).name
                    st.session_state.pending_nav="Pipeline"
                    bar.progress(100)
                    status_slot.success(result["status"])
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
                    with st.expander("Technical traceback"):
                        st.code(traceback.format_exc())
        with st.expander("Guided leaderboard",expanded=False):
            lb=run_dir/"guided_leaderboard.json"
            if lb.exists():
                rows=json.loads(lb.read_text(encoding="utf-8"))
                cols=["name","cv_gate_pass","cv_first_failed_gate","median_max_drawdown_r","worst_fold_max_drawdown_r","median_recovery_factor","worst_fold_recovery_factor","median_profit_factor","overall_expectancy_r","median_expectancy_r","worst_expectancy_r","total_validation_trades","selection_score","zero_features"]
                df=pd.DataFrame(rows)
                st.dataframe(df[[c for c in cols if c in df.columns]],use_container_width=True,hide_index=True,height=min(520,90+32*len(df)))
        return

    if status=="GUIDED_RESEARCH_REJECTED":
        st.error("Guided Research juga gagal mandatory OOF gates. Jangan buka holdout lama, jangan tambah budget membabi buta.")
        cv=m.get("cv_selection") or {}
        a,b,c,d=st.columns(4)
        a.metric("First fail",str((m.get("cv_acceptance") or {}).get("first_failed_gate") or "?"))
        b.metric("DD",_fmt(cv.get("median_max_drawdown_r"),"r2"))
        c.metric("RF",_fmt(cv.get("median_recovery_factor")))
        d.metric("Trades",_fmt(cv.get("total_validation_trades"),"int"))
        with st.expander("Guided leaderboard",expanded=True):
            lb=run_dir/"guided_leaderboard.json"
            if lb.exists():
                rows=json.loads(lb.read_text(encoding="utf-8"))
                st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(600,90+32*len(rows)))
        st.caption("Route berhenti di sini sampai ada hypothesis baru yang benar-benar berbeda. Tidak ada fallback tersembunyi ke Label page.")



def _factory_progress_ui():
    bar=st.progress(0); slot=st.empty(); details=st.empty(); events=[]
    def cb(p):
        stage=str(p.get("stage", "")); msg=str(p.get("message", "") or "Working…")
        cur=float(p.get("current",0) or 0); total=max(1.0,float(p.get("total",1) or 1))
        if stage=="factory_discovery": frac=.03+.08*min(1,cur/total)
        elif stage=="onnx_preflight": frac=.03+.07*min(1,cur/total)
        elif stage=="onnx_preflight_reuse": frac=.11
        elif stage in {"load","label"}: frac=.12
        elif stage in {"agent_round","cv"}:
            c=float(p.get("candidate_index",p.get("current",0)) or 0); t=max(1.0,float(p.get("candidate_total",p.get("total",1)) or 1)); frac=.15+.55*min(1,c/t)
        elif stage=="factory_tournament": frac=.10+.80*min(1,cur/total)
        elif stage in {"winner","onnx"}: frac=.90
        elif stage in {"factory_done","done"}: frac=1.0
        else: frac=.05
        bar.progress(min(100,int(frac*100))); slot.markdown(f"**{msg}**")
        if stage in {"onnx_preflight","factory_discovery","factory_tournament","factory_done"}:
            events.append({"Stage":stage,"Progress":f"{int(cur)}/{int(total)}","Message":msg})
            details.dataframe(pd.DataFrame(events[-12:]),use_container_width=True,hide_index=True,height=min(430,90+32*len(events[-12:])))
    return bar,slot,cb


def _factory_runs():
    if not FACTORY_DIR.exists(): return []
    return sorted([p for p in FACTORY_DIR.iterdir() if p.is_dir() and (p/"factory_manifest.json").exists()],key=lambda p:p.name,reverse=True)


def render_champion_factory_page(cfg: dict):
    _page_header("Legacy Champion Factory", "Diagnostic", "v0.7.0")
    with st.container(border=True,key="factory_dataset"):
        st.markdown("#### 1 · Master dataset + chronological contract")
        dataset=resolve_dataset("factory"); ok=dataset_card(dataset)
        if not ok or dataset is None: return
        info=available_date_range(dataset); dates=info["available_dates"]; lo=dates[0]; hi=dates[-1]
        fc=cfg.setdefault("champion_factory",{})
        def _clamp(raw, fallback):
            try: d=pd.Timestamp(raw).date()
            except Exception: d=fallback
            return min(max(d,lo),hi)
        d1=_clamp(fc.get("discovery_from"),lo); d2=_clamp(fc.get("discovery_to"),min(hi,pd.Timestamp("2022-12-31").date()))
        t1=_clamp(fc.get("tournament_from"),max(lo,pd.Timestamp("2023-01-01").date())); t2=_clamp(fc.get("tournament_to"),min(hi,pd.Timestamp("2025-12-31").date()))
        f1=_clamp(fc.get("fresh_from"),max(lo,pd.Timestamp("2026-01-01").date())); f2=hi
        a,b=st.columns(2); discovery_from=a.date_input("Discovery From",value=d1,min_value=lo,max_value=hi,key="factory_discovery_from"); discovery_to=b.date_input("Discovery To",value=d2,min_value=lo,max_value=hi,key="factory_discovery_to")
        a,b=st.columns(2); tournament_from=a.date_input("Tournament From",value=t1,min_value=lo,max_value=hi,key="factory_tournament_from"); tournament_to=b.date_input("Tournament To",value=t2,min_value=lo,max_value=hi,key="factory_tournament_to")
        a,b=st.columns(2); fresh_from=a.date_input("Fresh From",value=f1,min_value=lo,max_value=hi,key="factory_fresh_from"); fresh_to=b.date_input("Fresh To",value=f2,min_value=lo,max_value=hi,key="factory_fresh_to")
        valid=discovery_from<=discovery_to<tournament_from<=tournament_to<fresh_from<=fresh_to
        if not valid: st.error("Split overlap / tidak chronological. Wajib Discovery < Tournament < Fresh.")
        fc.update({"discovery_from":str(discovery_from),"discovery_to":str(discovery_to),"tournament_from":str(tournament_from),"tournament_to":str(tournament_to),"fresh_from":str(fresh_from),"fresh_to":str(fresh_to)})
        ident=quick_summary(dataset); tsp=cfg.get("trade_sample_policy",{})
        try:
            ds=auto_trade_sample(ident["period"],discovery_from,discovery_to,cfg,"DISCOVERY",observed_fraction=.50)
            ts=auto_trade_sample(ident["period"],tournament_from,tournament_to,cfg,"TOURNAMENT")
            fs=auto_trade_sample(ident["period"],fresh_from,fresh_to,cfg,"FRESH")
            x,y,z=st.columns(3)
            x.metric("Discovery OOF min",int(ds["minimum_trades"])); y.metric("Tournament min",int(ts["minimum_trades"])); z.metric("Fresh min",int(fs["minimum_trades"]))
            st.caption(f"Trade Sample {tsp.get('mode','AUTO')} · H1 baseline {int(tsp.get('base_h1_trades_per_month',8))}/bulan · exact Discovery OOF gate dihitung ulang dari actual fold exposure saat run.")
        except Exception as e: st.warning(f"AUTO trade preview tidak tersedia: {e}")

    with st.container(border=True,key="factory_policy"):
        st.markdown("#### 2 · Pool policy")
        a,b,c=st.columns(3)
        fc["target_pool"]=int(a.number_input("Qualified candidates required",12,12,int(fc.get("target_pool",12)),1,disabled=True))
        fc["max_total_experiments"]=int(b.number_input("Max total Discovery experiments",36,600,int(fc.get("max_total_experiments",216)),12,key="factory_max_total"))
        fc["max_generations"]=int(c.number_input("Max learning generations",1,20,int(fc.get("max_generations",8)),1,key="factory_max_gen"))
        st.caption("Target 12 adalah hard requirement. Budget habis sebelum 12 → INSUFFICIENT_QUALIFIED_POOL. Gate tidak dilonggarkan.")

    with st.container(border=True,key="factory_start"):
        st.markdown("#### 3 · Discovery / Screening")
        if st.button("START CHAMPION FACTORY · DISCOVERY UNTIL 12",type="primary",disabled=not valid,use_container_width=True,key="factory_start_btn"):
            persist_user_settings(); runtime=write_runtime_cfg(cfg,"champion_factory_runtime.json"); bar,slot,cb=_factory_progress_ui()
            try:
                res=run_discovery_pool(dataset,runtime,FACTORY_DIR,discovery_from,discovery_to,tournament_from,tournament_to,fresh_from,fresh_to,progress=cb,llm_api_key=st.session_state.llm_api_key)
                st.session_state["factory_selected"]=Path(res["factory"]).name; bar.progress(100); slot.success(f"{res['status']} · {res['qualified']}/{res['target']}"); st.rerun()
            except Exception as e:
                slot.error(str(e));
                with st.expander("Technical traceback"): st.code(traceback.format_exc())

    runs=_factory_runs()
    if not runs:
        st.info("Belum ada Champion Factory run."); return
    names=[p.name for p in runs]; default=st.session_state.get("factory_selected") or names[0]
    if default not in names: default=names[0]
    selected=st.selectbox("Factory lineage",names,index=names.index(default),key="factory_selected")
    fd=FACTORY_DIR/selected; fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8")); status=str(fm.get("status"))
    st.markdown(f"**Status:** `{status}` · Qualified `{fm.get('qualified_candidates',0)}/{fm.get('target_candidates',12)}` · Experiments `{fm.get('total_experiments',0)}/{fm.get('max_total_experiments',0)}`")
    pool_path=fd/"candidate_pool.json"
    if pool_path.exists():
        pool=json.loads(pool_path.read_text(encoding="utf-8")); rows=[]
        for c in pool:
            m=c.get("discovery_metrics") or {}; rows.append({"ID":c.get("pool_id"),"Family":_family_display_name(c.get("family")),"Model":c.get("name"),"Trades":m.get("total_validation_trades"),"Min":m.get("auto_min_validation_trades"),"PF":m.get("median_profit_factor"),"Overall R":m.get("overall_expectancy_r"),"Median R":m.get("median_expectancy_r"),"Worst R":m.get("worst_expectancy_r"),"DD R":m.get("median_max_drawdown_r"),"Ranking Score":m.get("selection_score")})
        if rows: st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True,height=min(500,90+32*len(rows)))

    if status=="DISCOVERY_POOL_READY":
        st.success("12 candidates frozen. Tournament contract sekarang boleh dibuka tepat sekali.")
        if st.button("RUN TOURNAMENT · 12 → 1 WINNER",type="primary",use_container_width=True,key=f"factory_tourney_{selected}"):
            persist_user_settings(); runtime=write_runtime_cfg(cfg,f"factory_tournament_{selected}.json"); bar,slot,cb=_factory_progress_ui()
            try:
                res=run_tournament(fd,dataset,runtime,progress=cb); bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e:
                slot.error(str(e));
                with st.expander("Technical traceback"): st.code(traceback.format_exc())

    tl=fd/"tournament_leaderboard.json"
    if tl.exists():
        rows=json.loads(tl.read_text(encoding="utf-8")); view=[]
        for r in rows:
            m=r.get("metrics") or {}; a=r.get("acceptance") or {}; view.append({"ID":r.get("pool_id"),"Family":_family_display_name(r.get("family")),"PASS":"YES" if a.get("passed") else "NO","First fail":a.get("first_failed_gate"),"Trades":m.get("trades"),"Min":m.get("auto_min_trades"),"PF":m.get("profit_factor"),"Exp R":m.get("expectancy_r"),"DD R":m.get("max_drawdown_r"),"Recovery":m.get("recovery_factor")})
        st.markdown("#### Tournament leaderboard"); st.dataframe(pd.DataFrame(view),use_container_width=True,hide_index=True,height=min(500,90+32*len(view)))

    if status=="TOURNAMENT_WINNER_READY":
        w=json.loads((fd/"tournament_winner.json").read_text(encoding="utf-8")); st.success(f"Tournament winner frozen · {w.get('pool_id')} · {_family_display_name(w.get('family'))} · {w.get('name')}")
        if st.button("RUN FRESH FORWARD · WINNER ONLY",type="primary",use_container_width=True,key=f"factory_fresh_{selected}"):
            persist_user_settings(); runtime=write_runtime_cfg(cfg,f"factory_fresh_{selected}.json"); bar,slot,cb=_factory_progress_ui()
            try:
                res=run_fresh(fd,dataset,runtime,progress=cb); bar.progress(100); slot.success(res["status"]); st.rerun()
            except Exception as e:
                slot.error(str(e));
                with st.expander("Technical traceback"): st.code(traceback.format_exc())
    fe=fd/"fresh_evidence.json"
    if fe.exists():
        e=json.loads(fe.read_text(encoding="utf-8")); f=e.get("fresh") or {}; m=f.get("metrics") or {}; a=f.get("acceptance") or {}; st.markdown("#### Fresh Forward evidence")
        x,y,z,q=st.columns(4); x.metric("Status",e.get("status")); y.metric("Trades",f"{int(m.get('trades',0))} / {int((f.get('auto_trade_sample') or {}).get('minimum_trades',0))}"); z.metric("PF",_fmt(m.get("profit_factor"))); q.metric("Exp R",_fmt(m.get("expectancy_r"),"r"))
        if not a.get("passed"): st.error(f"Fresh FAIL · first gate {a.get('first_failed_gate')} · runner-up fallback FORBIDDEN")


def _factory_selector(key: str="factory_selected_stage") -> Path | None:
    runs=_factory_runs()
    if not runs:
        st.info("Belum ada Factory lineage.")
        return None
    names=[x.name for x in runs]
    current=st.session_state.get("factory_selected") or names[0]
    if current not in names: current=names[0]
    name=st.selectbox("Factory lineage",names,index=names.index(current),key=key)
    st.session_state["factory_selected"]=name
    return FACTORY_DIR/name


def _factory_dataset_for_agent() -> Path | None:
    fd=None
    selected=st.session_state.get("factory_selected")
    if selected and (FACTORY_DIR/selected/"factory_manifest.json").exists(): fd=FACTORY_DIR/selected
    elif _factory_runs(): fd=_factory_runs()[0]
    if fd:
        fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8"))
        p=Path(str(fm.get("source_master") or ""))
        if p.exists(): return p
    choice=st.session_state.get("factory_source","Auto-detect MT5")
    if choice=="Custom path":
        p=Path(str(st.session_state.get("factory_path") or "").strip().strip('"'))
        if p.exists(): return p
    if choice=="Upload CSV":
        p=CACHE_DIR/"uploaded_training.csv"
        if p.exists(): return p
    return default_mt5_training_csv()


def _selected_factory_for_agent() -> Path | None:
    selected=st.session_state.get("factory_selected")
    if selected and (FACTORY_DIR/selected/"factory_manifest.json").exists(): return FACTORY_DIR/selected
    runs=_factory_runs(); return runs[0] if runs else None


def _agent_progress_callback(slot):
    def cb(p):
        stage=str(p.get("stage") or "research"); cur=p.get("current",0); total=p.get("total",1); msg=str(p.get("message") or stage)
        slot.caption(f"{stage} · {cur}/{total} · {msg}")
    return cb


def _execute_scientist_action(action: str, cfg: dict, progress_slot) -> dict:
    action=str(action or "NONE").upper(); dataset=_factory_dataset_for_agent(); fd=_selected_factory_for_agent()
    if action=="NONE": return {"status":"NO_ACTION"}
    if dataset is None or not Path(dataset).exists(): raise RuntimeError("Dataset master tidak tersedia untuk action Scientist")
    persist_user_settings()
    if action=="START_DISCOVERY":
        fc=cfg.get("champion_factory") or {}
        required=("discovery_from","discovery_to","tournament_from","tournament_to","fresh_from")
        miss=[k for k in required if not fc.get(k)]
        if miss: raise RuntimeError("Data contract belum lengkap: "+", ".join(miss))
        job=_start_discovery_background(cfg,Path(dataset))
        st.session_state["factory_discovery_job_id"]=job["job_id"]
        return {"status":"STARTED_BACKGROUND","job_id":job["job_id"],"factory":job.get("factory_id"),"qualified":0,"target":job.get("target",12)}
    if fd is None: raise RuntimeError("Factory lineage belum tersedia")
    runtime=write_runtime_cfg(cfg,f"scientist_{action.lower()}_{fd.name}.json")
    payload={"factory_dir":str(fd),"dataset":str(dataset),"config_path":str(runtime)}
    if action=="RUN_TOURNAMENT": job=start_factory_job(FACTORY_DIR,APP_DIR,"TOURNAMENT",payload)
    elif action=="RUN_MONTE_CARLO": job=start_factory_job(FACTORY_DIR,APP_DIR,"MONTE_CARLO",payload)
    elif action=="RUN_FORWARD": job=start_factory_job(FACTORY_DIR,APP_DIR,"FORWARD",payload)
    else: raise RuntimeError(f"Scientist action tidak di-whitelist: {action}")
    st.session_state[f"factory_{action.lower()}_job_id"]=job["job_id"]
    return {"status":"STARTED_BACKGROUND","job_id":job["job_id"],"factory":fd.name}


def _render_data_stage(cfg: dict):
    _page_header("Data", "Research workspace")
    dataset=resolve_dataset("factory"); ok=dataset_card(dataset)
    if not ok or dataset is None: return
    info=available_date_range(dataset); dates=info["available_dates"]; lo=dates[0]; hi=dates[-1]; fc=cfg.setdefault("champion_factory",{})
    def clamp(raw,fallback):
        try: d=pd.Timestamp(raw).date()
        except Exception: d=fallback
        return min(max(d,lo),hi)
    d1=clamp(fc.get("discovery_from"),lo); d2=clamp(fc.get("discovery_to"),min(hi,pd.Timestamp("2022-12-31").date())); t1=clamp(fc.get("tournament_from"),max(lo,pd.Timestamp("2023-01-01").date())); t2=clamp(fc.get("tournament_to"),min(hi,pd.Timestamp("2025-12-31").date())); f1=clamp(fc.get("fresh_from"),max(lo,pd.Timestamp("2026-01-01").date()))

    with st.expander(f"Research windows · Available {lo} → {hi}", expanded=True):
        st.caption("Chronology is visible by default because these windows define the scientific authority boundary.")
        c1,c2,c3=st.columns(3,gap="large")
        with c1:
            _subsection_header("Discovery", "Research + WFA/OOF window", first=True)
            discovery_from=st.date_input("From",d1,min_value=lo,max_value=hi,key="factory_discovery_from")
            discovery_to=st.date_input("To",d2,min_value=lo,max_value=hi,key="factory_discovery_to")
        with c2:
            _subsection_header("Tournament", "Independent validation window", first=True)
            tournament_from=st.date_input("From",t1,min_value=lo,max_value=hi,key="factory_tournament_from")
            tournament_to=st.date_input("To",t2,min_value=lo,max_value=hi,key="factory_tournament_to")
        with c3:
            _subsection_header("Forward · fresh", "Growing untouched validation", first=True)
            forward_from=st.date_input("From",f1,min_value=lo,max_value=hi,key="factory_fresh_from")
            st.text_input("To",value=f"AUTO_NEWEST · {hi}",disabled=True,key="factory_fresh_auto")
        valid=discovery_from<=discovery_to<tournament_from<=tournament_to<forward_from<=hi
        if not valid: st.error("Split overlap / tidak chronological. Wajib Discovery < Tournament < Forward Championship.")
        fc.update({"discovery_from":str(discovery_from),"discovery_to":str(discovery_to),"tournament_from":str(tournament_from),"tournament_to":str(tournament_to),"fresh_from":str(forward_from),"fresh_to":str(hi),"fresh_to_mode":"AUTO_NEWEST"})
        _subsection_header("Stress budget", "Monte Carlo applies only after Tournament survivors.")
        sim_col,_=st.columns([1,2.4]); fc["monte_carlo_simulations"]=int(sim_col.number_input("Monte Carlo simulations / survivor",100,500000,int(fc.get("monte_carlo_simulations",10000)),1000,key="monte_carlo_simulations"))
        try:
            ident=quick_summary(dataset); ds=auto_trade_sample(ident["period"],discovery_from,discovery_to,cfg,"DISCOVERY",observed_fraction=.50); ts=auto_trade_sample(ident["period"],tournament_from,tournament_to,cfg,"TOURNAMENT"); fs=auto_trade_sample(ident["period"],forward_from,hi,cfg,"FRESH")
            _subsection_header("AUTO sample preview", "Minimum closed-trade sufficiency before performance interpretation.")
            _stat_strip([
                ("Discovery OOF min",ds["minimum_trades"],"trades"),
                ("Tournament min",ts["minimum_trades"],"trades"),
                ("Forward min",fs["minimum_trades"],"trades"),
                ("Chronology","PASS" if valid else "FAIL","window ordering"),
            ])
        except Exception as e: st.warning(f"AUTO trade preview: {e}")

    with st.expander("Compute backend · current resolved plan",expanded=False):
        try:
            plan=resolve_compute_plan(cfg); st.dataframe(pd.DataFrame(compact_compute_status(plan,cfg)),use_container_width=True,hide_index=True)
        except Exception as e: st.warning(str(e))
    try: _data_fd=_factory_for_live_summary()
    except Exception: _data_fd=None
    if _data_fd is not None: _render_stage_scientist(_data_fd,"DATA")

def _factory_job_fraction(job: dict) -> float:
    status=str(job.get("status") or "")
    if status=="COMPLETED": return 1.0
    ev=dict(job.get("last_event") or {}); stage=str(ev.get("stage") or "")
    if stage=="onnx_preflight":
        total=max(1,int(ev.get("total",1) or 1)); cur=int(ev.get("current",0) or 0)
        return min(.06,.01+.05*cur/total)
    if str(job.get("action")).upper()=="DISCOVERY":
        max_gen=max(1,int((job.get("payload") or {}).get("max_generations",8) or 8))
        gen=max(1,int(job.get("generation",1) or 1))
        if stage=="factory_generation_done":
            return min(.96,.06+.90*gen/max_gen)
        if stage in {"cv","fidelity_screen","agent_round","scientist","diagnostic","onnx_preflight_reuse"}:
            ci=int(ev.get("candidate_index",ev.get("current",0)) or 0); ct=max(1,int(ev.get("candidate_total",ev.get("total",1)) or 1))
            return min(.95,.06+.90*((gen-1)+min(1,ci/ct))/max_gen)
        return min(.95,.06+.90*max(0,gen-1)/max_gen)
    cur=int(ev.get("current",0) or 0); total=max(1,int(ev.get("total",1) or 1))
    return min(.98,max(.02,cur/total))


def _factory_candidate_view(rows: list[dict]) -> pd.DataFrame:
    if not rows: return pd.DataFrame()
    cols=["Factory Cycle","Generation","Exp","Round","Model","Family","Stage","PASS","First fail","Fails","Closest fail","Margin %","DD R","Worst DD","Recovery","Worst RF","PF","Exp R","Worst R","Positive folds","Stress 1.50","Plateau","Trades","Memory M","Coverage","Score","Fit s"]
    out=[]
    for r in rows:
        x={k:r.get(k) for k in cols}
        # Backward-compatible display alias. Older committed telemetry used `Overall R`
        # while the table header expected `Exp R`, which rendered an ambiguous None.
        if x.get("Exp R") is None:
            x["Exp R"]=r.get("Overall R")
        # UI-only family parser: never expose canonical hybrid::... IDs in tables.
        if x.get("Family") not in (None, ""):
            x["Family"]=_family_display_name(x.get("Family"))
        if x.get("First fail"):
            x["First fail"]=_ui_gate_name(x.get("First fail"))
        out.append(x)
    return pd.DataFrame(out)



def _selected_dataframe_row(event) -> int | None:
    """Return the single selected row index from Streamlit dataframe selection."""
    try:
        rows=list(event.selection.rows)
    except Exception:
        try:
            rows=list(((event or {}).get("selection") or {}).get("rows") or [])
        except Exception:
            rows=[]
    if not rows:
        return None
    try:
        return int(rows[0])
    except Exception:
        return None


def _render_model_detail(detail: dict, *, key: str):
    params=dict(detail.get("parameters") or {})
    family=str(detail.get("family") or "—")
    _subsection_header("Model detail", "Frozen candidate setup · read-only inspector")
    count=detail.get("parameter_count")
    scope=str(detail.get("parameter_count_scope") or "")
    if count is None and scope=="TREE_STRUCTURE_DATA_DEPENDENT":
        size_text="Data-dependent tree structure"
    else:
        size_text=_format_parameter_count(count)
        if count is not None and scope=="EXECUTABLE_ARCHITECTURE":
            size_text += " · executable architecture"
    _fact_grid([
        ("Model",str(detail.get("model") or "—")),
        ("Family",_family_display_name(family)),
        (str(detail.get("parameter_count_label") or "Trainable parameters"),size_text),
        ("Seed",str(detail.get("training_seed") if detail.get("training_seed") is not None else "—")),
        ("Threshold",str(detail.get("take_threshold") if detail.get("take_threshold") is not None else "—")),
    ],wide_labels={"Model"})
    if detail.get("pool_id") or detail.get("trained_candidate_id"):
        st.caption(" · ".join(x for x in [
            f"Pool {detail.get('pool_id')}" if detail.get("pool_id") else "",
            f"Trained ID {str(detail.get('trained_candidate_id'))[:18]}" if detail.get("trained_candidate_id") else "",
            f"Source {detail.get('source')}" if detail.get("source") else "",
        ] if x))
    tree=dict(detail.get("tree_complexity") or {})
    if tree:
        bits=[]
        labels={"n_estimators":"trees","max_depth":"max depth","num_leaves":"leaves","min_child_weight":"min child weight","subsample":"subsample","colsample_bytree":"colsample"}
        for k in ("n_estimators","max_depth","num_leaves","min_child_weight","subsample","colsample_bytree"):
            if tree.get(k) is not None:
                bits.append(f"{labels[k]} {tree[k]}")
        if bits:
            upper=tree.get("structural_node_upper_bound")
            upper_text=f" · structural upper bound {_format_parameter_count(upper)} nodes" if upper is not None else ""
            st.caption("Tree/policy complexity · "+" · ".join(bits)+upper_text+" · exact fitted node count is data-dependent")
    if not params:
        st.warning("Exact candidate parameters are unavailable in this historical artifact; MAX will not reconstruct or guess them.")
        return
    setup_rows=model_parameter_groups(family,params)
    st.dataframe(pd.DataFrame(setup_rows),use_container_width=True,hide_index=True,height=min(480,88+30*len(setup_rows)),key=f"{key}_params")


def _model_table(display_rows, raw_rows, *, key: str, factory_dir: Path | None = None, run_dirs: list[Path | None] | None = None, height: int | None = None):
    """Selectable model list shared by every Research candidate surface.

    Selection is UI-only. Candidate authority is resolved from frozen evidence and is
    never written back into the research lifecycle.
    """
    df=display_rows if isinstance(display_rows,pd.DataFrame) else pd.DataFrame(display_rows or [])
    if df.empty:
        return None
    kwargs={"use_container_width":True,"hide_index":True,"on_select":"rerun","selection_mode":"single-row","key":key}
    if height is not None:
        kwargs["height"]=height
    event=st.dataframe(df,**kwargs)
    idx=_selected_dataframe_row(event)
    if idx is None or idx<0 or idx>=len(raw_rows or []):
        st.caption("Klik satu baris model untuk melihat ukuran dan exact parameter setup.")
        return None
    raw=dict((raw_rows or [])[idx] or {})
    rd=None
    if run_dirs and idx<len(run_dirs):
        rd=run_dirs[idx]
    if rd is None and raw.get("run_dir"):
        try: rd=Path(str(raw.get("run_dir")))
        except Exception: rd=None
    detail=resolve_model_detail(factory_dir=factory_dir,row=raw,run_dir=rd)
    _render_model_detail(detail,key=key)
    return detail


def _live_status_strip(title: str, message: str, *, meta: str = "", spinning: bool = True):
    spinner='<span class="cp-busy-spinner"></span>' if spinning else '<span class="cp-top-dot"></span>'
    meta_html=f'<span class="cp-live-meta">{html.escape(str(meta))}</span>' if meta else ''
    st.markdown(f'<div class="cp-live-status">{spinner}<strong>{html.escape(str(title))}</strong><span>{html.escape(str(message))}</span>{meta_html}</div>',unsafe_allow_html=True)


def _render_research_health(rows: list[dict]):
    """Deterministic research state; LLM narrative never overrides this panel."""
    if not rows:
        return
    total=len(rows); passed=sum(1 for r in rows if str(r.get("PASS") or "").upper()=="YES")
    fail_counts={}
    for r in rows:
        if str(r.get("PASS") or "").upper()=="YES":
            continue
        g=str(r.get("First fail") or "UNKNOWN")
        fail_counts[g]=int(fail_counts.get(g,0))+1
    if passed==0:
        st.warning(f"RESEARCH HEALTH · NO WFA SURVIVOR · 0/{total} candidate PASS. LLM tidak boleh menyebut frontier ini optimal/robust; lihat gate blocker di bawah.")
    else:
        st.success(f"RESEARCH HEALTH · WFA SURVIVORS PRESENT · {passed}/{total} candidate PASS.")
    if fail_counts:
        ranked=sorted(fail_counts.items(),key=lambda kv:(-kv[1],kv[0]))[:8]
        st.caption("First failed gate distribution · " + " · ".join(f"{k}: {v}" for k,v in ranked))


def _scientist_reports_from_events(job_id: str) -> list[dict]:
    """Return Scientist reports already committed to the background job event stream."""
    out=[]
    for ev in read_factory_events(FACTORY_DIR,job_id,600):
        note=ev.get("scientist_update")
        if isinstance(note,dict):
            x=dict(note)
            if ev.get("factory_generation") is not None: x.setdefault("factory_generation",ev.get("factory_generation"))
            if ev.get("factory_id"): x.setdefault("factory_id",ev.get("factory_id"))
            if ev.get("utc"): x.setdefault("created_utc",ev.get("utc"))
            out.append(x)
    return out


def _scientist_reports_from_factory(fd: Path | None) -> list[dict]:
    """Aggregate Factory Research Director plus per-generation Scientist journals."""
    if not fd or not Path(fd).exists(): return []
    fd=Path(fd); rows=[]
    dj=fd/"research_director_journal.json"
    try:
        data=json.loads(dj.read_text(encoding="utf-8"))
        if isinstance(data,list):
            for e in data:
                if isinstance(e,dict):
                    x=dict(e); x.setdefault("source","FACTORY_RESEARCH_DIRECTOR"); rows.append(x)
    except Exception: pass
    dp={}
    try: dp=json.loads((fd/"discovery_progress.json").read_text(encoding="utf-8"))
    except Exception: pass
    run_ids=list(dp.get("generation_runs") or [])
    if not run_ids:
        rr=fd/"research_runs"
        if rr.exists(): run_ids=[p.name for p in sorted(rr.iterdir()) if p.is_dir()]
    for generation,rid in enumerate(run_ids,1):
        jp=fd/"research_runs"/str(rid)/"scientist_journal.json"
        try:
            data=json.loads(jp.read_text(encoding="utf-8"))
            if isinstance(data,list):
                for e in data:
                    if isinstance(e,dict):
                        x=dict(e); x.setdefault("source_run",str(rid)); x.setdefault("factory_generation",generation); rows.append(x)
        except Exception: pass
    sj=fd/"stage_scientist_journal.json"
    try:
        data=json.loads(sj.read_text(encoding="utf-8"))
        if isinstance(data,list):
            for e in data:
                if isinstance(e,dict): rows.append(dict(e))
    except Exception: pass
    return rows


def _render_llm_research_report(job_id: str | None=None, fd: Path | None=None):
    entries=[]
    if job_id: entries.extend(_scientist_reports_from_events(str(job_id)))
    persisted=_scientist_reports_from_factory(fd)
    # Event stream and persisted journals can contain the same report. Preserve
    # Factory generation/source identity so reports from later generations cannot be
    # incorrectly de-duplicated just because round/summary text repeats.
    seen=set(); merged=[]
    for e in entries+persisted:
        rid=str(e.get("report_id") or "")
        key=("id",rid) if rid else ("legacy",str(e.get("factory_id") or ""),str(e.get("factory_generation") or ""),str(e.get("source_run") or ""),str(e.get("round") or ""),str(e.get("phase") or ""),str(e.get("summary") or ""))
        if key in seen: continue
        seen.add(key); merged.append(e)
    merged.sort(key=lambda e:(str(e.get("created_utc") or ""),int(e.get("factory_generation",0) or 0),int(e.get("round",0) or 0)))

    with st.expander("LLM Research Director / Scientist Report", expanded=True):
        _render_llm_route_health(_ui_llm_cfg(),compact=True)
        if not merged:
            st.caption("Research Director pre-flight akan muncul sebelum Generation 1; Scientist kemudian melapor pada committed research boundaries.")
        else:
            latest=merged[-1]
            agg=_aggregate_llm_usage(merged)
            # Acceptance/search authority label retained without duplicating it visually: LLM USAGE · CURRENT JOURNAL
            _subsection_header("LLM Usage", "Current journal", first=True)
            uc=st.columns(5,gap="small")
            input_display=_fmt_tokens(agg["input_tokens"]) if agg["input_known_calls"]==agg["calls"] and agg["calls"] else (f"{_fmt_tokens(agg['input_tokens'])} known" if agg["input_known_calls"] else "—")
            total_display=_fmt_tokens(agg["total_tokens"]) if agg["total_known_calls"]==agg["calls"] and agg["calls"] else (f"{_fmt_tokens(agg['total_tokens'])} known" if agg["total_known_calls"] else "partial")
            uc[0].metric("Calls",agg["calls"]); uc[1].metric("Input",input_display); uc[2].metric("Output",_fmt_tokens(agg["output_tokens"])); uc[3].metric("Total",total_display); uc[4].metric("Known cost",_fmt_cost(agg["known_cost_usd"],partial=bool(agg["partial_cost_calls"])) if agg["cost_calls"] else "Pricing not set")
            st.caption(f"Fallback {agg['fallbacks']} · Estimated {agg['estimated_usage_calls']} · Priced {agg['cost_calls']}/{agg['calls']}")
            _subsection_header("Latest committed analysis", "Complete latest Scientist report; no inner card disclosure.")
            _render_scientist_entry(latest,compact=False)

    if len(merged)>1:
        with st.expander(f"Full Scientist journal · {len(merged)} report",expanded=False):
            for i,e in enumerate(merged):
                if i: st.divider()
                _render_scientist_entry(e,compact=False)

def _start_auto_background(cfg: dict, dataset: Path) -> dict:
    fc=cfg.setdefault("champion_factory",{})
    # UI MUST NOT run broker reconciliation synchronously.  That audit can touch
    # MT5/broker history and may take long enough to pin the STARTING frame.
    # Spawn the owned Factory worker first; it performs the exact same fail-closed
    # Data Quality gate as its first authoritative stage.  This keeps START/STOP
    # responsive while preserving the R6 scientific gate.
    hi=available_date_range(dataset)["available_dates"][-1]
    runtime=write_runtime_cfg(cfg,"champion_factory_auto_runtime.json")
    payload={
        "dataset":str(dataset),"config_path":str(runtime),
        "run_data_quality_preflight":True,
        "discovery_from":str(fc["discovery_from"]),"discovery_to":str(fc["discovery_to"]),
        "tournament_from":str(fc["tournament_from"]),"tournament_to":str(fc["tournament_to"]),
        "fresh_from":str(fc["fresh_from"]),"fresh_to":str(hi),
        "target":int(fc.get("target_pool",12)),"max_generations":int(fc.get("max_generations",8)),
        "max_total_experiments":int(fc.get("max_total_experiments",216)),
        "orchestrator_max_cycles":int(fc.get("orchestrator_max_cycles",0) or 0),
    }
    return start_factory_job(FACTORY_DIR,APP_DIR,"AUTO",payload)


def _start_manual_background(cfg: dict, dataset: Path) -> dict:
    runtime_cfg, validated = compile_manual_runtime(cfg)
    fc=runtime_cfg.setdefault("champion_factory",{})
    hi=available_date_range(dataset)["available_dates"][-1]
    runtime=write_runtime_cfg(runtime_cfg,"champion_factory_manual_runtime.json")
    payload={
        "dataset":str(dataset),"config_path":str(runtime),
        "run_data_quality_preflight":True,
        "discovery_from":str(fc["discovery_from"]),"discovery_to":str(fc["discovery_to"]),
        "tournament_from":str(fc["tournament_from"]),"tournament_to":str(fc["tournament_to"]),
        "fresh_from":str(fc["fresh_from"]),"fresh_to":str(hi),
        "target":len(validated),"max_generations":1,"max_total_experiments":len(validated),
        "research_mode":"MANUAL",
    }
    return start_factory_job(FACTORY_DIR,APP_DIR,"MANUAL",payload)


def _current_generation_wfa_counts(rows: list[dict], job: dict) -> tuple[int,int]:
    """Return current Factory-cycle/generation Full-WFA evaluated/PASS counts."""
    rr=[r for r in (rows or []) if str(r.get("Stage") or "").upper()=="FULL WFA"]
    try:
        cycle=int(job.get("orchestrator_cycle",0) or 0)
    except Exception:
        cycle=0
    if cycle:
        scoped=[r for r in rr if int(r.get("Factory Cycle",0) or 0)==cycle]
        if scoped: rr=scoped
    try:
        gen=int(job.get("generation",0) or 0)
    except Exception:
        gen=0
    if gen:
        scoped=[r for r in rr if int(r.get("Generation",0) or 0)==gen]
        if scoped: rr=scoped
    passed=sum(1 for r in rr if str(r.get("PASS") or "").strip().upper() in {"YES","PASS","TRUE","1"})
    return len(rr),passed


def _render_pool_projection(job: dict, rows: list[dict] | None = None):
    """Explain committed/pending/projected Pool using Supervisor safe-boundary telemetry."""
    rows=rows if rows is not None else read_factory_candidates(FACTORY_DIR,str(job.get("job_id") or ""))
    evaluated,wfa_pass=_current_generation_wfa_counts(rows or [],job)
    committed=int(job.get("qualified",0) or 0); target=int(job.get("target",12) or 12)
    pending=int(job.get("pending_pool_eligible",0) or 0)
    projected=int(job.get("projected_pool",committed) or committed)
    _stat_strip([
        ("COMMITTED POOL",f"{committed}/{target}","scientific authority"),
        ("CURRENT GEN FULL WFA",f"{evaluated} eval",f"{wfa_pass} PASS"),
        ("UNIQUE PENDING ELIGIBLE",pending,"safe-boundary telemetry"),
        ("PROJECTED POOL",f"{projected}/{target}","projection only"),
    ])
    authority=str(job.get("pool_projection_authority") or "")
    if bool(job.get("pool_target_reached")) and committed<target:
        st.success("POOL TARGET REACHED · finishing current safe round / atomic generation commit")
    elif authority:
        st.caption("Pending/projected counts are exact at the last completed safe round boundary; only committed Pool is scientific authority.")


def _start_discovery_background(cfg: dict, dataset: Path) -> dict:
    fc=cfg.setdefault("champion_factory",{})
    hi=available_date_range(dataset)["available_dates"][-1]
    runtime=write_runtime_cfg(cfg,"champion_factory_runtime.json")
    payload={
        "dataset":str(dataset),"config_path":str(runtime),
        "discovery_from":str(fc["discovery_from"]),"discovery_to":str(fc["discovery_to"]),
        "tournament_from":str(fc["tournament_from"]),"tournament_to":str(fc["tournament_to"]),
        "fresh_from":str(fc["fresh_from"]),"fresh_to":str(hi),
        "target":int(fc.get("target_pool",12)),"max_generations":int(fc.get("max_generations",8)),
        "max_total_experiments":int(fc.get("max_total_experiments",216)),
    }
    return start_factory_job(FACTORY_DIR,APP_DIR,"DISCOVERY",payload)


@st.fragment(run_every="2s", key="factory_job_live_monitor")
def _render_factory_job_monitor(job_id: str):
    """Flat read-only live monitor. This fragment polls committed job evidence every 2 seconds."""
    job=load_factory_job(FACTORY_DIR,job_id)
    if not job: return
    status=str(job.get("status") or "UNKNOWN"); ev=dict(job.get("last_event") or {}); action=str(job.get("action") or "").upper()
    frac=_factory_job_fraction(job); msg=str(ev.get("message") or status)
    q=int(job.get("qualified",0) or 0); target=int(job.get("target",12) or 12)
    rows=read_factory_candidates(FACTORY_DIR,job_id) if action in {"DISCOVERY","AUTO","MANUAL"} else []
    fid=str(job.get("factory_id") or (job.get("payload") or {}).get("factory_id") or (ev.get("factory_id") or ""))
    report_fd=(FACTORY_DIR/fid) if fid else None

    # Deliberately not inside an expander/card: live activity must remain visually flat
    # and repaint on the root 2-second runtime poll without manual browser refresh.
    live_meta=(f"pool {q}/{target}" if action in {"DISCOVERY","AUTO","MANUAL"} else action or "Factory")
    _live_status_strip(f"{action or 'Research'} · {status}",msg,meta=live_meta,spinning=status in FACTORY_ACTIVE_STATUSES)
    st.progress(int(max(0,min(1,frac))*100),text=f"Research progress · {frac*100:.0f}%")
    if status=="INTERRUPTED":
        st.warning("Worker lama tidak hidup (restart/crash). Evidence committed tetap aman; RESUME melanjutkan dari atomic checkpoint terakhir.")
    elif status=="PAUSED":
        if str(job.get("pause_reason") or "")=="WAITING_FOR_SCIENTIST_REVIEW":
            st.warning("Research menunggu mandatory LLM Scientist post-mortem. RESUME akan retry Scientist dari evidence committed tanpa mengulang validation stage.")
        else:
            st.info("Research PAUSED pada checkpoint aman. Resume tidak mereset Factory.")
    elif status=="PAUSE_REQUESTED":
        st.info("Pause diminta. Worker akan berhenti pada control/checkpoint boundary berikutnya.")
    elif status=="STOP_REQUESTED":
        st.warning("STOP sedang diverifikasi. Research tidak dianggap berhenti sebelum worker process benar-benar mati.")
    elif status=="STOP_FAILED":
        sv=job.get("stop_verification") or {}; alive=sv.get("alive_after") or []
        st.error(f"STOP FAILED · worker masih hidup: {alive}. Gunakan FORCE STOP; status tidak dipalsukan sebagai STOPPED.")

    if action in {"DISCOVERY","AUTO","MANUAL"}:
        with st.expander("Pool & qualification", expanded=True):
            _render_pool_projection(job,rows)
            if not rows:
                st.caption("Belum ada candidate selesai. Leaderboard akan muncul otomatis setelah candidate pertama selesai.")

    if status in {"QUEUED","RUNNING","PAUSE_REQUESTED","STOP_REQUESTED","PAUSED","INTERRUPTED"}:
        st.caption("Live status refreshes automatically every 2 seconds. Lifecycle controls remain process-authoritative.")

    if status=="FAILED": st.error(str(job.get("error") or "Factory worker failed"))
    elif status=="STOPPED": st.warning("Job dihentikan. Last committed checkpoint tetap tersedia untuk RESUME.")
    elif status=="ABORTED": st.warning("Job di-abort permanen. Job ini tidak resumable; START RESEARCH membuat cycle baru.")
    elif status=="COMPLETED":
        res=job.get("result") or {}; detail=""
        if res.get("survivors") is not None: detail+=f" · survivors {res.get('survivors')}"
        if res.get("simulations") is not None: detail+=f" · MC {int(res.get('simulations')):,}"
        if res.get("champion"): detail+=f" · Champion {(res.get('champion') or {}).get('pool_id')}"
        if action in {"DISCOVERY","AUTO","MANUAL"}: detail+=f" · pool {res.get('qualified',q)}/{res.get('target',target)}"
        st.success(f"{res.get('status','COMPLETED')}{detail}")

    if action in {"DISCOVERY","AUTO","MANUAL"} and rows:
        with st.expander(f"Live candidate leaderboard · {len(rows)} recorded", expanded=True):
            _render_research_health(rows)
            _model_table(_factory_candidate_view(rows),rows,key=f"live_factory_models_{job_id}",factory_dir=report_fd,height=min(560,92+34*min(len(rows),14)))

    if action in {"DISCOVERY","AUTO"}:
        _render_llm_research_report(job_id,report_fd)
    events=read_factory_events(FACTORY_DIR,job_id,20)
    if events:
        with st.expander("Progress / event log",expanded=False):
            st.dataframe(pd.DataFrame([{"Stage":e.get("stage"),"Progress":f"{e.get('current','')}/{e.get('total','')}","Message":e.get("message")} for e in events]),use_container_width=True,hide_index=True)

def _known_factory_dataset() -> Path | None:
    choice=str(st.session_state.get("factory_source") or "Auto-detect MT5")
    if choice=="Auto-detect MT5":
        return default_mt5_training_csv()
    if choice=="Upload CSV":
        p=CACHE_DIR/"uploaded_training.csv"
        return p if p.exists() else None
    text=str(st.session_state.get("factory_path") or "").strip().strip('"')
    if text:
        p=Path(text)
        if p.exists() and p.is_file(): return p
    return None


def _latest_resumable_research_job() -> dict | None:
    candidates=[]
    for action in ("AUTO","MANUAL","DISCOVERY"):
        j=latest_factory_job(FACTORY_DIR,action,active_only=False)
        if j and factory_job_is_resumable(FACTORY_DIR,j): candidates.append(j)
    if not candidates: return None
    candidates.sort(key=lambda j:str(j.get("created_utc") or ""),reverse=True)
    return candidates[0]


def _ui_gate_name(name) -> str:
    g=str(name or "—")
    return ("WFA_"+g[3:]) if g.startswith("CV_") else g


def _factory_for_live_summary() -> Path | None:
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    if active:
        fid=str(active.get("factory_id") or (active.get("last_event") or {}).get("factory_id") or "")
        if fid:
            # Never fall back to a historical selection while a newer cycle is active.
            return FACTORY_DIR/fid
    selected=str(st.session_state.get("factory_selected") or "")
    if selected and (FACTORY_DIR/selected/"factory_manifest.json").exists(): return FACTORY_DIR/selected
    runs=_factory_runs(); return runs[0] if runs else None


def _render_stage_scientist(fd: Path, stage: str):
    rows=[e for e in _scientist_reports_from_factory(fd) if str(e.get("stage") or "").upper()==str(stage).upper()]
    if not rows: return
    rows.sort(key=lambda e:str(e.get("created_utc") or ""))
    with st.expander("Scientist · latest stage analysis",expanded=False):
        _render_scientist_entry(rows[-1],compact=False)

def _render_cpcv_candidate_scientist(fd: Path):
    rows=[e for e in _scientist_reports_from_factory(fd) if str(e.get("stage") or "").upper()=="CPCV_CANDIDATE"]
    if not rows:
        st.caption("LLM Scientist · per-candidate CPCV review belum tersedia.")
        return
    rows.sort(key=lambda e:str(e.get("created_utc") or ""))
    with st.expander(f"LLM Scientist · CPCV candidate reviews · {len(rows)}",expanded=False):
        for i,e in enumerate(rows[-12:]):
            if i: st.divider()
            _render_scientist_entry(e,compact=True)


@st.fragment(run_every="2s")
def _render_stage_live_header(stage: str, fd: Path):
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    if not active: return
    fid=str(active.get("factory_id") or "")
    if fid and fid!=fd.name: return
    ev=dict(active.get("last_event") or {}); msg=str(ev.get("message") or "")
    stage_u=str(stage).upper(); ev_stage=str(ev.get("stage") or "").upper()
    aliases={"DISCOVERY":{"CV","FIDELITY_SCREEN","FACTORY_DISCOVERY","FACTORY_GENERATION_DONE","SCIENTIST","RESEARCH_DIRECTOR","POOL_PROJECTION"},"POOL":{"FACTORY_DISCOVERY","FACTORY_GENERATION_DONE","POOL_PROJECTION"},"CPCV":{"CPCV","CPCV_FINALIST"},"TOURNAMENT":{"FACTORY_TOURNAMENT"},"MONTE_CARLO":{"MONTE_CARLO"},"FORWARD":{"FORWARD_CHAMPIONSHIP"}}
    if ev_stage not in aliases.get(stage_u,{stage_u}): return
    c,t=ev.get("current"),ev.get("total"); prog=f"{c}/{t}" if c is not None and t is not None else ""
    st.markdown(f'<div class="cp-activity"><strong>Current activity</strong><span>{html.escape(stage_u)} · {html.escape(prog)} · {html.escape(msg)}</span></div>',unsafe_allow_html=True)

@st.fragment(run_every="2s")
def _render_research_live_summary():
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    active_fid=str((active or {}).get("factory_id") or ((active or {}).get("last_event") or {}).get("factory_id") or "")
    active_fd=(FACTORY_DIR/active_fid) if active_fid else None; fm={}; pool=[]
    if active_fd is not None:
        try: fm=json.loads((active_fd/"factory_manifest.json").read_text(encoding="utf-8"))
        except Exception: fm={}
        try: pool=json.loads((active_fd/"candidate_pool.json").read_text(encoding="utf-8"))
        except Exception: pool=[]
    if active:
        ev=active.get("last_event") or {}
        cycle=ev.get("orchestrator_cycle") or active.get("orchestrator_cycle")
        stage=str(ev.get("stage") or fm.get("stage") or active.get("action") or "STARTING").upper()
        status=str(fm.get("status") or active.get("status") or "RUNNING")
        target=int(fm.get("target_candidates",active.get("target",12)) or 12)
        q=int(fm.get("qualified_candidates",len(pool) or active.get("qualified",0)) or 0)
        evaluated=int(active.get("generation_evaluated",0) or 0); wfa_pass=int(active.get("generation_passed",0) or 0)
        frac=max(0.0,min(1.0,_factory_job_fraction(active)))
        with st.expander(f"ACTIVE RESEARCH CYCLE · Cycle {cycle or '—'} · {stage}", expanded=True):
            st.markdown(
                f'<div class="cp-health-strip"><div><div class="cp-health-main">{html.escape(active_fid or "Factory initializing")}</div>'
                f'<div class="cp-health-meta">Live telemetry from the committed Factory process</div></div>'
                f'<span class="cp-chip blue">{html.escape(status)}</span></div>',unsafe_allow_html=True)
            _stat_strip([
                ("Pool",f"{q}/{target}","committed"),
                ("WFA",f"{evaluated} eval",f"{wfa_pass} PASS"),
                ("Stage",stage,"current"),
                ("Progress",f"{frac*100:.0f}%","factory"),
            ])
            st.markdown(f'<div class="cp-activity"><strong>Current</strong><span>{html.escape(str(ev.get("message") or "Waiting for committed telemetry"))}</span></div>',unsafe_allow_html=True)

        rows=read_factory_candidates(FACTORY_DIR,str(active.get("job_id") or ""))
        if rows:
            current=[r for r in rows if str(r.get("Stage") or "").upper()=="FULL WFA"] or list(rows)
            current=current[-12:]
            view=[]
            for r in current:
                view.append({
                    "Gen":r.get("Generation"),
                    "Model":r.get("Model") or r.get("Candidate") or r.get("ID"),
                    "Family":_family_display_name(r.get("Family")),
                    "PASS":r.get("PASS"),
                    "First fail":r.get("First fail"),
                    "Margin %":r.get("Margin %"),
                    "Worst R":r.get("Worst R") or r.get("Worst Exp"),
                    "DD R":r.get("DD R") or r.get("Worst DD"),
                    "Recovery":r.get("Recovery") or r.get("Worst Recovery"),
                })
            with st.expander(f"Live candidates · {len(current)} recent", expanded=True):
                _model_table(view,current,key=f"research_live_summary_{active.get('job_id')}",factory_dir=active_fd,height=min(390,82+31*len(view)))

        reports=_scientist_reports_from_factory(active_fd) if active_fd and active_fd.exists() else []
        if reports:
            reports.sort(key=lambda e:str(e.get("created_utc") or ""))
            latest=reports[-1]
            summary=str(latest.get("summary") or latest.get("conclusion") or "").strip()
            model_info=_scientist_usage(latest)
            model=str((model_info.get("provenance") or {}).get("selected_model") or "Scientist")
            conf=latest.get("confidence")
            right=f"{model}" + (f" · {float(conf)*100:.0f}%" if isinstance(conf,(int,float)) and float(conf)<=1 else (f" · {conf}%" if conf not in (None,"") else ""))
            with st.expander(f"Scientist · latest committed analysis · {right}", expanded=True):
                st.markdown(f'<div class="cp-summary-body">{html.escape(summary or "Latest committed Scientist report available")}</div>',unsafe_allow_html=True)
                st.divider()
                _render_scientist_entry(latest,compact=False)
    else:
        st.info("Tidak ada active research cycle.")

    runs=_factory_runs(); previous=next((r for r in runs if r.name!=active_fid and (r/"factory_manifest.json").exists()),None)
    if previous is not None:
        try: pm=json.loads((previous/"factory_manifest.json").read_text(encoding="utf-8"))
        except Exception: pm={}
        with st.expander("PREVIOUS CYCLE",expanded=False):
            st.markdown(f"**{previous.name}** · `{pm.get('status') or 'UNKNOWN'}` · Pool {int(pm.get('qualified_candidates',0) or 0)}/{int(pm.get('target_candidates',12) or 12)}")

def _render_research_stage(cfg: dict):
    _page_header("Research", "Control room")
    _render_research_live_summary()


def _queue_global_research_start():
    # Event-only callback: return control to the browser immediately so the next
    # fragment render can grey the button and paint a visible startup indicator
    # before deterministic preflight/audit begins.
    st.session_state["pending_research_start"]={"requested_utc":datetime.utcnow().isoformat()+"Z","phase":"ARMED"}


def _queue_global_research_stop(job_id: str):
    st.session_state["pending_research_stop"]={"job_id":str(job_id),"requested_utc":datetime.utcnow().isoformat()+"Z","phase":"ARMED"}


def _render_global_optimizer_controls_body(cfg: dict):
    """Single contextual Optimizer lifecycle authority: START / RESUME / STOP."""
    job=latest_strategy_optimizer_job()
    status=str((job or {}).get("status") or "IDLE")
    active=bool(job and status in STRATEGY_OPTIMIZER_ACTIVE)
    recoverable=bool(job and status in STRATEGY_OPTIMIZER_RECOVERABLE)
    research_active=latest_factory_job(FACTORY_DIR,active_only=True)
    starting=bool(st.session_state.get("optimizer_starting",False))
    with st.container(key="global_optimizer_lifecycle"):
        if active:
            msg=str(job.get("message") or "MT5 optimizer is active").strip()
            round_no=int(job.get("round") or 0); max_rounds=int((job.get("request") or {}).get("max_rounds") or 1)
            label=f"Optimizer · {status.replace('_',' ').title()}" + (f" · Round {round_no}/{max_rounds}" if round_no>0 else "")
            _live_status_strip(label,msg,meta=status,spinning=True)
            if st.button("STOP OPTIMIZER",type="primary",use_container_width=True,key=f"global_optimizer_stop_{job.get('job_id')}"):
                try:
                    cancel_strategy_optimizer_job(str(job.get("job_id"))); st.session_state.pop("strategy_optimizer_lifecycle_error",None)
                except Exception as exc: st.session_state["strategy_optimizer_lifecycle_error"]=str(exc)
                _rerun_current_fragment()
        elif recoverable:
            _live_status_strip("Optimizer","Existing evidence pending",meta=status,spinning=False)
            st.caption("Resume never reruns the checkpointed MT5 round. After its evidence is parsed, no-winner results automatically continue to the next round within the frozen budget.")
            if st.button("RESUME AUTO OPTIMIZER",type="primary",use_container_width=True,key=f"global_optimizer_resume_{job.get('job_id')}"):
                try:
                    resume_strategy_optimizer_job(str(job.get("job_id"))); st.session_state.pop("strategy_optimizer_lifecycle_error",None)
                except Exception as exc: st.session_state["strategy_optimizer_lifecycle_error"]=str(exc)
                _rerun_current_fragment()
        else:
            install=_strategy_optimizer_install_from_session()
            try: canonical_ea_identity(); ea_ready=True
            except Exception: ea_ready=False
            blocked=research_active is not None or install is None or not ea_ready or starting
            if job and status=="NO_CHAMPION_MAX_ROUNDS":
                st.caption("Frozen maximum-round budget is exhausted without a Champion. Change settings if needed, then START creates a new frozen Optimizer request.")
            elif research_active: st.caption("Research is active · Optimizer start is locked.")
            elif install is None: st.caption("Configure the MT5 installation on Strategy Optimizer.")
            elif not ea_ready: st.caption("Canonical Max MTF v2.0 baseline EA source is missing or invalid.")
            label="STARTING…" if starting else "START AUTO OPTIMIZER"
            if blocked:
                st.button(label,type="primary",use_container_width=True,key="global_optimizer_start",disabled=True)
            else:
                st.button("START AUTO OPTIMIZER",type="primary",use_container_width=True,key="global_optimizer_start",on_click=_start_global_optimizer_clicked,args=(cfg,))
        err=str(st.session_state.get("strategy_optimizer_lifecycle_error") or "").strip()
        if err: st.markdown('<div class="cp-lifecycle-error">'+html.escape(err)+'</div>',unsafe_allow_html=True)

def _render_global_research_controls_body(cfg: dict):
    """Research-only footer body; mounted only outside the Strategy Optimizer/Challenger/Champion domain."""
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    latest_auto=latest_factory_job(FACTORY_DIR,"AUTO",active_only=False)
    latest_manual=latest_factory_job(FACTORY_DIR,"MANUAL",active_only=False)
    latest_disc=latest_factory_job(FACTORY_DIR,"DISCOVERY",active_only=False)
    resumable=None
    for cand in (latest_auto,latest_manual,latest_disc):
        if cand and factory_job_is_resumable(FACTORY_DIR,cand):
            resumable=cand; break

    # A real active worker supersedes any stale UI-only START pending marker.
    if active and st.session_state.get("pending_research_start"):
        st.session_state.pop("pending_research_start",None)

    with st.container(key="global_research_lifecycle"):
        if active:
            jid=str(active.get("job_id")); status=str(active.get("status") or "RUNNING")
            stop_req=st.session_state.get("pending_research_stop") or {}
            stopping=str(stop_req.get("job_id") or "")==jid
            if status in {"QUEUED","DATA_QUALITY_PREFLIGHT","RUNNING","PAUSE_REQUESTED","STOP_REQUESTED"}:
                # Loader/status always lives ABOVE lifecycle buttons.  This preserves
                # the bottom button row and uses the otherwise-empty footer space while
                # preflight / research work is active instead of clipping status below it.
                ev=dict(active.get("last_event") or {})
                stage=str(ev.get("stage") or active.get("action") or "RESEARCH").replace("_"," ").title()
                msg=str(ev.get("message") or "Research worker is active").strip()
                if stopping:
                    busy_text="Stopping research worker…"
                elif status=="QUEUED":
                    busy_text="Starting research worker…"
                elif status=="DATA_QUALITY_PREFLIGHT":
                    busy_text="Data Quality preflight · validating broker-backed research data…"
                else:
                    busy_text=f"{stage} · {msg}"
                _live_status_strip("Research",busy_text,meta=status,spinning=True)
                c1,c2=st.columns(2,gap="small")
                c1.button("PAUSE",use_container_width=True,key=f"factory_global_pause_{jid}",help="Pause at the next safe boundary",disabled=stopping,on_click=request_factory_pause,args=(FACTORY_DIR,jid))
                c2.button("STOPPING…" if stopping else "STOP",type="primary",use_container_width=True,key=f"factory_global_stop_{jid}",help="Stop research now",disabled=stopping,on_click=_queue_global_research_stop,args=(jid,))
                if stopping:
                    # Two-phase UI state guarantees the browser receives the disabled
                    # control/loading frame before taskkill can block for verification.
                    if str(stop_req.get("phase") or "ARMED")=="ARMED":
                        stop_req=dict(stop_req); stop_req["phase"]="EXECUTE"; st.session_state["pending_research_stop"]=stop_req; _rerun_current_fragment()
                    try:
                        request_factory_stop(FACTORY_DIR,jid)
                    except Exception as exc:
                        st.session_state["research_lifecycle_error"]=str(exc)
                    finally:
                        st.session_state.pop("pending_research_stop",None)
                    _rerun_current_fragment()
            elif st.button("FORCE STOP",type="primary",use_container_width=True,key=f"factory_global_force_{jid}"):
                force_factory_stop(FACTORY_DIR,jid); _rerun_current_fragment()
        elif resumable:
            st.session_state.pop("pending_research_stop",None)
            jid=str(resumable.get("job_id"))
            if str(resumable.get("status") or "")=="FAILED":
                rc=factory_failed_recovery_contract(FACTORY_DIR,resumable)
                st.markdown('<div class="cp-lifecycle-error">FAILED · recovery available · '+html.escape(str(rc.get("failure_class") or "recognized failure"))+'</div>',unsafe_allow_html=True)
            c1,c2=st.columns(2,gap="small")
            if c1.button("RESUME",type="primary",use_container_width=True,key=f"factory_global_resume_{jid}"):
                try: resume_factory_job(FACTORY_DIR,APP_DIR,jid); _rerun_current_fragment()
                except Exception as e: st.error(str(e))
            if c2.button("ABORT",use_container_width=True,key=f"factory_global_abort_{jid}"):
                abort_factory_job(FACTORY_DIR,jid); _rerun_current_fragment()
        else:
            st.session_state.pop("pending_research_stop",None)
            # Surface worker-side startup/preflight failure in the same lifecycle
            # footer.  Once Data Quality moved off the UI thread, failures are owned
            # by the Factory job and must not disappear silently.
            latest_failed=None
            for cand in (latest_auto,latest_manual,latest_disc):
                if cand and str(cand.get("status") or "") == "FAILED":
                    latest_failed=cand; break
            if latest_failed:
                ferr=str(latest_failed.get("error") or "Research start failed").strip()
                st.markdown('<div class="cp-lifecycle-error">'+html.escape(ferr)+'</div>',unsafe_allow_html=True)
            dataset=_known_factory_dataset(); pending=bool(st.session_state.get("pending_research_start"))
            optimizer_job=latest_strategy_optimizer_job()
            optimizer_active=bool(optimizer_job and str(optimizer_job.get("status") or "") in STRATEGY_OPTIMIZER_ACTIVE)
            _mode=get_research_mode(cfg)
            _start_label="START MANUAL RESEARCH" if _mode=="MANUAL" else "START AUTO RESEARCH"
            if optimizer_active:
                st.caption("Strategy Optimizer is active. Research lifecycle is separate and cannot start concurrently.")
            if pending:
                # Legacy acceptance sentinel (wording only): Preflight · Data Quality · freezing research plan…
                # Hotfix8+ launches the owned worker first; the real Data Quality preflight runs there.
                # Startup feedback is deliberately above the fixed bottom button so it
                # remains visible even on short screens and never gets clipped below the viewport.
                _live_status_strip("Research","Launching research worker…",meta="STARTING",spinning=True)
            st.button("STARTING…" if pending else _start_label,type="primary",use_container_width=True,key="global_research_start",disabled=(dataset is None or pending or optimizer_active),on_click=_queue_global_research_start if (dataset is not None and not optimizer_active) else None)
            if pending:
                start_req=dict(st.session_state.get("pending_research_start") or {})
                # First pending frame is paint-only; second frame performs preflight.
                # This makes START visibly grey/disabled immediately on slow disks.
                if str(start_req.get("phase") or "ARMED")=="ARMED":
                    start_req["phase"]="EXECUTE"; st.session_state["pending_research_start"]=start_req; _rerun_current_fragment()
                try:
                    persist_user_settings()
                    if _mode=="MANUAL":
                        job=_start_manual_background(cfg,Path(dataset)); st.session_state["factory_manual_job_id"]=job["job_id"]
                    else:
                        job=_start_auto_background(cfg,Path(dataset)); st.session_state["factory_auto_job_id"]=job["job_id"]
                    st.session_state.pop("research_lifecycle_error",None)
                except Exception as e:
                    st.session_state["research_lifecycle_error"]=str(e)
                finally:
                    st.session_state.pop("pending_research_start",None)
                _rerun_current_fragment()
        err=str(st.session_state.get("research_lifecycle_error") or "").strip()
        if err:
            st.caption("Lifecycle: "+err)

def _render_discovery_stage(cfg: dict):
    _page_header("Discovery", "Research stage")
    dataset=resolve_dataset("factory")
    if dataset is None or not dataset_card(
        dataset,
        show_identity=False,
        show_data_quality=False,
    ):
        return
    fc=cfg.setdefault("champion_factory",{})

    with st.expander("Discovery plan · Research limits & qualification target", expanded=True):
        a,b,c=st.columns([1,1,.8],gap="large")
        fc["max_total_experiments"]=int(a.number_input("Max Discovery experiments",36,600,int(fc.get("max_total_experiments",216)),12,key="factory_max_total"))
        fc["max_generations"]=int(b.number_input("Max learning generations",1,20,int(fc.get("max_generations",8)),1,key="factory_max_gen"))
        c.metric("Qualified target","12 / 12")
        st.markdown('<div class="cp-info-line"><span>Lifecycle authority</span><span>Research · PAUSE at safe boundary · STOP verified process-authoritatively</span></div>',unsafe_allow_html=True)
        _subsection_header("Manual / advanced Discovery control", "Optional direct Discovery-only action; global START RESEARCH remains the normal lifecycle authority.")
        active_any=latest_factory_job(FACTORY_DIR,active_only=True)
        latest_auto=latest_factory_job(FACTORY_DIR,"AUTO",active_only=False)
        latest_disc=latest_factory_job(FACTORY_DIR,"DISCOVERY",active_only=False)
        resumable_auto=latest_auto if latest_auto and factory_job_is_resumable(FACTORY_DIR,latest_auto) else None
        resumable_disc=latest_disc if latest_disc and factory_job_is_resumable(FACTORY_DIR,latest_disc) else None
        blocked=bool(active_any or resumable_auto or resumable_disc)
        if st.button("DISCOVERY ONLY",use_container_width=True,key="factory_start_btn",disabled=blocked):
            try:
                persist_user_settings(); job=_start_discovery_background(cfg,dataset); st.session_state["factory_discovery_job_id"]=job["job_id"]; st.rerun()
            except Exception as e: st.error(str(e))
        st.caption("DISCOVERY ONLY berhenti setelah WFA/OOF Pool. START RESEARCH global menjalankan Pool → CPCV finalists → Tournament → Monte Carlo → Forward sampai terminal/Champion.")

    # Resolve lifecycle state again after the plan card so live rendering always uses current job state.
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    latest_auto=latest_factory_job(FACTORY_DIR,"AUTO",active_only=False)
    latest_disc=latest_factory_job(FACTORY_DIR,"DISCOVERY",active_only=False)
    resumable_auto=latest_auto if latest_auto and factory_job_is_resumable(FACTORY_DIR,latest_auto) else None
    resumable_disc=latest_disc if latest_disc and factory_job_is_resumable(FACTORY_DIR,latest_disc) else None
    if active:
        jid=str(active["job_id"])
        if str(active.get("action")).upper()=="AUTO": st.session_state["factory_auto_job_id"]=jid
        elif str(active.get("action")).upper()=="DISCOVERY": st.session_state["factory_discovery_job_id"]=jid
        _render_factory_job_monitor(jid)
    else:
        resumable=resumable_auto or resumable_disc
        if resumable:
            _render_factory_job_monitor(str(resumable["job_id"]))

    runs=_factory_runs()
    if runs:
        fd=_factory_selector("discovery_lineage")
        try:
            fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8"))
            with st.expander(f"Latest completed Factory · {str(fm.get('status') or 'UNKNOWN')}", expanded=True):
                _fact_grid([
                    ("Pool",f"{fm.get('qualified_candidates',0)}/{fm.get('target_candidates',12)}"),
                    ("Proposals",f"{fm.get('total_experiments',0)}/{fm.get('max_total_experiments',0)}"),
                    ("Factory",fd.name),
                ],wide_labels={"Factory"})
                topo_path=fd/"failure_topology.json"
                summary_path=fd/"all_trial_summary.json"
                if topo_path.exists():
                    topo=json.loads(topo_path.read_text(encoding="utf-8"))
                    _subsection_header("WFA failure topology", "Latest completed evidence")
                    _stat_strip([
                        ("Full WFA evaluated",int(topo.get("candidate_count",0) or 0),"candidates"),
                        ("WFA PASS",int(topo.get("passed_count",0) or 0),"survivors"),
                        ("Dominant fail",_ui_gate_name(topo.get("dominant_first_failed_gate") or "—"),"first failed gate"),
                        ("Failure group",str(topo.get("dominant_failure_group") or "—"),"dominant"),
                    ])
                    counts=topo.get("first_failed_gate_counts") or {}
                    if counts: st.caption("WFA Failure Topology · "+" · ".join(f"{_ui_gate_name(k)}: {v}" for k,v in list(counts.items())[:8]))
                    near=topo.get("near_miss_candidates") or []
                    if near:
                        _subsection_header("Near-miss / Failure Margins", "Closest rejected candidates remain visible when this Factory card is open.")
                        _model_table(near,near,key=f"discovery_near_miss_{fd.name}",factory_dir=fd)
                if summary_path.exists():
                    sm=json.loads(summary_path.read_text(encoding="utf-8")); st.caption(f"All-trial ledger · screen {int(sm.get('screen_records',0) or 0)} · full WFA {int(sm.get('full_wfa_records',0) or 0)} · records {int(sm.get('ledger_records',0) or 0)}")
        except Exception:
            pass
        if not active:
            _render_llm_research_report(None,fd)

def _render_pool_stage(cfg: dict):
    _page_header("Candidate Pool", "Research stage", "Inspector")
    fd=_factory_selector("pool_lineage")
    if not fd: return
    fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8"))
    pool_path=fd/"candidate_pool.json"
    with st.expander(f"Qualified candidate pool · {str(fm.get('status') or 'UNKNOWN')}", expanded=True):
        _render_stage_live_header("POOL",fd)
        _fact_grid([
            ("Qualified",f"{fm.get('qualified_candidates',0)}/{fm.get('target_candidates',12)}"),
            ("Factory",fd.name),
            ("Stage","POOL"),
        ],wide_labels={"Factory"})
        if not pool_path.exists():
            st.info("Pool belum terbentuk.")
            return
        pool=json.loads(pool_path.read_text(encoding="utf-8")); rows=[]
        _cpcv_by_id={}
        try:
            _cev=json.loads((fd/"cpcv_qualification_evidence.json").read_text(encoding="utf-8"))
            _cpcv_by_id={str(r.get("pool_id")):r for r in (_cev.get("rows") or []) if isinstance(r,dict)}
        except Exception:
            pass
        for c in pool:
            _pid=str(c.get("pool_id") or ""); _cr=_cpcv_by_id.get(_pid)
            _cstat=("PASS" if bool(_cr.get("passed")) else "FAIL") if _cr is not None else c.get("cpcv_status","WAITING")
            m=c.get("discovery_metrics") or {}; rows.append({"ID":c.get("pool_id"),"Family":_family_display_name(c.get("family")),"Model":c.get("name"),"Seed":c.get("training_seed"),"Threshold":c.get("take_threshold"),
                "WFA PF":m.get("median_profit_factor"),"WFA Overall R":m.get("overall_expectancy_r"),"WFA Median R":m.get("median_expectancy_r"),"Worst R":m.get("worst_expectancy_r"),"Worst DD":m.get("worst_fold_max_drawdown_r"),"Worst Recovery":m.get("worst_fold_recovery_factor"),"Ranking Score":m.get("selection_score"),
                "CPCV":_cstat,"Trained ID":str(c.get("trained_candidate_id") or "")[:12]})
        _subsection_header("Candidates", "All Pool authority columns remain visible; dense evidence stays in the table.")
        _model_table(rows,pool,key=f"pool_models_{fd.name}",factory_dir=fd,height=min(530,90+32*len(rows)))
        if fm.get("status")=="DISCOVERY_POOL_READY": st.success("Exact WFA/OOF-qualified Pool frozen. Auto workflow proceeds to CPCV.")
    _render_stage_scientist(fd,"POOL")

def _start_factory_stage_job(action: str, cfg: dict, dataset: Path, fd: Path) -> dict:
    persist_user_settings(); runtime=write_runtime_cfg(cfg,f"factory_{action.lower()}_{fd.name}.json")
    payload={"factory_dir":str(fd),"dataset":str(dataset),"config_path":str(runtime)}
    return start_factory_job(FACTORY_DIR,APP_DIR,action,payload)



@st.fragment(run_every="2s")
def _render_cpcv_live_inspector(fd: Path):
    try: fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8"))
    except Exception: fm={}
    pool=[]; live={}; ev={}; topo={}; live_splits={}
    for name,target in (("candidate_pool.json","pool"),("cpcv_live.json","live"),("cpcv_qualification_evidence.json","ev"),("cpcv_failure_topology.json","topo")):
        try:
            val=json.loads((fd/name).read_text(encoding="utf-8"))
            if target=="pool": pool=val if isinstance(val,list) else []
            elif target=="live": live=val if isinstance(val,dict) else {}
            elif target=="ev": ev=val if isinstance(val,dict) else {}
            else: topo=val if isinstance(val,dict) else {}
        except Exception: pass
    try:
        x=json.loads((fd/"cpcv_live_split_results.json").read_text(encoding="utf-8")); live_splits=x if isinstance(x,dict) else {}
    except Exception: pass
    crows=list(ev.get("rows") or []); by_id={str(r.get("pool_id")):r for r in crows if isinstance(r,dict)}; tested=len(crows); passed=sum(bool(r.get("passed")) for r in crows); failed=tested-passed
    target=int(((fm.get("cpcv") or {}).get("target_survivors") or 3)); total_finalists=int(((fm.get("cpcv") or {}).get("max_finalists") or len(pool) or 12))
    with st.expander("Qualification progress · Purged combinatorial stress qualification", expanded=True):
        _stat_strip([
            ("Completed",f"{tested}/{total_finalists}","finalists"),
            ("PASS",passed,"survivors"),
            ("FAIL",failed,"rejected"),
            ("Target",f"{passed}/{target}","required"),
        ])
        if live:
            status=str(live.get("status") or ""); candidate=live.get("candidate") or live.get("pool_id") or "—"
            if status=="RUNNING": st.markdown(f'<div class="cp-activity"><strong>Current activity</strong><span>{html.escape(str(candidate))} · split {live.get("split_no") or live.get("split_completed") or 0}/{live.get("split_total") or 15} · groups {html.escape(str(live.get("test_groups") or "—"))}</span></div>',unsafe_allow_html=True)
    view=[]
    sorted_pool=sorted(pool,key=lambda x:int(x.get("cpcv_rank") or 999))
    for c in sorted_pool:
        pid=str(c.get("pool_id") or ""); r=by_id.get(pid,{}); m=c.get("cpcv_summary") or r.get("summary") or {}; dm=c.get("discovery_metrics") or {}; stat=("PASS" if bool(r.get("passed")) else "FAIL") if r else str(c.get("cpcv_status") or "WAITING"); splits=int((r.get("evidence") or {}).get("combinations",c.get("cpcv_splits_completed",0)) or 0) if r else int(c.get("cpcv_splits_completed",0) or 0); kpi_authority="FINAL · canonical reconstructed CPCV" if r else "WAITING"
        if not r and pid==str(live.get("pool_id") or "") and str(live.get("status") or "")=="RUNNING":
            splits=max(splits,int(live.get("split_completed",0) or 0)); stat="RUNNING"
            _lr=(live_splits.get("rows") or []) if str(live_splits.get("pool_id") or "")==pid else []
            _prov=provisional_cpcv_summary(_lr)
            if int(_prov.get("completed_split_records",0) or 0)>0:
                m=_prov; splits=int(_prov.get("completed_split_records",0) or 0); kpi_authority="PROVISIONAL · completed splits only"
        if not r and pid==str(live.get("pool_id") or ""):
            split_total=int(live.get("split_total",15) or 15)*max(1,int(live.get("seed_total",1) or 1))
        else:
            split_total=(15 if not r else splits)
        view.append({"Rank":c.get("cpcv_rank") or r.get("rank"),"ID":pid,"Family":_family_display_name(c.get("family")),"Model":c.get("name"),"Ranking Score":dm.get("selection_score"),"CPCV":stat,"Splits":(f"{splits}/{split_total}" if stat=="RUNNING" else splits),"KPI authority":kpi_authority,"First fail":r.get("first_failed_gate") if r else c.get("cpcv_first_failed_gate"),"Median PF":m.get("median_profit_factor"),"Median Exp":m.get("median_expectancy_r"),"Worst R":m.get("worst_expectancy_r"),"Worst DD":m.get("worst_max_drawdown_r"),"Worst Recovery":m.get("worst_recovery_factor")})
    with st.expander(f"Results · {len(view)} finalists", expanded=True):
        if view: _model_table(view,sorted_pool,key=f"cpcv_models_{fd.name}",factory_dir=fd,height=min(520,90+32*len(view)))
        else: st.caption("No finalist evidence yet.")

    focus=str(live.get("pool_id") or ""); rr=by_id.get(focus) or (crows[-1] if crows else None); paths=((rr.get("evidence") or {}).get("paths") or []) if rr else []; live_rows=(live_splits.get("rows") or []) if str(live_splits.get("pool_id") or "")==focus else []; detail_rows=paths or live_rows; audit=((rr.get("evidence") or {}).get("methodology_audit") or {}) if rr else {}
    if detail_rows or audit or topo:
        with st.expander("Forensics",expanded=False):
            tabs=st.tabs(["Stress splits","Canonical paths","Group attribution","Failure topology"])
            with tabs[0]:
                if detail_rows:
                    sv=[{"Split":x.get("split",x.get("path")),"Groups":str(x.get("test_groups")),"PF":x.get("profit_factor"),"Exp R":x.get("expectancy_r"),"DD R":x.get("max_drawdown_r"),"Recovery":x.get("recovery_factor"),"Trades":x.get("trades"),"Fit s":x.get("fit_seconds")} for x in detail_rows]
                    st.dataframe(pd.DataFrame(sv),use_container_width=True,hide_index=True)
                else: st.caption("No split evidence yet.")
            with tabs[1]:
                st.markdown("**CPCV Methodology Audit · dual report**")
                canon=((audit.get("canonical_reconstructed_path_view") or {}).get("paths") or [])
                if canon:
                    cv=[{"Path":x.get("canonical_path"),"Source split pairs":str(x.get("source_split_pairs")),"Trades":x.get("trades"),"PF":x.get("profit_factor"),"Exp R":x.get("expectancy_r"),"DD R":x.get("max_drawdown_r"),"Recovery":x.get("recovery_factor"),"Sharpe":x.get("sharpe_ratio"),"Sortino":x.get("sortino_ratio"),"Calmar":x.get("calmar_mar_ratio"),"PSR":x.get("probabilistic_sharpe_ratio"),"DSR":x.get("deflated_sharpe_ratio"),"Ulcer R":x.get("ulcer_index_r"),"Daily CVaR95 R":x.get("daily_cvar95_r")} for x in canon]
                    st.dataframe(pd.DataFrame(cv),use_container_width=True,hide_index=True)
                else: st.caption("No reconstructed paths yet.")
            with tabs[2]:
                groups=audit.get("group_attribution") or []
                if groups: st.dataframe(pd.DataFrame(groups),use_container_width=True,hide_index=True)
                else: st.caption("No group attribution yet.")
            with tabs[3]:
                counts=topo.get("all_failed_gate_counts") or {}
                if counts: st.dataframe(pd.DataFrame([{"Gate":k,"Count":v} for k,v in counts.items()]),use_container_width=True,hide_index=True)
                wc=topo.get("worst_split_combination") or {}
                if wc: st.caption(f"Worst groups {wc.get('test_groups')} · median Exp {wc.get('median_expectancy_r')} · DD {wc.get('median_max_drawdown_r')} · Recovery {wc.get('median_recovery_factor')}")
    _render_cpcv_candidate_scientist(fd); _render_stage_scientist(fd,"CPCV")

def _render_cpcv_stage(cfg: dict):
    _page_header("CPCV Finalist Qualification", "Validation stage", "Inspector")
    fd=_factory_selector("cpcv_lineage")
    if not fd: return
    _render_stage_live_header("CPCV",fd)
    _render_cpcv_live_inspector(fd)

def _render_tournament_stage(cfg: dict):
    _page_header("Tournament", "Validation stage")
    fd=_factory_selector("tournament_lineage")
    if not fd: return
    fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8")); tl=fd/"tournament_leaderboard.json"; rows=json.loads(tl.read_text(encoding="utf-8")) if tl.exists() else []; passed=sum(1 for r in rows if bool((r.get("acceptance") or {}).get("passed"))); failed=max(0,len(rows)-passed)
    with st.expander(f"Tournament summary · {str(fm.get('status') or '—')}", expanded=True):
        _render_stage_live_header("TOURNAMENT",fd)
        _stat_strip([
            ("Entrants",len(rows),"candidates"),
            ("PASS",passed,"survivors"),
            ("FAIL",failed,"rejected"),
            ("Status",str(fm.get("status") or "—"),"factory"),
        ])
    view=[]
    for r in rows:
        m=r.get("metrics") or {}; a0=r.get("acceptance") or {}; view.append({"ID":r.get("pool_id"),"Family":_family_display_name(r.get("family")),"PASS":"YES" if a0.get("passed") else "NO","First fail":a0.get("first_failed_gate"),"Trades":m.get("trades"),"Min":m.get("auto_min_trades"),"PF":m.get("profit_factor"),"Exp R":m.get("expectancy_r"),"DD R":m.get("max_drawdown_r"),"Recovery":m.get("recovery_factor"),"Positive months":m.get("positive_month_ratio"),"Positive quarters":m.get("positive_quarter_ratio")})
    with st.expander(f"Results · {len(view)} candidates", expanded=True):
        if view: _model_table(view,rows,key=f"tournament_models_{fd.name}",factory_dir=fd,height=min(520,90+32*len(view)))
        else: st.caption("No Tournament result yet.")
    tp=fd/"tournament_failure_topology.json"; sp=fd/"tournament_survivors.json"
    if tp.exists() or sp.exists():
        with st.expander("Forensics",expanded=False):
            if tp.exists():
                topo=json.loads(tp.read_text(encoding="utf-8")); counts=topo.get("first_failed_gate_counts") or {}
                if counts: st.dataframe(pd.DataFrame([{"Gate":k,"Count":v} for k,v in counts.items()]),use_container_width=True,hide_index=True)
            if sp.exists(): st.caption(f"Frozen survivors · {len(json.loads(sp.read_text(encoding='utf-8')))} candidate(s)")
    _render_stage_scientist(fd,"TOURNAMENT")

def _render_monte_carlo_stage(cfg: dict):
    _page_header("Monte Carlo", "Stress stage")
    fd=_factory_selector("mc_lineage")
    if not fd: return
    fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8")); ep=fd/"monte_carlo_evidence.json"; ev=json.loads(ep.read_text(encoding="utf-8")) if ep.exists() else {}; rows=list(ev.get("rows") or []); passed=sum(1 for r in rows if bool((r.get("acceptance") or {}).get("passed"))); failed=max(0,len(rows)-passed); sims=int(ev.get("simulation_count",0) or 0)
    with st.expander(f"Stress summary · {str(fm.get('status') or '—')}", expanded=True):
        _render_stage_live_header("MONTE_CARLO",fd)
        _stat_strip([
            ("Candidates",len(rows),"stress-tested"),
            ("PASS",passed,"survivors"),
            ("FAIL",failed,"rejected"),
            ("Simulations",f"{sims:,}" if sims else "—","per evidence"),
        ])
    view=[]
    for r in rows:
        mc=r.get("monte_carlo") or {}; robust=mc.get("robust_metrics") or {}; acc=r.get("acceptance") or {}; view.append({"ID":r.get("pool_id"),"Family":_family_display_name(r.get("family")),"PASS":"YES" if acc.get("passed") else "NO","First fail":acc.get("first_failed_gate"),"PF p05":robust.get("profit_factor"),"Exp p05":robust.get("expectancy_r"),"DD p95":robust.get("max_drawdown_r"),"Recovery p05":robust.get("recovery_factor"),"Trades":robust.get("trades")})
    with st.expander(f"Results · {len(view)} candidates", expanded=True):
        if view: _model_table(view,rows,key=f"monte_carlo_models_{fd.name}",factory_dir=fd)
        else: st.caption("No Monte Carlo result yet.")
    tp=fd/"monte_carlo_failure_topology.json"
    if tp.exists():
        with st.expander("Forensics",expanded=False):
            topo=json.loads(tp.read_text(encoding="utf-8")); counts=topo.get("first_failed_gate_counts") or {}
            if counts: st.dataframe(pd.DataFrame([{"Gate":k,"Count":v} for k,v in counts.items()]),use_container_width=True,hide_index=True)
    _render_stage_scientist(fd,"MONTE_CARLO")

def _render_forward_stage(cfg: dict):
    _page_header("Forward Championship", "Fresh validation")
    fd=_factory_selector("forward_lineage")
    if not fd: return
    fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8")); lp=fd/"forward_leaderboard.json"; rows=json.loads(lp.read_text(encoding="utf-8")) if lp.exists() else []; passed=sum(1 for r in rows if bool((r.get("acceptance") or {}).get("passed"))); failed=max(0,len(rows)-passed)
    with st.expander(f"Fresh-forward summary · {str(fm.get('status') or 'LOCKED')}", expanded=True):
        _render_stage_live_header("FORWARD",fd)
        _stat_strip([
            ("Candidates",len(rows),"fresh-tested"),
            ("PASS",passed,"survivors"),
            ("FAIL",failed,"rejected"),
            ("State",str(fm.get("status") or "LOCKED"),"authority"),
        ])
    view=[]
    for r in rows:
        m=r.get("metrics") or {}; acc=r.get("acceptance") or {}; view.append({"ID":r.get("pool_id"),"Family":_family_display_name(r.get("family")),"PASS":"YES" if acc.get("passed") else "NO","First fail":acc.get("first_failed_gate"),"Trades":m.get("trades"),"Min":m.get("auto_min_trades"),"PF":m.get("profit_factor"),"Exp R":m.get("expectancy_r"),"DD R":m.get("max_drawdown_r"),"Recovery":m.get("recovery_factor")})
    with st.expander(f"Results · {len(view)} candidates", expanded=True):
        if view: _model_table(view,rows,key=f"forward_models_{fd.name}",factory_dir=fd,height=min(520,90+32*len(view)))
        else: st.caption("No Forward result yet.")
    checks=fm.get("forward_checks") or []
    if checks:
        with st.expander("Forensics · locked evidence",expanded=False): st.dataframe(pd.DataFrame(checks),use_container_width=True,hide_index=True)
    _render_stage_scientist(fd,"CHAMPION" if fm.get("status") in {"FACTORY_WINNER","CHAMPION"} else "FORWARD")

def _render_model_champion_summary():
    champion_reg=load_registry(APP_DIR)
    current=champion_reg.get("current")
    _subsection_header("Model Champion", "Current production model authority")
    if current:
        st.success(f"Current Model Champion · {current.get('champion_id')} · {current.get('model_name')} · source {current.get('source_challenger_id') or 'legacy'}")
        k=current.get("locked_test_kpi") or current.get("kpi") or {}
        if k:
            c1,c2,c3,c4,c5=st.columns(5)
            c1.metric("PF",_fmt(k.get("profit_factor")))
            c2.metric("Exp R",_fmt(k.get("expectancy_r"),"r"))
            c3.metric("DD R",_fmt(k.get("max_drawdown_r")))
            c4.metric("Recovery",_fmt(k.get("recovery_factor")))
            c5.metric("Trades",str(k.get("trades") if k.get("trades") is not None else "—"))
        champion_row={
            "Champion":current.get("champion_id"),
            "Model":current.get("model_name"),
            "Family":_family_display_name(current.get("model_family")),
            "Source Challenger":current.get("source_challenger_id"),
        }
        champion_raw=dict(current); champion_raw["run_dir"]=str(current.get("source_run") or "")
        _model_table([champion_row],[champion_raw],key="model_champion_current",run_dirs=[Path(str(current.get("source_run"))) if current.get("source_run") else None])
    else:
        st.info("Current Model Champion: NONE · Research Challengers remain non-production until explicit promotion.")

def _render_model_challenger_registry(cfg: dict):
    reg=load_challenger_registry(APP_DIR)
    entries=list(reg.get("entries") or [])
    _subsection_header("Model Challengers", "Research output → Shadow → explicit Owner promotion")
    if not entries:
        st.caption("No registered Model Challenger yet. Research will register each ELIGIBLE_CHALLENGER here with a human-readable filename.")
        return

    rows=[]; by_id={}
    for e in reversed(entries):
        cid=str(e.get("challenger_id") or "?"); by_id[cid]=e
        locked=e.get("locked_test_kpi") or {}; sh={}; stage="—"
        run=Path(str(e.get("run_dir") or ""))
        try:
            ev=load_evidence(run); sh=ev.get("shadow_forward") or {}
        except Exception: pass
        try:
            sp=run/"supervisor_state.json"
            if sp.exists(): stage=str(json.loads(sp.read_text(encoding="utf-8")).get("stage") or "—")
        except Exception: pass
        rows.append({
            "Challenger":cid,
            "Family":e.get("family_label") or _family_display_name(e.get("model_family")),
            "Model":e.get("model_name"),
            "State":e.get("status") or "CHALLENGER",
            "Trades":locked.get("trades"),
            "PF":locked.get("profit_factor"),
            "Exp R":locked.get("expectancy_r"),
            "DD R":locked.get("max_drawdown_r"),
            "Recovery":locked.get("recovery_factor"),
            "Shadow trades":sh.get("trades"),
            "Shadow PF":sh.get("profit_factor"),
            "Shadow Exp R":sh.get("expectancy_r"),
            "Supervisor":stage,
        })
    with st.expander(f"Model Challengers · {len(rows)}",expanded=True):
        _model_table(rows,raw_entries,key="model_challenger_models",run_dirs=[Path(str(x.get("run_dir") or "")) if str(x.get("run_dir") or "") else None for x in raw_entries],height=min(520,100+33*len(rows)))
        choices=[r["Challenger"] for r in rows]
        selected=st.selectbox("Selected Challenger",choices,key="champion_registry_selected")
        e=by_id[selected]; run=Path(str(e.get("run_dir") or ""))
        if not run.exists():
            st.error(f"Challenger run folder is unavailable: {run}")
            return
        m=load_manifest(run)
        art=m.get("challenger_artifact") or {}
        params=art.get("manual_ea_parameters") or e.get("manual_ea_parameters") or {}
        st.caption("Shadow selection remains Owner-controlled in Max EA. Use the exact human-readable file below; this UI never rewrites the EA Challenger parameter automatically.")
        if params:
            st.code("\n".join(f"{k}: {v}" for k,v in params.items() if v),language=None)

        terminals=detect_terminal_files_dirs(); target=None
        c1,c2=st.columns([1.25,1.75])
        with c1:
            if terminals:
                target=Path(st.selectbox("MT5 Files target",[str(x) for x in terminals],key=f"registry_target_{selected}"))
            else:
                raw=st.text_input("MT5 Files target",key=f"registry_manual_target_{selected}")
                target=Path(raw) if raw.strip() else None
            if st.button("PUBLISH FOR SHADOW",disabled=target is None,use_container_width=True,key=f"registry_publish_{selected}"):
                try:
                    res=publish_challenger_to_terminal(run,target,m)
                    st.success(f"Published {res.get('challenger_id')} · EA unchanged")
                except Exception as exc:
                    st.error(str(exc))
        with c2:
            try:
                state=assess_promotion(run,cfg,APP_DIR)
                st.caption(f"Promotion authority · {state.get('stage')} · {'READY' if state.get('promotion_ready') else 'NOT READY'}")
                pending=[g.get("name") for g in (state.get("gates") or []) if not g.get("passed")]
                if pending: st.caption("Pending: "+", ".join(str(x) for x in pending))
            except Exception as exc:
                state={"promotion_ready":False}; st.warning(f"Promotion assessment unavailable: {exc}")
            allow=st.checkbox("Confirm explicit promotion to production Champion",value=False,key=f"registry_allow_{selected}")
            if st.button("PROMOTE SELECTED CHALLENGER",type="primary",disabled=(not state.get("promotion_ready") or target is None or not allow),use_container_width=True,key=f"registry_promote_{selected}"):
                try:
                    res=promote(run,target,cfg,APP_DIR)
                    st.success(f"CHAMPION {res.get('champion_id')} ← {res.get('challenger_id')}")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))


def _render_model_challengers_stage(cfg: dict):
    _page_header("Model Challengers", "Review · Shadow · Promote", "ONNX/model registry only")
    st.caption("Model Challengers are non-production Research outputs. Strategy Optimizer/EA Challengers are managed on the separate Strategy Challengers page.")
    _render_model_challenger_registry(cfg)

def _render_model_champion_stage(cfg: dict):
    _page_header("Model Champion", "Current production model authority", "ONNX/model only")
    _render_model_champion_summary()
    st.divider()
    st.caption("Factory winner evidence · Factory lifecycle status is FACTORY_WINNER; production authority starts only after explicit Model promotion.")
    fd=_factory_selector("model_champion_lineage")
    if not fd: return
    fm=json.loads((fd/"factory_manifest.json").read_text(encoding="utf-8")); status=fm.get("status"); cp=fd/"champion.json"
    with st.expander(f"Factory winner · {str(status or 'UNKNOWN')}", expanded=True):
        if status in {"FACTORY_WINNER","CHAMPION"} and cp.exists():
            w=json.loads(cp.read_text(encoding="utf-8")); st.success(f"ELIGIBLE CHALLENGER · {w.get('pool_id')} · {_family_display_name(w.get('family'))} · {w.get('name')}")
            m=w.get("metrics") or {}
            _stat_strip([
                ("PF",_fmt(m.get("profit_factor")),"profit factor"),
                ("Exp R",_fmt(m.get("expectancy_r"),"r"),"expectancy"),
                ("DD R",_fmt(m.get("max_drawdown_r")),"drawdown"),
                ("Recovery",_fmt(m.get("recovery_factor")),"factor"),
            ])
            winner_row={"ID":w.get("pool_id"),"Model":w.get("name"),"Family":_family_display_name(w.get("family")),"State":"ELIGIBLE_CHALLENGER"}
            _model_table([winner_row],[w],key=f"factory_winner_model_{fd.name}",factory_dir=fd)
            st.caption("Research authority: Discovery WFA/OOF → Pool → CPCV → Tournament → Monte Carlo → Fresh Forward → eligible Model Challenger. This is not production Champion authority until explicit promotion.")
        elif status=="NO_CHAMPION_FORWARD_FAIL": st.error("NO CHALLENGER · seluruh Monte Carlo survivors gagal Forward KPI.")
        elif status in {"FACTORY_WINNER_RUNTIME_BLOCKED","CHAMPION_RUNTIME_BLOCKED"}: st.error("Factory winner terpilih tetapi ONNX generator/parity runtime BLOCKED. Repair runtime; jangan ulang research.")
        elif status=="FORWARD_INSUFFICIENT_SAMPLE": st.warning("Belum eligible Challenger · minimal satu Forward survivor belum memenuhi AUTO sample.")
        elif status=="MONTE_CARLO_NO_SURVIVOR": st.error("NO CHALLENGER · tidak ada Tournament survivor yang PASS Monte Carlo.")
        elif status=="CPCV_NO_SURVIVOR": st.error("NO CHALLENGER · tidak ada WFA finalist yang PASS CPCV.")
        elif status=="TOURNAMENT_NO_SURVIVOR": st.error("NO CHALLENGER · tidak ada kandidat yang PASS Tournament KPI.")
        else: st.info(f"Factory winner belum tersedia · `{status}`")

def _render_strategy_challengers_stage(cfg: dict):
    _page_header("Strategy Challengers", "Review · Promote · Delete", "EA strategy registry only")
    st.caption("Eligible Strategy Optimizer winners remain non-production until explicit Owner promotion. Model/ONNX Challengers are managed separately.")
    _render_strategy_challenger_registry(cfg)

def _render_strategy_champion_stage(cfg: dict):
    _page_header("Strategy Champion", "Current production strategy authority", "Max_MTF.mq5 · Max_MTF.set")
    _render_strategy_champion_summary()


@st.cache_data(ttl=60,show_spinner=False)
def _ui_hardware_profile_cached():
    return collect_hardware_profile()

@st.cache_data(ttl=60,show_spinner=False)
def _ui_model_size_advisor_cached(identity_json: str, cfg_json: str, profile_json: str) -> dict:
    identity=json.loads(identity_json); cfg=json.loads(cfg_json); profile=json.loads(profile_json)
    return build_model_size_advisor(identity,cfg,profile)

@st.cache_data(ttl=60,show_spinner=False)
def _ui_discovery_identity_cached(dataset_path: str, discovery_from: str, discovery_to: str) -> dict:
    identity=quick_summary(dataset_path)
    if not discovery_from or not discovery_to:
        identity["advisor_row_scope"]="FULL_DATASET_FALLBACK"
        return identity
    t=read_csv_auto(dataset_path,usecols=["signal_time"])["signal_time"]
    ts=pd.to_datetime(t,errors="coerce")
    lo=pd.Timestamp(discovery_from); hi=pd.Timestamp(discovery_to)+pd.Timedelta(days=1)-pd.Timedelta(microseconds=1)
    rows=int(((ts>=lo)&(ts<=hi)).sum())
    identity["rows"]=rows
    identity["start"]=str(lo.date())
    identity["end"]=str(pd.Timestamp(discovery_to).date())
    identity["advisor_row_scope"]="DISCOVERY_WINDOW"
    return identity

def _current_model_size_advisor(cfg: dict) -> dict | None:
    """Advisory preview only; never mutates/freeze Owner settings."""
    dataset=_known_factory_dataset()
    if dataset is None or not Path(dataset).exists():
        return None
    try:
        fc=cfg.get("champion_factory") or {}
        identity=_ui_discovery_identity_cached(str(dataset),str(fc.get("discovery_from") or ""),str(fc.get("discovery_to") or ""))
        profile=_ui_hardware_profile_cached()
        ra=cfg.get("research_architecture") or {}
        # Keep only inputs that own model-size advice. Current slider values are excluded
        # so moving a slider never changes the suggestion itself.
        slim_cfg={
            "split":copy.deepcopy(cfg.get("split") or {}),
            "compute":copy.deepcopy(cfg.get("compute") or {}),
            "resolved_compute":copy.deepcopy(cfg.get("resolved_compute") or {}),
            "research_architecture":{
                "sequence_capacity_hint":int(ra.get("sequence_capacity_hint",128) or 128),
                "family_size_priorities":{},
            },
        }
        return _ui_model_size_advisor_cached(
            json.dumps(identity,sort_keys=True,default=str),
            json.dumps(slim_cfg,sort_keys=True,default=str),
            json.dumps(profile,sort_keys=True,default=str),
        )
    except Exception as exc:
        return {"schema":"MAX_MODEL_SIZE_ADVISOR_V1","status":"UNAVAILABLE","error":str(exc),"families":{},"safe_envelopes":{},"capacity":{}}

def _format_parameter_count(value) -> str:
    try: n=int(value)
    except Exception: return "—"
    if n>=1_000_000: return f"{n/1_000_000:.2f}M"
    if n>=1_000: return f"{n/1_000:.0f}K"
    return str(n)

def _format_bound_value(value) -> str:
    if isinstance(value,int): return f"{value:,}"
    try:
        x=float(value)
        if abs(x)>=1000: return f"{x:,.0f}"
        if abs(x)>=1: return f"{x:.4g}"
        return f"{x:.6g}"
    except Exception:
        return str(value)

def _latest_research_plan_file() -> tuple[Path | None, dict]:
    for fd in _factory_runs():
        rp=fd/"research_plan.json"
        if rp.exists():
            try:
                obj=json.loads(rp.read_text(encoding="utf-8"))
                if isinstance(obj,dict): return fd,obj
            except Exception: pass
    return None,{}

def _family_display_name(family: str) -> str:
    """Human-readable UI label; canonical backend family IDs are never mutated."""
    names={
        "lightgbm":"LightGBM","xgboost":"XGBoost","random_forest":"Random Forest",
        "gru":"GRU","lstm":"LSTM","tcn":"TCN","transformer":"Transformer Encoder","patchtst":"PatchTST",
        "itransformer":"iTransformer","tft":"TFT","transformer_moe":"Transformer MoE",
    }
    raw=str(family or "").strip().lower()
    if raw.startswith("hybrid::"):
        parts=[p for p in raw.split("::")[1:] if p]
        if parts:
            return " → ".join(names.get(p, p.replace("_"," ").title()) for p in parts)
    return names.get(raw, raw.replace("::"," → ").replace("_"," ").title())


def _render_adaptive_model_research(cfg: dict):
    try:
        profile=_ui_hardware_profile_cached(); summary=summarize_hardware_profile(profile); caps=capability_catalog(profile,cfg)
    except Exception as exc:
        st.error(f"Hardware profiler unavailable: {exc}"); return

    ra=cfg.setdefault("research_architecture",{})
    reg=registry_for_scientist(); base=dict(reg.get("base_families") or {})
    mode=str(ra.get("family_selection_mode") or "AUTO").upper()
    if mode not in {"AUTO","MANUAL","SCIENTIST_DIRECTED"}: mode="AUTO"

    # Hardware snapshot first: family selection is always interpreted against this
    # deterministic profile by the Factory compiler.
    c=st.columns(4,gap="small")
    _physical=summary.get("physical_cores"); _logical=summary.get("logical_threads"); _planning=summary.get("planning_cores")
    _cpu_help=(f"Physical {_physical} · logical {_logical}" if _physical is not None else f"Physical unknown · planning {_planning or '—'} · logical {_logical or '—'}") + f" · source {summary.get('core_count_source') or 'unknown'}"
    c[0].metric("CPU",str(summary.get("cpu") or "Unknown")[:30],help=_cpu_help)
    _rt=summary.get("ram_total_gib"); _ra=summary.get("ram_available_gib")
    c[1].metric("RAM",f"{float(_rt):.1f} GiB" if _rt is not None else "Unknown",help=(f"Available {float(_ra):.1f} GiB" if _ra is not None else "Available unknown") + f" · source {summary.get('ram_source') or 'unknown'}")
    c[2].metric("GPU",str(summary.get("gpu") or "CPU only")[:28],help=f"VRAM {summary.get('vram_total_gib') or '—'} GiB · free {summary.get('vram_free_gib') or '—'} GiB")
    c[3].metric("CUDA","READY" if summary.get("cuda_available") else "NO",help="PyTorch CUDA runtime availability")

    sel_col, plan_col=st.columns([1.15,2.85],gap="medium")
    with sel_col:
        _family_modes=["AUTO","SCIENTIST_DIRECTED","MANUAL"]
        picked=st.radio("Family selection",_family_modes,index=_family_modes.index(mode) if mode in _family_modes else 0,horizontal=True,key="adaptive_family_selection_mode",format_func=lambda x:{"AUTO":"Auto","SCIENTIST_DIRECTED":"Scientist directed","MANUAL":"Strict manual"}[x])
        ra["family_selection_mode"]=picked
    with plan_col:
        fd,plan=_latest_research_plan_file(); active=set(plan.get("active_families") or [])
        if plan:
            st.caption(f"Compiled plan · {fd.name if fd else '—'} · {plan.get('selection_source','?')} · {len(active)} active")
            cap=plan.get("capacity_guidance") or {}; dcap=plan.get("dataset_capacity_profile") or {}; ds=(dcap.get("dataset") or {})
            pref=cap.get("preferred_total_params") or []; ref=cap.get("reference_train_rows")
            if pref:
                st.caption(f"Capacity · {int(ds.get('snapshot_rows') or 0):,} rows · ref train {int(ref or 0):,} · preferred {int(pref[0])/1000:.0f}k–{int(pref[1])/1000:.0f}k params")
        else:
            st.caption("No compiled Factory plan yet · next Factory compiles from hardware + allowed families + Scientist.")

    # AUTO = every registered family is available to the Scientist, subject to
    # deterministic hardware feasibility. MANUAL = Owner-selected allowed universe.
    saved_allowed={str(x).lower() for x in (ra.get("allowed_families") or []) if str(x).lower() in base}
    if not saved_allowed:
        saved_allowed=set(base)
    selected=set()
    categories=[]
    for cat in ("ML","DL","SPECIALIST"):
        fams=[f for f,spec in base.items() if str(spec.get("category") or "").upper()==cat]
        if fams: categories.append((cat,fams))
    leftovers=[f for f in base if not any(f in fs for _,fs in categories)]
    if leftovers: categories.append(("OTHER",leftovers))

    for cat,fams in categories:
        st.markdown(f"**{cat}**")
        cols=st.columns(min(4,max(1,len(fams))),gap="small")
        for i,fam in enumerate(fams):
            spec=base[fam]; cap=(caps.get("families") or {}).get(fam) or {}
            feasible=bool(cap.get("feasible")); backend=str(cap.get("preferred_backend") or "CPU")
            default=(fam in saved_allowed) if picked in {"MANUAL","SCIENTIST_DIRECTED"} else feasible
            checked=cols[i % len(cols)].checkbox(
                _family_display_name(fam), value=bool(default), disabled=(picked=="AUTO"),
                key=f"adaptive_family_{fam}", help=f"{spec.get('role')} · {backend} · {'feasible now' if feasible else 'not feasible on current runtime'}"
            )
            if picked in {"MANUAL","SCIENTIST_DIRECTED"} and checked:
                selected.add(fam)
            elif picked=="AUTO":
                selected.add(fam)
    if picked in {"MANUAL","SCIENTIST_DIRECTED"}:
        ra["allowed_families"]=sorted(selected)
        if not selected:
            st.error("Select at least one model family before starting a new Factory.")
        unavailable=[f for f in selected if not bool(((caps.get("families") or {}).get(f) or {}).get("feasible"))]
        if unavailable:
            st.warning("Selected but not executable on the current runtime: "+", ".join(_family_display_name(f) for f in unavailable))
        if picked=="SCIENTIST_DIRECTED":
            st.caption("Scientist may switch/refine among every allowed feasible family as evidence changes; deterministic gates remain final authority.")
    else:
        # Preserve the Owner's last manual checklist for a later switch back to MANUAL.
        ra.setdefault("allowed_families",sorted(base))

    if active:
        st.caption("Active compiled portfolio · "+" · ".join(_family_display_name(f) for f in sorted(active)))
    st.caption("Hybrid topology is not a model-family checkbox. Compatible hybrids may be composed only from allowed base families; deterministic compatibility, leakage and compute budgets remain final authority.")
    _topo_mode=str(ra.get("topology_selection_mode") or "OWNER_FIXED").upper()
    if _topo_mode not in {"OWNER_FIXED","SCIENTIST_DIRECTED"}: _topo_mode="OWNER_FIXED"
    _topo_modes=["OWNER_FIXED","SCIENTIST_DIRECTED"]
    _picked_topo=st.radio("Topology direction",_topo_modes,index=_topo_modes.index(_topo_mode),horizontal=True,key="adaptive_topology_selection_mode",format_func=lambda x:{"OWNER_FIXED":"Owner fixed","SCIENTIST_DIRECTED":"Scientist directed"}[x])
    ra["topology_selection_mode"]=_picked_topo
    if _picked_topo=="SCIENTIST_DIRECTED":
        st.caption("Scientist may move Single ↔ Hybrid allocation during structural escape. Owner allow-list, deterministic compatibility and compute ceilings still constrain the universe.")

    # Owner model-size preferences. These are not raw hyperparameters. They narrow only
    # candidate generation *inside* the current dynamic legal/resource/scientific capacity authority.
    st.markdown("**Model size priority**")
    st.caption("0.00 = Small preference · 0.50 = balanced · 1.00 = Large preference. The slider biases search inside current dynamic LEGAL/RESOURCE/SCIENTIFIC capacity; it never creates a hard size ceiling or auto-applies a model.")
    _fsp=ra.setdefault("family_size_priorities",{})
    _ordered=[f for f in ("lightgbm","xgboost","random_forest","gru","lstm","tcn","transformer","patchtst","itransformer","tft","transformer_moe") if f in base]
    _size_advisor=_current_model_size_advisor(cfg)
    _size_advisor_families=((_size_advisor or {}).get("families") or {})
    _size_advisor_safe=((_size_advisor or {}).get("safe_envelopes") or {})
    _size_advisor_capacity=((_size_advisor or {}).get("capacity") or {})
    _size_grid=st.columns(2,gap="medium")
    for _idx,fam in enumerate(_ordered):
        with _size_grid[_idx % 2]:
            row=st.columns([1.55,.46,3.35,.46,.48,.42],gap="small")
            _adv=dict(_size_advisor_families.get(fam) or {})
            _suggestion=dict(_adv.get("suggestion") or {})
            _suggested=_suggestion.get("suggested_priority")
            row[0].markdown(f"**{_family_display_name(fam)}**")
            row[0].caption(f"Suggested {float(_suggested):.2f}" if _suggested is not None else "Suggested —")
            row[1].caption("Small")
            _cur=clamp_size_priority(_fsp.get(fam,0.50))
            _fsp[fam]=float(row[2].slider(
                f"{_family_display_name(fam)} size",0.0,1.0,_cur,0.05,
                key=f"adaptive_size_priority_{fam}",format="%.2f",label_visibility="collapsed",
                help="Owner model-size search preference inside current dynamic capacity. Small/Balanced/Large bias where candidates are sampled; hard LEGAL/RESOURCE/SCIENTIFIC admission remains deterministic and unchanged."))
            row[3].caption("Large")
            row[4].caption(f"{_fsp[fam]:.2f}")
            try:
                _resolved=current_family_resolution(fam,_fsp[fam],_size_advisor_safe)
            except Exception:
                _resolved={"current_bounds":{},"size_parameters":[],"estimated_parameter_count_range":None}
            with row[5].popover("?",help="Show the actual size-controlled parameter range for the current slider. Click for details; suggestion is never auto-applied."):
                st.markdown(f"**{_family_display_name(fam)} · current size {_fsp[fam]:.2f}**")
                if _suggested is not None:
                    st.caption(f"Suggested size {_suggested:.2f} · advisory only · current slider remains {_fsp[fam]:.2f}.")
                else:
                    st.caption("Suggested size unavailable until a valid Factory dataset/WFA basis is available.")
                _size_keys=list(_resolved.get("size_parameters") or [])
                _bounds=dict(_resolved.get("current_bounds") or {})
                if _size_keys:
                    _rows=[]
                    for _key in _size_keys:
                        _rng=_bounds.get(_key) or []
                        if len(_rng)>=2:
                            _rows.append({"Parameter":_key,"Current slider range":f"{_format_bound_value(_rng[0])} – {_format_bound_value(_rng[1])}"})
                    if _rows:
                        st.dataframe(pd.DataFrame(_rows),use_container_width=True,hide_index=True)
                else:
                    st.caption("No declared size-controlled parameters for this family.")
                _pc=_resolved.get("estimated_parameter_count_range")
                if isinstance(_pc,(list,tuple)) and len(_pc)>=2 and _pc[0] is not None:
                    st.markdown(f"**Estimated trainable parameters:** {_format_parameter_count(_pc[0])} – {_format_parameter_count(_pc[1])}")
                    st.caption("Estimate uses the executable temporal model constructor across the current size envelope; non-size parameters use deterministic midpoint values.")
                else:
                    st.caption("Trainable parameter count: N/A for tree models; tree node/leaf count is data-dependent. The ranges above are the executable structural search dimensions.")
                if _size_advisor_capacity:
                    st.caption(
                        f"Basis · dataset {int(_size_advisor_capacity.get('dataset_rows') or 0):,} rows · "
                        f"minimum legal WFA train fold {int(_size_advisor_capacity.get('minimum_wfa_train_rows') or 0):,} · "
                        f"configured min train {int(_size_advisor_capacity.get('configured_min_train_rows') or 0):,}. "
                        "Factory generation may move within executable registry bounds, but each actual candidate must still pass dynamic LEGAL/RESOURCE/SCIENTIFIC capacity admission."
                    )
    ra["family_size_priority_schema"]="CP_FAMILY_SIZE_PRIORITY_V1"

    # Owner authority: candidate research allocation, NOT prediction blending.
    st.markdown("**Topology priority**")
    tp=st.columns([0.75,5.5,0.75],gap="small")
    tp[0].caption("Single")
    _hp=float(ra.get("hybrid_priority",0.50))
    _hp=max(0.0,min(1.0,_hp))
    ra["hybrid_priority"]=float(tp[1].slider(
        "Single ↔ Hybrid",0.0,1.0,_hp,0.05,key="adaptive_hybrid_priority",
        format="%.2f",label_visibility="collapsed",
        help="Candidate allocation: 0.00 = 100% standalone, 0.50 = 50/50, 1.00 = 100% hybrid. This does not blend model predictions."
    ))
    tp[2].caption("Hybrid")
    _single_pct=100.0*(1.0-float(ra["hybrid_priority"])); _hybrid_pct=100.0*float(ra["hybrid_priority"])
    st.caption(f"Single {_single_pct:.0f}% · Hybrid {_hybrid_pct:.0f}% · allocation by candidate count; compute-time share is reported separately.")
    _allowed_topology=(selected if picked=="MANUAL" else {f for f,row in (caps.get("families") or {}).items() if bool((row or {}).get("eligible"))})
    _has_temporal=any(str((base.get(f) or {}).get("role"))=="temporal" for f in _allowed_topology)
    _has_policy=any(str((base.get(f) or {}).get("role"))=="policy" for f in _allowed_topology)
    if float(ra["hybrid_priority"])>0.0 and not (_has_temporal and _has_policy):
        st.warning("Hybrid allocation is currently constrained: the allowed/executable universe needs at least one temporal family and one ML policy family.")

    b=st.columns(4,gap="small")
    ra["safe_ram_fraction"]=float(b[0].slider("Safe RAM",0.40,0.95,float(ra.get("safe_ram_fraction",0.75)),0.05,key="adaptive_ram_budget"))
    ra["safe_vram_fraction"]=float(b[1].slider("Safe VRAM",0.40,0.95,float(ra.get("safe_vram_fraction",0.80)),0.05,key="adaptive_vram_budget"))
    ra["max_single_experiment_minutes"]=int(b[2].number_input("Max min / experiment",5,1440,int(ra.get("max_single_experiment_minutes",120)),5,key="adaptive_exp_minutes"))
    ra["require_baseline"]=b[3].toggle("Prefer cheap baseline",value=bool(ra.get("require_baseline",True)),key="adaptive_baseline",help="AUTO/Manual never enables a family you did not allow. In MANUAL, this preference is satisfied only when LightGBM/XGBoost is in the allowed universe.")


def _render_compute_backend_control(cfg: dict):
    cc=cfg.setdefault("compute",{})
    try:
        profile=_ui_hardware_profile_cached(); hs=summarize_hardware_profile(profile)
    except Exception:
        hs={}
    a,b,c,d=st.columns(4,gap="small")
    a.metric("CPU",str(hs.get("cpu") or "Unknown")[:28])
    b.metric("GPU",str(hs.get("gpu") or "None")[:26])
    c.metric("VRAM",f"{hs.get('vram_total_gib') or '—'} GiB")
    d.metric("Torch CUDA","READY" if hs.get("cuda_available") else "NO")

    modes=["AUTO","CPU","CUDA","ROCM"]
    cur=str(cc.get("mode","AUTO")).upper()
    if cur not in modes: cur="AUTO"
    m1,m2=st.columns([2,1],gap="small")
    cc["mode"]=m1.selectbox("Compute policy",modes,index=modes.index(cur),key="compute_mode",help="AUTO resolves the best verified backend independently for every family.")
    cc["fallback_cpu"]=m2.toggle("Fallback CPU",value=bool(cc.get("fallback_cpu",True)),key="compute_fallback_cpu")
    t=st.columns(4,gap="small")
    cc["allow_cuda"]=t[0].toggle("CUDA",value=bool(cc.get("allow_cuda",True)),key="compute_allow_cuda")
    cc["allow_rocm"]=t[1].toggle("ROCm/HIP",value=bool(cc.get("allow_rocm",True)),key="compute_allow_rocm")
    cc["allow_opencl"]=t[2].toggle("OpenCL",value=bool(cc.get("allow_opencl",True)),key="compute_allow_opencl")
    cc["allow_vulkan"]=t[3].toggle("Vulkan scan",value=bool(cc.get("allow_vulkan",True)),key="compute_allow_vulkan",help="Detection only; CPMF does not claim a verified Vulkan training backend.")
    refresh=st.button("Rescan compute",key="compute_rescan",use_container_width=False)
    try:
        plan=resolve_compute_plan(cfg,refresh=bool(refresh))
        rows=compact_compute_status(plan,cfg)
        st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        notes=list(plan.get("notes") or [])
        if notes: st.caption(" · ".join(notes))
    except Exception as e:
        st.error(str(e))

# Lifecycle acceptance authority: Tidak ada duplicate START authority di halaman ini. Workflow/lifecycle dikendalikan dari Research; stage pages remain inspectors.
def _scientist_chat_factory() -> Path | None:
    active=latest_factory_job(FACTORY_DIR,active_only=True)
    if isinstance(active,dict):
        ev=active.get("last_event") if isinstance(active.get("last_event"),dict) else {}
        fid=str(active.get("factory_id") or ev.get("factory_id") or "").strip()
        if fid and (FACTORY_DIR/fid/"factory_manifest.json").exists(): return FACTORY_DIR/fid
    try:
        fd=_selected_factory_for_agent()
        if fd and (Path(fd)/"factory_manifest.json").exists(): return Path(fd)
    except Exception: pass
    runs=_factory_runs()
    return runs[0] if runs else None


def _rerun_current_fragment():
    try:
        st.rerun(scope="fragment")
    except TypeError:
        st.rerun()


def _chat_error_text(exc: Exception, model: str) -> str:
    raw=str(exc or "").strip(); lo=raw.lower()
    if "429" in lo or "quota" in lo or "rate limit" in lo or "exhaust" in lo: return f"{model}: quota/rate-limit."
    if "500" in lo or "internal" in lo or "server error" in lo: return f"{model}: provider internal error."
    if "401" in lo or "403" in lo or "auth" in lo or "api key" in lo: return f"{model}: auth/config error."
    return f"{model}: {raw or 'request failed'}"


def _chat_model_label(value: str) -> str:
    raw=str(value or "").split("/")[-1].strip()
    return raw.replace("-"," ").replace("_"," ").title() if raw else "Model"


def _chat_worker_cfg(value):
    """JSON-safe LLM routing config for background Chat worker; never serialize secrets."""
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    if isinstance(value,list): return [_chat_worker_cfg(v) for v in value]
    if isinstance(value,tuple): return [_chat_worker_cfg(v) for v in value]
    if isinstance(value,dict):
        out={}
        for k,v in value.items():
            lk=str(k).lower()
            # Environment-variable *names* are routing metadata, not credentials.
            # Preserve e.g. api_key_env while stripping actual secret-bearing values.
            if not lk.endswith("_env") and any(tok in lk for tok in ("api_key","apikey","secret","password","credential","token")):
                continue
            out[str(k)]=_chat_worker_cfg(v)
        return out
    return str(value)


def _settle_scientist_chat_job(factory_id: str, thread_id: str):
    """Fold a terminal Chat job into the current persistent thread exactly once.

    A Clear Chat rotates the persistent thread id. Any job from an older thread
    is cancelled/discarded and can never resurrect history after the reset.
    """
    jid=str(st.session_state.get("pending_scientist_chat_job") or "")
    if not jid: return None
    job=load_scientist_chat_job(APP_DIR,jid)
    if not job:
        st.session_state.pop("pending_scientist_chat_job",None)
        st.session_state.scientist_chat_last_error="Chat worker state missing."
        return None
    status=str(job.get("status") or "")
    job_thread=str(job.get("thread_id") or "").strip()
    current_thread=str(thread_id or "").strip()
    if not job_thread or not current_thread or job_thread != current_thread:
        # Hard thread isolation: a late response from before Clear Chat is stale.
        if status in {"QUEUED","RUNNING"}:
            cancel_scientist_chat_job(APP_DIR,jid)
        cleanup_scientist_chat_job_files(APP_DIR,jid)
        st.session_state.pop("pending_scientist_chat_job",None)
        st.session_state.scientist_chat_last_error=""
        st.session_state.scientist_chat_notice="Stale generation discarded after chat reset."
        return None
    if status in {"QUEUED","RUNNING"}: return job

    history=SCIENTIST_CHAT_STORE.load(factory_id)
    already=any(str(m.get("chat_job_id") or "")==jid for m in history if isinstance(m,dict))
    if status=="COMPLETED":
        ans=job.get("result") if isinstance(job.get("result"),dict) else {}
        if not already:
            history.append({
                "role":"assistant","content":str(ans.get("content") or ""),
                "created_utc":ans.get("created_utc") or datetime.utcnow().isoformat()+"Z",
                "requested_model":ans.get("requested_model"),"answered_by":ans.get("answered_by"),
                "provider":ans.get("provider"),"answering_route":ans.get("answering_route") or {},
                "fallback_used":bool(ans.get("fallback_used")),"context_sources":ans.get("context_sources") or [],
                "usage":ans.get("usage") or {},"cost":ans.get("cost") or {},"attempts":ans.get("attempts") or [],"process":ans.get("process") or {},"chat_profile":ans.get("chat_profile") or {},"requested_chat_profile":ans.get("requested_chat_profile") or {},"request_id":str(job.get("request_id") or ""),"chat_job_id":jid,"visibility":"conversation",
            })
            SCIENTIST_CHAT_STORE.save(factory_id,history,thread_id=current_thread)
        st.session_state.scientist_chat_last_error=""
        st.session_state.scientist_chat_notice=""
    elif status=="CANCELLED":
        st.session_state.scientist_chat_last_error=""
        st.session_state.scientist_chat_notice="Generation stopped."
    else:
        model=str(job.get("requested_model") or "Scientist")
        st.session_state.scientist_chat_last_error=_chat_error_text(RuntimeError(str(job.get("error") or "request failed")),model)
        st.session_state.scientist_chat_notice=""
        if not already:
            history.append({
                "role":"assistant","content":str(job.get("error") or "request failed"),
                "created_utc":datetime.utcnow().isoformat()+"Z","answered_by":model,"error":True,"visibility":"internal","request_id":str(job.get("request_id") or ""),"chat_job_id":jid,
                "attempts":job.get("attempts") or [],
            })
            SCIENTIST_CHAT_STORE.save(factory_id,history,thread_id=current_thread)
    cleanup_scientist_chat_job_files(APP_DIR,jid)
    st.session_state.pop("pending_scientist_chat_job",None)
    return None


def _render_scientist_chat(cfg: dict):
    """Isolated Scientist Chat with background generation and explicit cancel authority."""
    fd=_scientist_chat_factory(); factory_id=fd.name if fd else "NO_FACTORY"

    # Clear is handled through the component's existing clear callback BEFORE the
    # next fragment body renders. This guarantees that the render following a Clear
    # already carries the new persistent thread_id/clear_epoch. It avoids the old
    # two-rerun dependency that could leave the composer stale/disabled, and avoids
    # registering an extra V2 poll callback that proved incompatible in owner runtime.
    clear_req=st.session_state.pop("_scientist_chat_clear_requested",None)
    if isinstance(clear_req,dict):
        clear_factory=str(clear_req.get("factory_id") or factory_id)
        jid=str(st.session_state.get("pending_scientist_chat_job") or "")
        if jid:
            cancel_scientist_chat_job(APP_DIR,jid)
            cleanup_scientist_chat_job_files(APP_DIR,jid)
        st.session_state.pop("pending_scientist_chat_job",None)
        SCIENTIST_CHAT_STORE.clear(clear_factory)
        st.session_state.scientist_chat_last_error=""
        st.session_state.scientist_chat_notice=""
        st.session_state.scientist_chat_clear_epoch=int(st.session_state.get("scientist_chat_clear_epoch") or 0)+1
        # IMPORTANT: keep scientist_component_last_* nonce markers. V2 trigger
        # dedupe survives Clear so a replayed pre-clear SEND cannot resurrect history.
        st.session_state.pop("scientist_last_submit_signature",None)
        st.session_state.pop("scientist_last_submit_monotonic",None)
        # The selected Factory can change independently of Chat visibility. Re-resolve
        # after applying the requested thread boundary so this render is authoritative.
        fd=_scientist_chat_factory(); factory_id=fd.name if fd else "NO_FACTORY"
    active=latest_factory_job(FACTORY_DIR,active_only=True); live_rows=[]
    if isinstance(active,dict) and active.get("job_id"):
        try: live_rows=read_factory_candidates(FACTORY_DIR,str(active.get("job_id") or ""))
        except Exception: live_rows=[]

    llmc=cfg.setdefault("agent",{}).setdefault("llm",{})
    connected=st.session_state.get("llm_models") if st.session_state.get("llm_provider_connected") else []
    models=available_chat_models(llmc,connected)
    if st.session_state.get("scientist_chat_route_contract") != "R4_STRICT_MANUAL_V1":
        st.session_state.scientist_chat_fallback=False; st.session_state.scientist_chat_route_contract="R4_STRICT_MANUAL_V1"

    saved=str(st.session_state.get("scientist_chat_model") or "")
    if models and saved not in models:
        preferred=str(llmc.get("model") or ""); st.session_state.scientist_chat_model=preferred if preferred in models else models[0]
    selected_model=str(st.session_state.get("scientist_chat_model") or (models[0] if models else ""))

    scopes=["AUTO","CURRENT FACTORY","CURRENT GENERATION","MODEL & CANDIDATES","DATA QUALITY","RESEARCH SETTINGS","SCIENTIST MEMORY"]
    if str(st.session_state.get("scientist_chat_context_scope") or "AUTO") not in scopes:
        st.session_state.scientist_chat_context_scope="AUTO"
    selected_context=str(st.session_state.get("scientist_chat_context_scope") or "AUTO")
    scope_labels={"AUTO":"AUTO","CURRENT FACTORY":"FACTORY","CURRENT GENERATION":"GEN","MODEL & CANDIDATES":"MODEL","DATA QUALITY":"DATA","RESEARCH SETTINGS":"SETTINGS","SCIENTIST MEMORY":"MEMORY"}

    chat_fallback_models=[m for m in available_chat_fallback_models(llmc) if m!=selected_model]
    if not chat_fallback_models: st.session_state.scientist_chat_fallback=False

    thread_id=SCIENTIST_CHAT_STORE.current_thread_id(factory_id)
    pending_job=_settle_scientist_chat_job(factory_id,thread_id)
    pending=bool(pending_job and str(pending_job.get("status") or "") in {"QUEUED","RUNNING"})
    pending_jid=str((pending_job or {}).get("job_id") or "")
    pending_model=str((pending_job or {}).get("requested_model") or selected_model)

    history=SCIENTIST_CHAT_STORE.load(factory_id)
    visible=[m for m in history if isinstance(m,dict) and str(m.get("role") or "") in {"user","assistant"} and not bool(m.get("error"))]
    messages=[]
    for msg in visible[-80:]:
        role="user" if str(msg.get("role") or "") == "user" else "assistant"; content=str(msg.get("content") or "").strip()
        if not content: continue
        answered=str(msg.get("answered_by") or msg.get("requested_model") or "")
        _proc=msg.get("process") if isinstance(msg.get("process"),dict) else {}
        _steps=[str((x or {}).get("label") or "") for x in (_proc.get("steps") or []) if isinstance(x,dict) and str((x or {}).get("label") or "").strip()]
        messages.append({"role":role,"content":content,"fallback_used":bool(msg.get("fallback_used")),"answered_by":_chat_model_label(answered) if role=="assistant" else "","process_steps":_steps[-5:] if role=="assistant" else [],"analysis_depth":str(_proc.get("analysis_depth") or "") if role=="assistant" else "","streamed":bool(_proc.get("streamed")) if role=="assistant" else False})

    last_error=str(st.session_state.get("scientist_chat_last_error") or "").strip()
    notice=str(st.session_state.get("scientist_chat_notice") or "").strip()
    mode_label="LIVE" if active else "Snapshot"
    status_text=f"Read-only · {mode_label}" + (" · Generating" if pending else (" · Provider issue" if last_error else (f" · {notice}" if notice else "")))
    data={
        "factory_id":factory_id,"thread_id":thread_id,"status_text":status_text,"status_error":bool(last_error),
        "models":models,"model_labels":{m:_chat_model_label(m) for m in models},"selected_model":selected_model,
        "contexts":scopes,"context_labels":scope_labels,"selected_context":selected_context,
        "fallback_enabled":bool(st.session_state.get("scientist_chat_fallback",False)),"chat_fallback_models":chat_fallback_models,
        "messages":messages,"history_signature":str(hash(json.dumps(messages,ensure_ascii=False,sort_keys=True))),
        "pending":pending,"pending_job_id":pending_jid,"pending_model_label":_chat_model_label(pending_model),
        "pending_phase":str((pending_job or {}).get("phase") or "QUEUED"),"pending_phase_label":str((pending_job or {}).get("phase_label") or "Scientist working"),
        "pending_partial_text":str((pending_job or {}).get("partial_text") or ""),
        "pending_process_steps":[str((x or {}).get("label") or "") for x in ((pending_job or {}).get("process_steps") or []) if isinstance(x,dict) and str((x or {}).get("label") or "").strip()][-5:],
        "error_text":last_error,"clear_epoch":int(st.session_state.get("scientist_chat_clear_epoch") or 0),
    }
    def _request_scientist_clear():
        # V2 clear trigger callback executes before the resulting fragment rerun.
        # Queue only a tiny serializable marker; the store mutation happens at the
        # top of this renderer before any new thread data is sent to the browser.
        st.session_state["_scientist_chat_clear_requested"]={"factory_id":factory_id}

    with st.container(key="scientist_chat_drawer"):
        result=render_scientist_chat_component(
            data=data,
            key="scientist_chat_component_r4",
            on_clear_change=_request_scientist_clear,
        )

    model_state=str(getattr(result,"model","") or "")
    if model_state in models: st.session_state.scientist_chat_model=model_state
    context_state=str(getattr(result,"context","") or "")
    if context_state in scopes: st.session_state.scientist_chat_context_scope=context_state
    st.session_state.scientist_chat_fallback=bool(getattr(result,"fallback",False)) if chat_fallback_models else False

    def _fresh_event(name: str, payload):
        if not isinstance(payload,dict) or not payload.get("nonce"): return None
        nonce=str(payload.get("nonce")); sk=f"scientist_component_last_{name}_nonce"
        if str(st.session_state.get(sk) or "") == nonce: return None
        st.session_state[sk]=nonce; return payload

    stop_ev=_fresh_event("stop",getattr(result,"stop",None))
    if stop_ev:
        jid=str(st.session_state.get("pending_scientist_chat_job") or stop_ev.get("job_id") or "")
        event_thread=str(stop_ev.get("thread_id") or "")
        terminal={}
        if jid and (not event_thread or event_thread==thread_id):
            terminal=cancel_scientist_chat_job(APP_DIR,jid) or {}
        terminal_status=str(terminal.get("status") or "")
        if terminal_status=="STOPPED":
            st.session_state.scientist_chat_notice="Generation stopped."; st.session_state.scientist_chat_last_error=""
            st.session_state.pop("pending_scientist_chat_job",None)
        elif terminal_status in {"COMPLETED","FAILED"}:
            # STOP raced a worker terminal commit. Keep the pending id so the next
            # reconciliation folds the already-terminal result exactly once.
            st.session_state.scientist_chat_notice=""
        _rerun_current_fragment()

    close_ev=_fresh_event("close",getattr(result,"close",None))
    if close_ev:
        st.session_state.scientist_chat_open=False; persist_user_settings(); st.rerun()

    # Consume the transient clear trigger nonce for parity/audit. The actual clear
    # was already applied before this render by on_clear_change. Never clear twice.
    _fresh_event("clear",getattr(result,"clear",None))

    send_ev=_fresh_event("send",getattr(result,"send",None))
    if send_ev and not pending:
        event_thread=str(send_ev.get("thread_id") or "").strip()
        if event_thread != thread_id:
            st.session_state.scientist_chat_notice="Stale send ignored after chat reset."
            _rerun_current_fragment()
        prompt=str(send_ev.get("text") or "").strip(); model=str(send_ev.get("model") or st.session_state.get("scientist_chat_model") or "").strip(); context_scope=str(send_ev.get("context") or st.session_state.get("scientist_chat_context_scope") or "AUTO")
        if model not in models:
            st.session_state.scientist_chat_last_error="Selected Chat model is no longer available."; _rerun_current_fragment()
        if context_scope not in scopes: context_scope="AUTO"
        allow_fallback=bool(send_ev.get("fallback")) and bool(available_chat_fallback_models(llmc))
        if prompt:
            request_id=str(send_ev.get("nonce") or "").strip() or (datetime.utcnow().strftime("REQ_%Y%m%d%H%M%S%f"))
            # Backend idempotency authority. Streamlit/component reruns may replay a UI
            # event, but one request_id may create at most one persisted user turn/job.
            history=SCIENTIST_CHAT_STORE.load(factory_id)
            if any(str(m.get("request_id") or "")==request_id for m in history if isinstance(m,dict)):
                _rerun_current_fragment()
            _sig=(factory_id,model,context_scope,prompt)
            _prev=st.session_state.get("scientist_last_submit_signature")
            _prev_at=float(st.session_state.get("scientist_last_submit_monotonic",0.0) or 0.0)
            import time as _time
            _now=_time.monotonic()
            if _prev==_sig and (_now-_prev_at)<2.0:
                st.session_state.scientist_chat_notice="Duplicate send ignored."
                _rerun_current_fragment()
            st.session_state["scientist_last_submit_signature"]=_sig
            st.session_state["scientist_last_submit_monotonic"]=_now
            try:
                _chat_live_hw=_ui_hardware_profile_cached()
            except Exception as _hw_exc:
                _chat_live_hw={"schema":"MAX_SCIENTIST_LIVE_HARDWARE_ERROR_V1","status":"UNAVAILABLE","error_class":type(_hw_exc).__name__}
            try:
                _chat_live_compute=resolve_compute_plan(cfg)
            except Exception as _compute_exc:
                _chat_live_compute={"schema":"MAX_SCIENTIST_LIVE_COMPUTE_ERROR_V1","status":"UNAVAILABLE","error_class":type(_compute_exc).__name__}
            context=build_read_only_context(
                fd,scope=context_scope,live_job=active,live_candidates=live_rows,
                research_settings=build_research_settings_snapshot(cfg),
                live_hardware=_chat_live_hw,live_compute_plan=_chat_live_compute,
            )
            history.append({"role":"user","content":prompt,"request_id":request_id,"thread_id":thread_id,"created_utc":datetime.utcnow().isoformat()+"Z"}); SCIENTIST_CHAT_STORE.save(factory_id,history,thread_id=thread_id)
            req={
                "factory_id":factory_id,"thread_id":thread_id,"request_id":request_id,"llm_cfg":_chat_worker_cfg(llmc),"selected_model":model,
                "history":history[:-1],"user_prompt":prompt,"context":context,"allow_fallback":allow_fallback,
            }
            try:
                job=start_scientist_chat_job(APP_DIR,req,st.session_state.llm_api_key)
                st.session_state["pending_scientist_chat_job"]=job["job_id"]; st.session_state.scientist_chat_last_error=""; st.session_state.scientist_chat_notice=""
            except Exception as exc:
                st.session_state.scientist_chat_last_error=_chat_error_text(exc,model)
            _rerun_current_fragment()


def _render_research_control(cfg: dict):
    fc=cfg.setdefault("champion_factory",{})
    current=get_research_mode(cfg)
    labels=["AUTO FACTORY","MANUAL RESEARCH"]
    picked=st.radio(
        "Research mode",labels,index=0 if current=="AUTO" else 1,horizontal=True,
        key="research_control_mode",
        help="AUTO lets Max propose/search candidates. MANUAL runs only the exact Owner candidates below. Deterministic validation remains mandatory in both modes.",
    )
    mode="MANUAL" if picked=="MANUAL RESEARCH" else "AUTO"
    fc["research_mode"]=mode
    _training_method = training_method_context()
    if mode=="AUTO":
        st.markdown("**AUTO FACTORY** · LLM Research Scientist (when enabled) + deterministic candidate discovery + deterministic validation.")
        st.caption("LLM may propose experiments but cannot grant PASS. Concrete Scientist candidates are strict against effective bounds; all modes share MODEL_TRAINING_METHOD_CONTRACT_V1.")
        return

    mr=fc.setdefault("manual_research",{})
    mr["schema"]="MAX_MANUAL_RESEARCH_V1"; mr["enabled"]=True
    st.markdown("**MANUAL RESEARCH** · Owner exact candidates · **0 LLM calls · 0 deterministic candidate discovery**")
    st.caption("Only proposal/discovery authority is disabled. Full WFA, CPCV, Tournament, Monte Carlo, Fresh/Locked Forward and Champion gates remain mandatory and deterministic. Training methodology is read-only from MODEL_TRAINING_METHOD_CONTRACT_V1.")

    top=st.columns([1,1,1.2],gap="small")
    existing=[x for x in (mr.get("candidates") or []) if isinstance(x,dict)]
    count=int(top[0].number_input("Exact candidates",1,8,max(1,min(8,int(mr.get("candidate_count",len(existing) or 1)))),1,key="manual_research_candidate_count"))
    mr["candidate_count"]=count
    mr["take_threshold"]=float(top[1].number_input("Exact take threshold",0.01,0.99,float(mr.get("take_threshold",0.65)),0.01,key="manual_research_take_threshold"))
    mr["minimum_wfa_survivors"]=int(top[2].number_input("Minimum WFA survivors",1,count,min(count,max(1,int(mr.get("minimum_wfa_survivors",1) or 1))),1,key="manual_research_min_survivors"))

    families=[f for f in all_families(include_legacy=False,include_dynamic=True) if bool((family_spec(f) or {}).get("deployable",True))]
    if not families:
        st.error("No deployable model families are registered.")
        return
    _manual_size_advisor=_current_model_size_advisor(cfg)
    _manual_advisor_families=((_manual_size_advisor or {}).get("families") or {})
    while len(existing)<count:
        existing.append(default_manual_candidate(families[0],len(existing)+1))
    existing=existing[:count]
    edited=[]
    for i,row0 in enumerate(existing,1):
        fam0=str(row0.get("family") or families[0]).lower()
        if fam0 not in families: fam0=families[0]
        with st.expander(f"Manual candidate {i} · {_family_display_name(fam0)}",expanded=(i==1)):
            family=st.selectbox(
                "Exact model family",families,index=families.index(fam0),
                format_func=_family_display_name,key=f"manual_candidate_family_{i}",
            )
            if family!=fam0:
                row=default_manual_candidate(family,i)
            else:
                row=dict(row0); row.setdefault("params",{})
            row["family"]=family
            row["name"]=st.text_input("Candidate name",value=str(row.get("name") or f"manual_{family}_{i:02d}"),key=f"manual_candidate_name_{i}")[:64]
            bounds=get_bounds([family]).get(family,{})
            params=dict(row.get("params") or {})
            st.caption("Every research parameter below is exact Owner input. Illegal/out-of-capacity values fail closed before the worker starts; they are never silently widened.")
            cols=st.columns(3,gap="small")
            _family_advice=dict(_manual_advisor_families.get(family) or {})
            _manual_ranges=dict(_family_advice.get("manual_parameter_ranges") or {})
            _family_suggestion=dict(_family_advice.get("suggestion") or {})
            for j,(key,(lo,hi,typ)) in enumerate(bounds.items()):
                default=params.get(key,(int(round((float(lo)+float(hi))/2)) if typ is int else (float(lo)+float(hi))/2.0))
                _pair=cols[j%3].columns([5.0,.72],gap="small")
                if typ is int:
                    value=int(round(float(default))); value=max(int(lo),min(int(hi),value))
                    params[key]=int(_pair[0].number_input(key,min_value=int(lo),max_value=int(hi),value=value,step=1,key=f"manual_c{i}_{key}"))
                else:
                    value=float(default); value=max(float(lo),min(float(hi),value))
                    span=max(1e-9,float(hi)-float(lo)); step=max(1e-6,span/100.0)
                    params[key]=float(_pair[0].number_input(key,min_value=float(lo),max_value=float(hi),value=value,step=float(step),format="%.6g",key=f"manual_c{i}_{key}"))
                _range=dict(_manual_ranges.get(key) or {})
                # Dynamic MANUAL hybrids inherit suggestion doctrine from their exact
                # temporal/policy components; there is intentionally no separate AUTO
                # hybrid-size slider.
                if not _range and hybrid_parts(family):
                    _parts=hybrid_parts(family) or (None,None)
                    if key.startswith("temporal_") and _parts[0]:
                        _range=dict((((_manual_advisor_families.get(_parts[0]) or {}).get("manual_parameter_ranges") or {}).get(key[len("temporal_"):]) or {}))
                    elif key.startswith("policy_") and _parts[1]:
                        _range=dict((((_manual_advisor_families.get(_parts[1]) or {}).get("manual_parameter_ranges") or {}).get(key[len("policy_"):]) or {}))
                    elif key=="training_memory_months" and _parts[0] and _parts[1]:
                        _ta=dict((((_manual_advisor_families.get(_parts[0]) or {}).get("manual_parameter_ranges") or {}).get(key) or {}))
                        _pa=dict((((_manual_advisor_families.get(_parts[1]) or {}).get("manual_parameter_ranges") or {}).get(key) or {}))
                        _tsg=_ta.get("suggested") or []; _psg=_pa.get("suggested") or []
                        if len(_tsg)>=2 and len(_psg)>=2:
                            _ilo=max(float(_tsg[0]),float(_psg[0])); _ihi=min(float(_tsg[1]),float(_psg[1]))
                            if _ilo<=_ihi:
                                _range={"suggested":[int(round(_ilo)) if typ is int else _ilo,int(round(_ihi)) if typ is int else _ihi],"allowed":[lo,hi],"size_controlled":False}
                with _pair[1].popover("?",help=f"Suggested range for {key}. Advisory only; clicking never changes the exact Owner value."):
                    st.markdown(f"**{_family_display_name(family)} · {key}**")
                    st.markdown(f"Current exact value: **{_format_bound_value(params[key])}**")
                    _sg=_range.get("suggested") or []
                    if len(_sg)>=2:
                        st.markdown(f"Suggested range: **{_format_bound_value(_sg[0])} – {_format_bound_value(_sg[1])}**")
                    else:
                        st.caption("Suggested range unavailable until a valid Factory dataset/WFA basis is available.")
                    st.caption(f"Allowed contract: {_format_bound_value(lo)} – {_format_bound_value(hi)}")
                    if bool(_range.get("size_controlled")):
                        _sp=_family_suggestion.get("suggested_priority")
                        st.caption((f"Size-controlled parameter · suggestion derived from AUTO size {_sp:.2f}. " if _sp is not None else "Size-controlled parameter. ") + "MANUAL remains exact Owner authority.")
                    else:
                        st.caption("Manual exact values are not hard-sliced by the AUTO size preference; final Factory-start admission still requires legal, resource-safe, and scientifically admitted capacity.")
            row["params"]=params
            edited.append(row)
    mr["candidates"]=edited

    st.markdown("**Validation authority · locked ON**")
    v=st.columns(5,gap="small")
    for col,label in zip(v,["Full WFA","CPCV","Tournament","Monte Carlo","Fresh / Champion"]):
        col.markdown(f"✓ **{label}**")
    try:
        _,validated=compile_manual_runtime(cfg)
        st.success(f"Manual contract valid · {len(validated)} exact candidate(s) ready. START MANUAL RESEARCH will make zero LLM calls and generate zero extra candidates.")
    except Exception as exc:
        st.error("Manual contract blocked: "+str(exc))


def _render_advanced_stage(cfg: dict):
    _page_header("Advanced", "Configuration")
    with st.expander("Research",expanded=True):
        _render_research_control(cfg)
        _subsection_header("Execution & labels", "Sampling, WFA structure and outcome policy")
        core_controls(cfg,"advanced")
        _subsection_header("Adaptive model research", "Family capacity and bounded experiment policy")
        _render_adaptive_model_research(cfg)

    with st.expander("Scientist",expanded=True):
        llmc=cfg.setdefault("agent",{}).setdefault("llm",{})
        llmc["enabled"]=st.toggle("Enable LLM Scientist",value=bool(llmc.get("enabled",False)),key="advanced_llm_enable")
        llm_provider_controls(llmc)
        _subsection_header("Creativity", "Changes experiment breadth only; deterministic gates remain immutable")
        ac=cfg.setdefault("agent",{}); search=ac.setdefault("search",{})
        a,b=st.columns(2)
        llmc["max_proposals_per_round"]=int(a.number_input("Scientist proposals / round",1,10,int(llmc.get("max_proposals_per_round",5)),1,key="advanced_scientist_proposals"))
        search["scientific_creativity"]=float(b.slider("Scientific creativity",0.0,1.0,float(search.get("scientific_creativity",0.50)),0.05,key="advanced_scientific_creativity"))
        a,b,c,d=st.columns(4)
        search["exploration_ratio"]=float(a.slider("Base exploration",0.15,0.85,float(search.get("exploration_ratio",0.45)),0.05,key="advanced_base_exploration"))
        search["crossover_ratio"]=float(b.slider("Crossover",0.0,0.8,float(search.get("crossover_ratio",0.30)),0.05,key="advanced_crossover"))
        search["min_family_weight"]=float(c.slider("Min family weight",0.02,0.25,float(search.get("min_family_weight",0.08)),0.01,key="advanced_min_family_weight"))
        search["llm_research_influence"]=float(d.slider("LLM influence",0.0,1.0,float(search.get("llm_research_influence",search.get("llm_strategy_weight",0.45))),0.05,key="advanced_llm_research_influence")); search["llm_strategy_weight"]=search["llm_research_influence"]
        cp=adaptive_creativity_profile(cfg); pt=cp.get("phase_temperatures") or {}
        st.caption(f"Adaptive {cp.get('mode')} · exploration {cp.get('target_exploration_ratio',0):.2f} · hypothesis temp {pt.get('DISCOVERY_HYPOTHESIS',0):.2f} · forensic temp {pt.get('STAGE_FORENSIC',0):.2f}")

    with st.expander("KPI & Evaluation",expanded=True):
        render_gate_kpi_controls(cfg)
        _subsection_header("Evaluation engine", "Budget/flow settings; statistical thresholds stay above in their owning gate")
        fc=cfg.setdefault("champion_factory",{})
        a,b=st.columns(2); fc["monte_carlo_simulations"]=int(a.number_input("Monte Carlo simulations / survivor",100,500000,int(fc.get("monte_carlo_simulations",10000)),1000,key="advanced_mc_simulations")); fc["orchestrator_max_cycles"]=int(b.number_input("Auto Orchestrator max cycles · 0 = terminal",0,100,int(fc.get("orchestrator_max_cycles",0) or 0),1,key="advanced_orchestrator_max_cycles"))
        cs=fc.setdefault("cpcv_stage",{}); a,b,c=st.columns(3); cs["target_survivors"]=int(a.number_input("CPCV survivor target",1,12,int(cs.get("target_survivors",3)),1,key="advanced_cpcv_target")); cs["finalist_batch_size"]=int(b.number_input("CPCV finalist batch",1,12,int(cs.get("finalist_batch_size",3)),1,key="advanced_cpcv_batch")); cs["max_finalists"]=int(c.number_input("CPCV max finalists",1,12,int(cs.get("max_finalists",12)),1,key="advanced_cpcv_max"))

    with st.expander("Compute & hardware",expanded=True):
        _render_compute_backend_control(cfg)

    with st.expander("Legacy diagnostics",expanded=False):
        runs=list_runs(RUNS_DIR)
        if runs:
            name=st.selectbox("Legacy lineage",[p.name for p in runs],key="advanced_legacy_lineage"); rd=next(p for p in runs if p.name==name); st.caption(f"Status {load_manifest(rd).get('status')} · {rd}")
        else: st.caption("No legacy research runs.")

ensure_state(); cfg=st.session_state.ui_cfg
pages=["Research","Data","Discovery","Pool","CPCV","Tournament","Monte Carlo","Forward Championship","Model Challengers","Model Champion","Advanced","Strategy Optimizer","Strategy Challengers","Strategy Champion"]
STRATEGY_NAV_PAGES=frozenset({"Strategy Optimizer","Strategy Challengers","Strategy Champion"})


def _is_strategy_nav_page(page: str) -> bool:
    return str(page) in STRATEGY_NAV_PAGES

# UI ADAPTIVE RECOVERY CONTRACT:
# - No st.sidebar is used by the shell. LeftNav and Scientist are fixed viewport panels.
# - ShellState is the only authority that changes main workspace margins / drawer transforms.
# - Main page navigation targets only the workspace fragment.
# - Scientist remains mounted so chat history/model/context/draft survive page and drawer operations.
# - Wide screens reflow; <=900px uses slide-over drawers; chat regions are viewport-anchored to prevent overlap.

st.markdown("""
<style>
/* RESPONSIVE SHELL AUTHORITY — one CSS system for left/main/right. */
:root{
  --cp-left-w:clamp(196px,14vw,224px);
  --cp-scientist-w:clamp(336px,25vw,410px);
  --cp-chat-head-h:52px;
  --cp-chat-tools-h:58px;
  --cp-chat-compose-h:62px;
  --cp-shell-ease:180ms cubic-bezier(.2,.8,.2,1);
}
*{box-sizing:border-box;}
[data-testid="stSidebar"],[data-testid="stSidebarCollapsedControl"],[data-testid="stSidebarCollapseButton"]{display:none!important;}
[data-testid="stAppViewContainer"],.stApp{height:100dvh!important;max-height:100dvh!important;overflow:hidden!important;}
section[data-testid="stMain"],.stMain{min-width:0!important;width:auto!important;height:100dvh!important;max-height:100dvh!important;min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important;overscroll-behavior-y:contain!important;scrollbar-gutter:stable!important;transition:margin-left var(--cp-shell-ease),margin-right var(--cp-shell-ease)!important;}
.block-container{max-width:none!important;width:100%!important;min-height:max-content!important;overflow:visible!important;margin:0!important;padding:.45rem clamp(.7rem,1.45vw,1.55rem) 4rem!important;}

/* LEFT NAV — adaptive width, browser height, internal scroll only. */
.st-key-left_nav_panel{position:fixed!important;left:0!important;top:0!important;bottom:0!important;width:var(--cp-left-w)!important;max-width:88vw!important;height:100dvh!important;z-index:1450!important;background:#08121f!important;border-right:1px solid var(--cp-border-soft)!important;overflow:hidden!important;padding:.6rem .65rem .7rem!important;transition:transform var(--cp-shell-ease)!important;display:grid!important;grid-template-rows:auto minmax(0,1fr) auto!important;gap:0!important;}
.st-key-left_nav_panel>[data-testid="stVerticalBlockBorderWrapper"],.st-key-left_nav_panel>div>[data-testid="stVerticalBlockBorderWrapper"]{height:100%!important;min-height:0!important;border:0!important;padding:0!important;margin:0!important;background:transparent!important;}
.st-key-left_nav_panel>[data-testid="stVerticalBlockBorderWrapper"]>[data-testid="stVerticalBlock"],.st-key-left_nav_panel>div>[data-testid="stVerticalBlockBorderWrapper"]>[data-testid="stVerticalBlock"]{height:100%!important;min-height:0!important;display:grid!important;grid-template-rows:auto minmax(0,1fr) auto!important;gap:0!important;padding:0!important;}
.st-key-left_nav_header{position:relative!important;z-index:4!important;background:#08121f!important;padding:.15rem 0 .45rem!important;border-bottom:1px solid var(--cp-border-soft)!important;margin:0 0 .45rem!important;overflow:hidden!important;}
.st-key-left_nav_nav{min-height:0!important;overflow-y:auto!important;overflow-x:hidden!important;scrollbar-width:thin!important;overscroll-behavior:contain!important;padding:.05rem 0 .55rem!important;}
.st-key-left_nav_footer{position:relative!important;z-index:3!important;background:#08121f!important;border-top:1px solid var(--cp-border-soft)!important;padding:.55rem 0 .05rem!important;overflow:visible!important;min-height:max-content!important;}
.st-key-left_nav_header>[data-testid="stVerticalBlockBorderWrapper"],.st-key-left_nav_header>div>[data-testid="stVerticalBlockBorderWrapper"]{overflow:visible!important;}
.st-key-left_nav_header [data-testid="stVerticalBlock"]{position:relative!important;display:block!important;overflow:visible!important;padding:0!important;gap:0!important;}
.st-key-left_nav_hide{position:absolute!important;top:4px!important;right:0!important;width:32px!important;height:32px!important;z-index:8!important;margin:0!important;}
.st-key-left_nav_hide button{width:32px!important;height:32px!important;min-height:32px!important;padding:0!important;border-radius:8px!important;margin:0!important;}
.st-key-left_nav_panel .cp-side-brand{padding:.2rem 38px .28rem 0!important;margin:0!important;border:0!important;min-width:0!important;width:100%!important;overflow:visible!important;}
.st-key-left_nav_panel .cp-side-logo{display:block!important;min-width:0!important;max-width:100%!important;}
.st-key-left_nav_panel .cp-side-name{max-width:100%!important;overflow:visible!important;white-space:normal!important;font-size:.94rem!important;line-height:1.1!important;}
.st-key-left_nav_panel .cp-side-ver{max-width:100%!important;overflow:visible!important;text-overflow:clip!important;white-space:normal!important;line-height:1.32!important;font-size:.60rem!important;margin-top:.18rem!important;color:var(--cp-muted)!important;}
.st-key-left_nav_panel .cp-side-build{display:block!important;margin-top:.05rem!important;color:#7891ad!important;}
.st-key-left_nav_panel div[role="radiogroup"]{position:static!important;display:flex!important;flex-direction:column!important;gap:.14rem!important;overflow:visible!important;padding:.08rem!important;margin:.1rem 0 .7rem!important;border:0!important;background:transparent!important;box-shadow:none!important;backdrop-filter:none!important;}
.st-key-left_nav_panel div[role="radiogroup"] label{width:100%!important;padding:.48rem .62rem!important;border-radius:8px!important;}
/* Left navigation is a menu, not a questionnaire: keep radio semantics/state, hide only the visual bullet. */
.st-key-left_nav_panel label[data-testid="stRadioOption"] > div > div > div:first-child{display:none!important;}
.st-key-left_nav_panel label[data-testid="stRadioOption"] > div > div{gap:0!important;}
.st-key-left_nav_panel div[role="radiogroup"] label p{font-size:.74rem!important;font-weight:760!important;white-space:normal!important;overflow-wrap:anywhere!important;}
.st-key-left_nav_panel div[role="radiogroup"] label:has(input:checked){background:#18365d!important;box-shadow:inset 3px 0 0 var(--cp-blue)!important;}
/* Strategy pages are one compact section. Separate the section before Strategy Optimizer,
   never between Strategy Optimizer / Challengers / Champion. Page 12 is Strategy Optimizer. */
.st-key-left_nav_panel div[role="radiogroup"] label:nth-of-type(12){margin-top:.68rem!important;position:relative!important;}
.st-key-left_nav_panel div[role="radiogroup"] label:nth-of-type(12)::before{content:"";position:absolute;left:.18rem;right:.18rem;top:-.42rem;height:1px;background:var(--cp-border-soft);pointer-events:none;}
.st-key-left_nav_panel div[role="radiogroup"] label:nth-of-type(13),
.st-key-left_nav_panel div[role="radiogroup"] label:nth-of-type(14){margin-top:0!important;}
.st-key-left_nav_footer .st-key-global_research_lifecycle,.st-key-left_nav_footer .st-key-global_optimizer_lifecycle,.st-key-left_nav_footer .st-key-contextual_lifecycle_controls{position:relative!important;z-index:1!important;background:#08121f!important;padding:0!important;margin:0!important;border:0!important;border-radius:0!important;box-shadow:none!important;}
.st-key-left_nav_footer .st-key-global_research_lifecycle [data-testid="stVerticalBlock"],.st-key-left_nav_footer .st-key-global_optimizer_lifecycle [data-testid="stVerticalBlock"],.st-key-left_nav_footer .st-key-contextual_lifecycle_controls [data-testid="stVerticalBlock"]{padding:0!important;gap:.18rem!important;overflow:visible!important;}
.st-key-left_nav_footer .st-key-global_research_lifecycle [data-testid="stVerticalBlockBorderWrapper"],.st-key-left_nav_footer .st-key-global_optimizer_lifecycle [data-testid="stVerticalBlockBorderWrapper"],.st-key-left_nav_footer .st-key-contextual_lifecycle_controls [data-testid="stVerticalBlockBorderWrapper"]{border:0!important;background:transparent!important;border-radius:0!important;padding:0!important;box-shadow:none!important;}
.st-key-left_nav_footer .cp-live-status{width:100%!important;margin:0 0 .44rem!important;padding:.12rem 0 .4rem!important;border-radius:0!important;background:transparent!important;}
.st-key-left_nav_footer .st-key-global_research_lifecycle div.stButton>button,.st-key-left_nav_footer .st-key-global_optimizer_lifecycle div.stButton>button{width:100%!important;min-height:2rem!important;padding:.22rem .38rem!important;font-size:.66rem!important;border-radius:7px!important;margin:0!important;}
.st-key-left_nav_footer .st-key-global_research_lifecycle div.stButton>button:disabled,.st-key-left_nav_footer .st-key-global_optimizer_lifecycle div.stButton>button:disabled{background:#27313e!important;border-color:#3a4655!important;color:#8b98a8!important;opacity:.88!important;cursor:not-allowed!important;}
.st-key-left_nav_restore{position:fixed!important;left:0!important;top:50%!important;transform:translateY(-50%)!important;width:32px!important;z-index:1510!important;transition:opacity .12s ease!important;}
.st-key-left_nav_restore button{width:32px!important;height:54px!important;min-height:54px!important;padding:0!important;border-radius:0 9px 9px 0!important;border-left:0!important;}

/* SCIENTIST — position each region directly. No fragile parent-grid dependency. */
.st-key-scientist_chat_drawer{position:fixed!important;top:0!important;right:0!important;bottom:0!important;width:var(--cp-scientist-w)!important;max-width:94vw!important;height:100dvh!important;z-index:1460!important;background:#08121f!important;border-left:1px solid var(--cp-border)!important;box-shadow:-14px 0 28px rgba(0,0,0,.20)!important;overflow:hidden!important;padding:0!important;transition:transform var(--cp-shell-ease)!important;contain:layout paint!important;}
.st-key-scientist_chat_drawer>[data-testid="stVerticalBlockBorderWrapper"],.st-key-scientist_chat_drawer>div>[data-testid="stVerticalBlockBorderWrapper"]{border:0!important;background:transparent!important;border-radius:0!important;box-shadow:none!important;padding:0!important;margin:0!important;height:100%!important;min-height:0!important;}
.st-key-scientist_chat_drawer [data-testid="stVerticalBlock"]{min-width:0!important;height:100%!important;min-height:0!important;overflow:hidden!important;gap:0!important;padding:0!important;}
.st-key-scientist_chat_drawer [data-testid="stElementContainer"]{height:100%!important;min-height:0!important;overflow:hidden!important;margin:0!important;}
.st-key-scientist_chat_drawer [data-testid*="Component"]{height:100%!important;min-height:0!important;overflow:hidden!important;}
.st-key-scientist_chat_drawer [data-testid*="Component"]>div,.st-key-scientist_chat_drawer [data-testid*="Component"] iframe{height:100%!important;min-height:0!important;max-height:100%!important;overflow:hidden!important;}
.st-key-scientist_chat_topbar,.st-key-scientist_chat_config,.st-key-scientist_chat_history,.st-key-scientist_chat_compose{position:absolute!important;left:0!important;right:0!important;margin:0!important;min-width:0!important;}
.st-key-scientist_chat_topbar{top:0!important;height:var(--cp-chat-head-h)!important;min-height:var(--cp-chat-head-h)!important;max-height:var(--cp-chat-head-h)!important;overflow:hidden!important;padding:.5rem .62rem!important;border-bottom:1px solid var(--cp-border-soft)!important;background:#08121f!important;z-index:4!important;}
.st-key-scientist_chat_topbar [data-testid="stHorizontalBlock"]{align-items:center!important;gap:.35rem!important;flex-wrap:nowrap!important;}
.st-key-scientist_chat_close_button button{width:32px!important;height:32px!important;min-height:32px!important;padding:0!important;border-radius:8px!important;}
.cp-chat-title{font-size:.9rem;font-weight:900;color:var(--cp-text);line-height:1.05}.cp-chat-status{font-size:.56rem;color:var(--cp-muted);margin-top:.12rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.cp-chat-status.error{color:#ff9c9c}
.st-key-scientist_chat_config{top:var(--cp-chat-head-h)!important;height:var(--cp-chat-tools-h)!important;min-height:var(--cp-chat-tools-h)!important;max-height:var(--cp-chat-tools-h)!important;overflow:visible!important;padding:.45rem .6rem!important;border-bottom:1px solid var(--cp-border-soft)!important;background:#08121f!important;z-index:4!important;}
.st-key-scientist_chat_config [data-testid="stHorizontalBlock"]{gap:.38rem!important;align-items:center!important;flex-wrap:nowrap!important;}
/* Streamlit 1.63+ selectbox markup is not tied to BaseWeb. Style by semantic widget roles/testids,
   while retaining the legacy BaseWeb selector for backward-compatible rendering. */
.st-key-scientist_chat_config [data-baseweb="select"]>div,
.st-key-scientist_chat_config [data-testid="stSelectbox"]>div>div,
.st-key-scientist_chat_config [data-testid="stSelectbox"] [role="combobox"],
.st-key-scientist_chat_config [role="combobox"]{
  min-height:38px!important;height:38px!important;border-radius:9px!important;
  background:var(--cp-surface-2)!important;border-color:var(--cp-border)!important;
  color:var(--cp-text)!important;box-shadow:none!important;
}
.st-key-scientist_chat_config [data-testid="stSelectbox"] input,
.st-key-scientist_chat_config [role="combobox"] input{
  background:transparent!important;color:var(--cp-text)!important;
}
.st-key-scientist_chat_config [data-testid="stSelectbox"] svg,
.st-key-scientist_chat_config [role="combobox"] svg{color:var(--cp-muted)!important;fill:currentColor!important;}
.st-key-scientist_chat_config button{min-height:38px!important;height:38px!important;padding:.25rem .48rem!important;border-radius:9px!important;background:var(--cp-surface-2)!important;border-color:var(--cp-border)!important;color:var(--cp-text)!important;box-shadow:none!important;}
.st-key-scientist_chat_history{top:calc(var(--cp-chat-head-h) + var(--cp-chat-tools-h))!important;bottom:var(--cp-chat-compose-h)!important;height:auto!important;min-height:0!important;max-height:none!important;overflow-y:auto!important;overflow-x:hidden!important;overscroll-behavior:contain!important;padding:.72rem .7rem 1rem!important;background:#08121f!important;scrollbar-width:thin!important;scrollbar-gutter:stable!important;z-index:1!important;}
.st-key-scientist_chat_history>[data-testid="stVerticalBlock"],.st-key-scientist_chat_history>div>[data-testid="stVerticalBlock"]{gap:.55rem!important;padding:0!important;margin:0!important;min-width:0!important;}.cp-chat-empty{font-size:.74rem;color:var(--cp-muted);line-height:1.45;padding:.55rem .25rem;}
div[class*="st-key-scientist_message_user_"]{width:fit-content!important;max-width:min(84%,30rem)!important;margin:.08rem 0 .12rem auto!important;background:#142a44!important;border:1px solid #2b4f72!important;border-radius:13px 13px 4px 13px!important;padding:.48rem .68rem!important;overflow:visible!important;box-shadow:none!important;min-width:0!important;}
div[class*="st-key-scientist_message_assistant_"]{width:fit-content!important;max-width:min(94%,34rem)!important;margin:.08rem auto .12rem 0!important;background:#0f1c2d!important;border:1px solid #20364f!important;border-radius:13px 13px 13px 4px!important;padding:.58rem .72rem!important;overflow:visible!important;box-shadow:none!important;min-width:0!important;}
div[class*="st-key-scientist_message_user_"] [data-testid="stVerticalBlock"],div[class*="st-key-scientist_message_assistant_"] [data-testid="stVerticalBlock"]{gap:.2rem!important;padding:0!important;min-width:0!important;}
div[class*="st-key-scientist_message_user_"] [data-testid="stMarkdownContainer"],div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"]{overflow-wrap:anywhere!important;word-break:break-word!important;min-width:0!important;max-width:100%!important;}
div[class*="st-key-scientist_message_user_"] [data-testid="stMarkdownContainer"] p,div[class*="st-key-scientist_message_user_"] [data-testid="stMarkdownContainer"] li{margin:0!important;font-size:.78rem!important;line-height:1.42!important;color:var(--cp-text)!important;}
div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] p,div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] li{font-size:.78rem!important;line-height:1.48!important;color:var(--cp-text-2)!important;}
div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] p{margin:0 0 .48rem!important;}div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] p:last-child{margin-bottom:0!important;}div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] pre{white-space:pre-wrap!important;overflow-wrap:anywhere!important;max-width:100%!important;font-size:.68rem!important;}div[class*="st-key-scientist_message_assistant_"] [data-testid="stMarkdownContainer"] table{display:block!important;max-width:100%!important;overflow-x:auto!important;font-size:.68rem!important;}
.st-key-scientist_chat_compose{bottom:0!important;height:var(--cp-chat-compose-h)!important;min-height:var(--cp-chat-compose-h)!important;max-height:var(--cp-chat-compose-h)!important;overflow:hidden!important;padding:.48rem .6rem!important;background:#08121f!important;border-top:1px solid var(--cp-border-soft)!important;z-index:5!important;}.st-key-scientist_chat_compose [data-testid="stForm"]{border:0!important;padding:0!important;margin:0!important;background:transparent!important;}.st-key-scientist_chat_compose [data-testid="stForm"] [data-testid="stVerticalBlock"]{gap:0!important;padding:0!important;min-width:0!important;}.st-key-scientist_chat_compose [data-testid="stHorizontalBlock"]{gap:.36rem!important;align-items:center!important;flex-wrap:nowrap!important;}.st-key-scientist_chat_compose [data-testid="stTextInput"]{margin:0!important;min-width:0!important;}.st-key-scientist_chat_compose [data-testid="stTextInput"] input{height:42px!important;min-height:42px!important;max-height:42px!important;border-radius:10px!important;background:var(--cp-surface-2)!important;border-color:var(--cp-border)!important;font-size:.76rem!important;padding:.45rem .7rem!important;}.st-key-scientist_chat_compose [data-testid="stFormSubmitButton"] button{width:42px!important;height:42px!important;min-height:42px!important;padding:0!important;border-radius:10px!important;background:#1b3654!important;border:1px solid #31506f!important;font-size:1rem!important;}
.st-key-scientist_chat_restore{position:fixed!important;right:0!important;top:50%!important;transform:translateY(-50%)!important;width:32px!important;z-index:1510!important;transition:opacity .12s ease!important;}.st-key-scientist_chat_restore button{width:32px!important;height:54px!important;min-height:54px!important;padding:0!important;border-radius:9px 0 0 9px!important;border-right:0!important;}

/* Intermediate desktop: keep reflow, but compress both fixed regions safely. */
@media(max-width:1240px) and (min-width:901px){
  :root{--cp-left-w:clamp(184px,16vw,204px);--cp-scientist-w:clamp(310px,29vw,350px);}
  .block-container{padding-left:.72rem!important;padding-right:.72rem!important;}
  .st-key-left_nav_panel div[role="radiogroup"] label{padding:.42rem .46rem!important;}
  .st-key-left_nav_panel div[role="radiogroup"] label p{font-size:.70rem!important;}
}

/* Tablet/mobile: drawers become predictable slide-overs; main owns full viewport. */
@media(max-width:900px){
  :root{--cp-left-w:min(82vw,236px);--cp-scientist-w:min(92vw,420px);}
  section[data-testid="stMain"],.stMain{margin-left:0!important;margin-right:0!important;}
  .st-key-left_nav_panel{box-shadow:14px 0 26px rgba(0,0,0,.30)!important;}
  .st-key-scientist_chat_drawer{box-shadow:-14px 0 26px rgba(0,0,0,.30)!important;max-width:92vw!important;}
  .block-container{padding-left:.65rem!important;padding-right:.65rem!important;}
}

/* Phone: active drawer is almost full width, but close/restore controls remain reachable. */
@media(max-width:640px){
  :root{--cp-left-w:min(88vw,250px);--cp-scientist-w:100vw;--cp-chat-head-h:48px;--cp-chat-tools-h:54px;--cp-chat-compose-h:58px;}
  .st-key-scientist_chat_drawer{width:100vw!important;max-width:100vw!important;border-left:0!important;}
  .st-key-scientist_chat_topbar{padding:.38rem .5rem!important;}
  .st-key-scientist_chat_config{padding:.38rem .45rem!important;}
  .st-key-scientist_chat_config [data-testid="stHorizontalBlock"]{gap:.28rem!important;}
  .st-key-scientist_chat_config [data-baseweb="select"]>div,
  .st-key-scientist_chat_config [data-testid="stSelectbox"]>div>div,
  .st-key-scientist_chat_config [data-testid="stSelectbox"] [role="combobox"],
  .st-key-scientist_chat_config [role="combobox"],
  .st-key-scientist_chat_config button{height:36px!important;min-height:36px!important;}
  .st-key-scientist_chat_history{padding:.58rem .5rem .8rem!important;}
  div[class*="st-key-scientist_message_user_"],div[class*="st-key-scientist_message_assistant_"]{max-width:96%!important;}
  .st-key-scientist_chat_compose{padding:.38rem .45rem!important;}
  .st-key-scientist_chat_compose [data-testid="stTextInput"] input{height:40px!important;min-height:40px!important;max-height:40px!important;}
  .st-key-scientist_chat_compose [data-testid="stFormSubmitButton"] button{width:40px!important;height:40px!important;min-height:40px!important;}
  .cp-appbar{padding-left:.55rem!important;padding-right:.55rem!important;}
  .cp-top-context{display:none!important;}
}

/* Short screens: reserve vertical space deterministically instead of allowing overlap. */
@media(max-height:700px){
  :root{--cp-chat-head-h:46px;--cp-chat-tools-h:50px;--cp-chat-compose-h:56px;}
  .st-key-scientist_chat_topbar{padding:.32rem .5rem!important;}
  .st-key-scientist_chat_config{padding:.3rem .45rem!important;}
  .st-key-scientist_chat_config [data-baseweb="select"]>div,
  .st-key-scientist_chat_config [data-testid="stSelectbox"]>div>div,
  .st-key-scientist_chat_config [data-testid="stSelectbox"] [role="combobox"],
  .st-key-scientist_chat_config [role="combobox"],
  .st-key-scientist_chat_config button{height:34px!important;min-height:34px!important;}
  .st-key-scientist_chat_history{padding:.48rem .55rem .7rem!important;}
  .st-key-scientist_chat_compose{padding:.3rem .45rem!important;}
  .st-key-scientist_chat_compose [data-testid="stTextInput"] input{height:38px!important;min-height:38px!important;max-height:38px!important;}
  .st-key-scientist_chat_compose [data-testid="stFormSubmitButton"] button{width:38px!important;height:38px!important;min-height:38px!important;}
}
</style>
""",unsafe_allow_html=True)


def _render_nav_page(page: str, cfg: dict):
    if _is_strategy_nav_page(page):
        _rehydrate_persisted_ui_state(prefix="strategy_opt_")
    if page=="Research": _render_research_stage(cfg)
    elif page=="Strategy Optimizer":
        render_strategy_optimizer_page(cfg)
    elif page=="Data": _render_data_stage(cfg)
    elif page=="Discovery": _render_discovery_stage(cfg)
    elif page=="Pool": _render_pool_stage(cfg)
    elif page=="CPCV": _render_cpcv_stage(cfg)
    elif page=="Tournament": _render_tournament_stage(cfg)
    elif page=="Monte Carlo": _render_monte_carlo_stage(cfg)
    elif page=="Forward Championship": _render_forward_stage(cfg)
    elif page=="Model Challengers": _render_model_challengers_stage(cfg)
    elif page=="Model Champion": _render_model_champion_stage(cfg)
    elif page=="Strategy Challengers": _render_strategy_challengers_stage(cfg)
    elif page=="Strategy Champion": _render_strategy_champion_stage(cfg)
    elif page=="Advanced": _render_advanced_stage(cfg)
    else: st.error(f"Unknown navigation page: {page}")


def _set_left_open(value: bool):
    # CSS-only shell transition: keep LeftNav mounted so no widget state is rebuilt.
    st.session_state.left_nav_open=bool(value)
    persist_user_settings()
    st.rerun("shell_state")


def _set_scientist_open(value: bool):
    # Never rerun Scientist to hide/show it: an unsent form draft only exists in
    # the browser until submit, so rebuilding the fragment could discard it.
    st.session_state.scientist_chat_open=bool(value)
    persist_user_settings()
    st.rerun("shell_state")


def _nav_page_changed():
    # Navigation must refresh the workspace AND its contextual lifecycle footer in
    # the same event. Scientist is intentionally excluded so history/model/context
    # and the browser-held unsent draft remain mounted.
    target=str(st.session_state.get("nav_page_v071") or "Research")
    st.session_state["_workspace_render_pending"]={"page":target,"requested_utc":datetime.utcnow().isoformat()+"Z"}
    persist_user_settings()
    st.rerun(["workspace","contextual_lifecycle"])


@st.fragment(key="shell_state")
def _shell_state_fragment():
    left_open=bool(st.session_state.get("left_nav_open",True))
    chat_open=bool(st.session_state.get("scientist_chat_open",True))
    left_tx="0" if left_open else "calc(-1 * var(--cp-left-w) - 8px)"
    chat_tx="0" if chat_open else "calc(100% + 8px)"
    main_left="var(--cp-left-w)" if left_open else "0px"
    main_right="var(--cp-scientist-w)" if chat_open else "0px"
    left_restore=("0","none") if left_open else ("1","auto")
    chat_restore=("0","none") if chat_open else ("1","auto")
    st.markdown(f"""<style>
      .st-key-left_nav_panel{{transform:translateX({left_tx})!important;}}
      .st-key-scientist_chat_drawer{{transform:translateX({chat_tx})!important;}}
      /* ShellState owns visibility; viewport policy owns center geometry.
         Keep desktop reflow dynamic, but never let this late-injected style
         override the <=900px slide-over contract. */
      @media (min-width:901px){{
        section[data-testid="stMain"],.stMain{{margin-left:{main_left}!important;margin-right:{main_right}!important;}}
      }}
      @media (max-width:900px){{
        section[data-testid="stMain"],.stMain{{margin-left:0!important;margin-right:0!important;width:100%!important;max-width:100%!important;}}
      }}
      .st-key-left_nav_restore{{opacity:{left_restore[0]}!important;pointer-events:{left_restore[1]}!important;}}
      .st-key-scientist_chat_restore{{opacity:{chat_restore[0]}!important;pointer-events:{chat_restore[1]}!important;}}
    </style>""",unsafe_allow_html=True)


@st.fragment(run_every="2s", key="contextual_lifecycle")
def _render_contextual_lifecycle_controls(cfg: dict):
    """Single footer authority: Strategy lifecycle across the whole Strategy section; Research elsewhere.

    Do not mount two lifecycle fragments and hide one with cross-fragment CSS.
    That can leave stale/inverted controls after workspace-only navigation reruns.
    """
    nav_page=str(st.session_state.get("nav_page_v071") or "Research")
    with st.container(key="contextual_lifecycle_controls"):
        if _is_strategy_nav_page(nav_page):
            # The footer renders before the workspace on a full app pass and may rerun
            # independently as a fragment. Restore durable Optimizer widgets here so
            # Strategy Challenger/Champion START uses the same frozen operator setup.
            _rehydrate_persisted_ui_state(prefix="strategy_opt_")
            _render_global_optimizer_controls_body(cfg)
        else:
            _render_global_research_controls_body(cfg)


def _render_left_panel():
    with st.container(key="left_nav_panel"):
        with st.container(key="left_nav_header"):
            # One fixed header authority: no st.columns/horizontal wrapper.  The
            # hide control is absolutely anchored by CSS so the brand never
            # creates an internal horizontal scrollbar on narrow viewports.
            st.markdown('<div class="cp-side-brand"><div class="cp-side-logo"><div class="cp-side-name">Max</div><div class="cp-side-ver">MTF Research<span class="cp-side-build">v2.0.1</span></div></div></div>',unsafe_allow_html=True)
            st.button("‹",key="left_nav_hide",help="Hide navigation",on_click=_set_left_open,args=(False,))
        with st.container(key="left_nav_nav"):
            st.radio("Navigation",pages,horizontal=False,key="nav_page_v071",label_visibility="collapsed",on_change=_nav_page_changed,persist_state="session")
        with st.container(key="left_nav_footer"):
            _render_contextual_lifecycle_controls(cfg)
    with st.container(key="left_nav_restore"):
        st.button("›",key="left_nav_restore_button",help="Show navigation",use_container_width=True,on_click=_set_left_open,args=(True,))
    try: persist_user_settings()
    except Exception: pass


@st.fragment(key="workspace")
def _workspace_fragment():
    nav_page=str(st.session_state.get("nav_page_v071") or "Research")
    if nav_page not in pages:
        nav_page="Research"; st.session_state.nav_page_v071=nav_page
    pending_render=st.session_state.get("_workspace_render_pending") or {}
    render_pending=str(pending_render.get("page") or "")==nav_page
    render_slot=st.empty() if render_pending else None
    if render_slot is not None:
        render_slot.markdown(
            '<div class="cp-busy-row"><span class="cp-busy-spinner"></span><span>Rendering '+html.escape(nav_page)+'…</span><span class="cp-busy-pulse"><i></i><i></i><i></i></span></div>',
            unsafe_allow_html=True,
        )
    if _is_strategy_nav_page(nav_page):
        opt_job=latest_strategy_optimizer_job()
        opt_status=str((opt_job or {}).get("status") or "IDLE")
        if opt_job and opt_status in STRATEGY_OPTIMIZER_ACTIVE:
            round_no=int(opt_job.get("round") or 0)
            max_rounds=int((opt_job.get("request") or {}).get("max_rounds") or 1)
            chip=f'<span class="cp-chip blue">{html.escape(opt_status)}</span><span class="cp-chip">MT5 round {round_no}/{max_rounds}</span>'
        elif opt_job and opt_status in {"STRATEGY_CHALLENGER_FOUND","CHAMPION_FOUND","NO_CHAMPION_MAX_ROUNDS","FAILED","STOPPED"}:
            chip=f'<span class="cp-chip">{html.escape(opt_status)}</span>'
        else:
            chip='<span class="cp-chip">OPTIMIZER IDLE</span>'
    else:
        active=latest_factory_job(FACTORY_DIR,active_only=True)
        if active:
            ev=active.get("last_event") or {}; status=str(active.get("status") or "RUNNING"); stage=str(ev.get("stage") or active.get("action") or "RESEARCH").upper(); cycle=ev.get("orchestrator_cycle") or active.get("orchestrator_cycle") or "—"
            chip=f'<span class="cp-chip blue">{html.escape(status)}</span><span class="cp-chip">Cycle {html.escape(str(cycle))} · {html.escape(stage)}</span>'
        else:
            chip='<span class="cp-chip">IDLE</span>'
    st.markdown(f'<div class="cp-appbar"><div class="cp-top-left"><span class="cp-top-dot"></span><div><div class="cp-top-page">{html.escape(nav_page)}</div><div class="cp-top-context">Max Research Agent · ONNX Factory</div></div></div><div class="cp-shell-badges">{chip}</div></div>',unsafe_allow_html=True)
    _render_nav_page(nav_page,cfg)

    # Save acknowledgement is emitted only after the persistent write succeeds.
    current_digest=_config_digest(cfg)
    prior_digest=str(st.session_state.get("_last_saved_cfg_digest") or "")
    changed=current_digest!=prior_digest
    saved_ok=persist_user_settings()
    if saved_ok and changed:
        st.session_state._last_saved_cfg_digest=current_digest
        label="Data saved" if nav_page=="Data" else ("Settings saved" if nav_page=="Advanced" else "Changes saved")
        st.toast(label)
    elif not saved_ok:
        st.error("Settings save failed · "+str(st.session_state.get("settings_persist_error") or "unknown error"))

    if render_pending:
        if render_slot is not None: render_slot.empty()
        st.session_state.pop("_workspace_render_pending",None)
        st.toast(f"{nav_page} ready")


@st.fragment(run_every="1s", key="scientist")
def _scientist_fragment():
    with st.container(key="scientist_chat_restore"):
        st.button("‹",key="scientist_chat_restore_button",help="Show Scientist chat",use_container_width=True,on_click=_set_scientist_open,args=(True,))
    _render_scientist_chat(cfg)
    try: persist_user_settings()
    except Exception: pass


_shell_state_fragment()
_render_left_panel()
_workspace_fragment()
_scientist_fragment()
