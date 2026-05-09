"""
Personal Goal Progress Dashboard — Version 2.5
------------------------------------------------
A Streamlit goal, habit, progress diary, and execution-score dashboard.

Version 2.5 upgrades:
- Weekly/Monthly Review forms can optionally auto-create a Reflection habit log
- Auto-detects existing Weekly Strategic Reflection habit and reuses it

Version 2.4 upgrades:
- Weekly Reflection form and review table
- Monthly Review form and summary page
- Target vs Actual by Goal
- Edit/Delete Log controls
- Better goal setup fields: weekly target hours, success definition, review frequency, and role/context

Version 2.3 upgrades:
- Show goal/habit descriptions in goal table, goal detail, quick log, and status management views

Version 2.2 upgrades:
- Rich executive metric snapshot with separated Goals and Habits
- Goal effort, habit consistency, leverage quality, priority alignment, and attention-risk insights

Version 2.1 upgrades:
- Weekly Command Center
- Quick Log Form
- Priority vs Actual Effort chart
- Leverage Type field
- Next Best Action insight box
- Better filters, search, status management, archive action, duplicate last log

Storage modes:
1. Google Sheets mode when GOOGLE_SHEET_URL and [gcp_service_account] are present in secrets.toml
2. Local CSV fallback using ./data/goals.csv, ./data/logs.csv, ./data/milestones.csv
"""

from __future__ import annotations

import traceback
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

try:
    import gspread
    from google.oauth2.service_account import Credentials
except Exception:
    gspread = None
    Credentials = None


# -----------------------------------------------------------------------------
# Page setup
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="Personal Goal Progress Dashboard",
    page_icon="🎯",
    layout="wide",
)

APP_DIR = Path(__file__).resolve().parent
DATA_DIR = APP_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

GOALS_FILE = DATA_DIR / "goals.csv"
LOGS_FILE = DATA_DIR / "logs.csv"
MILESTONES_FILE = DATA_DIR / "milestones.csv"
WEEKLY_REFLECTIONS_FILE = DATA_DIR / "weekly_reflections.csv"
MONTHLY_REVIEWS_FILE = DATA_DIR / "monthly_reviews.csv"

GOALS_COLUMNS = [
    "goal_id", "type", "title", "category", "description", "status", "priority",
    "target_value", "target_unit", "weekly_target_hours", "success_definition", "review_frequency", "role_context",
    "start_date", "target_date", "created_at", "updated_at",
]

LOGS_COLUMNS = [
    "log_id", "goal_id", "log_date", "hours_spent", "quantity", "quantity_unit",
    "leverage_type", "progress_note", "achievement", "difficulty", "energy_level", "mood", "created_at",
]

MILESTONES_COLUMNS = [
    "milestone_id", "goal_id", "milestone_date", "milestone_title",
    "milestone_description", "impact_score", "created_at",
]

WEEKLY_REFLECTIONS_COLUMNS = [
    "reflection_id", "week_start", "what_i_built", "what_created_leverage",
    "what_distracted_me", "what_to_stop_doing", "next_best_action",
    "focus_score", "created_at",
]

MONTHLY_REVIEWS_COLUMNS = [
    "review_id", "month_start", "top_achievements", "best_leverage_activity",
    "biggest_distraction", "most_neglected_area", "what_to_double_down",
    "what_to_stop", "next_month_focus", "created_at",
]

CATEGORY_OPTIONS = [
    "Client Zero / AI Tools",
    "Career Leadership",
    "AI and Automation Capability",
    "Wealth and Assets",
    "Health and Energy",
    "Learning",
    "Japanese",
    "Reflection",
    "Other",
]

STATUS_OPTIONS = ["Active", "Inactive", "Archived"]
TYPE_OPTIONS = ["Goal", "Habit"]
PRIORITY_OPTIONS = ["High", "Medium", "Low"]
DIFFICULTY_OPTIONS = ["Easy", "Normal", "Hard"]
ENERGY_OPTIONS = ["Low", "Medium", "High"]
MOOD_OPTIONS = ["Poor", "Okay", "Good", "Great"]
LEVERAGE_TYPE_OPTIONS = [
    "Build Asset",
    "Improve System",
    "Solve Operational Problem",
    "Develop Capability",
    "Create Strategic Visibility",
    "Create Financial Leverage",
    "Protect Health & Energy",
    "Reflect & Reprioritize",
    "Maintenance / Admin",
]

EXECUTION_WEIGHTS = {
    "Client Zero / AI Tools": 30,
    "Career Leadership": 15,
    "Wealth and Assets": 15,
    "Health and Energy": 20,
    "Learning": 10,
    "Reflection": 10,
}

WEEKLY_TARGET_HOURS = {
    "Client Zero / AI Tools": 6.0,
    "Career Leadership": 1.0,
    "Wealth and Assets": 1.0,
    "Health and Energy": 3.0,
    "Learning": 2.5,
    "Reflection": 0.5,
}

HIGH_LEVERAGE_TYPES = {
    "Build Asset",
    "Improve System",
    "Solve Operational Problem",
    "Create Strategic Visibility",
    "Create Financial Leverage",
}


# -----------------------------------------------------------------------------
# Styling
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
        .block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            background: linear-gradient(180deg, #ffffff 0%, #f8fafc 100%);
            border: 1px solid #e5e7eb;
            padding: 14px 16px;
            border-radius: 18px;
            box-shadow: 0 1px 8px rgba(15,23,42,0.05);
        }
        .section-card {
            border: 1px solid #e5e7eb;
            border-radius: 18px;
            padding: 16px 18px;
            background: #ffffff;
            margin-bottom: 12px;
            box-shadow: 0 1px 8px rgba(15,23,42,0.04);
        }
        .small-muted {color: #64748b; font-size: 0.88rem;}
        .insight-box {
            border-left: 5px solid #f97316;
            padding: 10px 14px;
            background: #fff7ed;
            border-radius: 12px;
            margin-bottom: 8px;
        }
        .nba-box {
            border-left: 6px solid #2563eb;
            padding: 14px 16px;
            background: #eff6ff;
            border-radius: 14px;
            margin-bottom: 12px;
            font-size: 1.02rem;
        }
        .success-box {
            border-left: 6px solid #16a34a;
            padding: 12px 15px;
            background: #f0fdf4;
            border-radius: 14px;
            margin-bottom: 12px;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------
def now_ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def safe_to_date(value) -> Optional[date]:
    if pd.isna(value) or value == "":
        return None
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def month_start(d: date) -> date:
    return d.replace(day=1)


def ensure_csv(path: Path, columns: List[str], seed_rows: Optional[List[Dict]] = None) -> None:
    if not path.exists():
        pd.DataFrame(seed_rows or [], columns=columns).to_csv(path, index=False)
        return

    df = pd.read_csv(path)
    changed = False
    for col in columns:
        if col not in df.columns:
            df[col] = ""
            changed = True
    if changed:
        df[columns].to_csv(path, index=False)


def seed_data_if_missing() -> None:
    today = date.today()
    seed_goals = [
        {
            "goal_id": "goal_client_zero",
            "type": "Goal",
            "title": "Build Client Zero AI Tools",
            "category": "Client Zero / AI Tools",
            "description": "Build real dashboards, automations, and internal tools that create leverage.",
            "status": "Active",
            "priority": "High",
            "target_value": 300,
            "target_unit": "Hours",
            "weekly_target_hours": 6.0,
            "success_definition": "One serious operational tool or dashboard that creates real leverage.",
            "review_frequency": "Weekly",
            "role_context": "Builder / Client Zero",
            "start_date": str(today.replace(month=1, day=1)),
            "target_date": str(today.replace(month=12, day=31)),
            "created_at": now_ts(),
            "updated_at": now_ts(),
        },
        {
            "goal_id": "goal_ai_capability",
            "type": "Goal",
            "title": "Develop AI and Automation Capability",
            "category": "AI and Automation Capability",
            "description": "Improve Python, Pandas, SQL, Streamlit, APIs, agents, and practical automation skills.",
            "status": "Active",
            "priority": "High",
            "target_value": 150,
            "target_unit": "Hours",
            "weekly_target_hours": 2.5,
            "success_definition": "Practical AI and automation capability applied to real tools.",
            "review_frequency": "Weekly",
            "role_context": "Capability development",
            "start_date": str(today.replace(month=1, day=1)),
            "target_date": str(today.replace(month=12, day=31)),
            "created_at": now_ts(),
            "updated_at": now_ts(),
        },
        {
            "goal_id": "habit_health_energy",
            "type": "Habit",
            "title": "Protect Health and Energy",
            "category": "Health and Energy",
            "description": "Maintain energy through walking, running, sleep, and recovery.",
            "status": "Active",
            "priority": "High",
            "target_value": 156,
            "target_unit": "Sessions",
            "weekly_target_hours": 3.0,
            "success_definition": "Stable health, energy, walking/running, sleep, and recovery rhythm.",
            "review_frequency": "Weekly",
            "role_context": "Health foundation",
            "start_date": str(today.replace(month=1, day=1)),
            "target_date": str(today.replace(month=12, day=31)),
            "created_at": now_ts(),
            "updated_at": now_ts(),
        },
        {
            "goal_id": "habit_reflection",
            "type": "Habit",
            "title": "Weekly Strategic Reflection",
            "category": "Reflection",
            "description": "Review what created leverage, what distracted me, and what to focus on next.",
            "status": "Active",
            "priority": "High",
            "target_value": 26,
            "target_unit": "Hours",
            "weekly_target_hours": 0.5,
            "success_definition": "A weekly decision on what to focus on, stop, and build next.",
            "review_frequency": "Weekly",
            "role_context": "Strategic review",
            "start_date": str(today.replace(month=1, day=1)),
            "target_date": str(today.replace(month=12, day=31)),
            "created_at": now_ts(),
            "updated_at": now_ts(),
        },
    ]
    ensure_csv(GOALS_FILE, GOALS_COLUMNS, seed_goals)
    ensure_csv(LOGS_FILE, LOGS_COLUMNS, [])
    ensure_csv(MILESTONES_FILE, MILESTONES_COLUMNS, [])
    ensure_csv(WEEKLY_REFLECTIONS_FILE, WEEKLY_REFLECTIONS_COLUMNS, [])
    ensure_csv(MONTHLY_REVIEWS_FILE, MONTHLY_REVIEWS_COLUMNS, [])


def coerce_numeric(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df


def parse_dates(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    for col in cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# -----------------------------------------------------------------------------
# Storage layer: Local CSV or Google Sheets
# -----------------------------------------------------------------------------
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _secret_get(*path, default=None):
    try:
        value = st.secrets
        for key in path:
            value = value[key]
        return value
    except Exception:
        return default


def _format_exception(exc: Exception) -> str:
    message = str(exc).strip()
    exc_type = type(exc).__name__
    if message:
        return f"{exc_type}: {message}"
    return exc_type


def _normalise_service_account_info(info) -> dict:
    data = dict(info)
    private_key = data.get("private_key", "")
    if isinstance(private_key, str):
        data["private_key"] = private_key.replace("\\n", "\n")
    return data


def use_google_sheets() -> bool:
    explicit = _secret_get("goal_tracker", "use_google_sheets", default=None)
    if explicit is not None:
        return str(explicit).strip().lower() in {"true", "1", "yes", "on"}
    return bool(get_spreadsheet_url() and _secret_get("gcp_service_account", default=None))


def get_spreadsheet_url() -> Optional[str]:
    return _secret_get("GOOGLE_SHEET_URL", default=None) or _secret_get("goal_tracker", "spreadsheet_url", default=None)


@st.cache_resource(show_spinner=False)
def get_gspread_workbook():
    if gspread is None or Credentials is None:
        raise RuntimeError("Google packages are not installed. Run: pip install gspread google-auth")

    spreadsheet_url = get_spreadsheet_url()
    if not spreadsheet_url:
        raise RuntimeError("Missing GOOGLE_SHEET_URL or goal_tracker.spreadsheet_url in secrets.toml")

    service_account_info = _secret_get("gcp_service_account", default=None)
    if not service_account_info:
        raise RuntimeError("Missing [gcp_service_account] block in secrets.toml")

    credentials = Credentials.from_service_account_info(
        _normalise_service_account_info(service_account_info),
        scopes=GOOGLE_SCOPES,
    )
    client = gspread.authorize(credentials)
    return client.open_by_url(spreadsheet_url)


def get_or_create_worksheet(name: str, columns: List[str]):
    workbook = get_gspread_workbook()
    try:
        worksheet = workbook.worksheet(name)
    except Exception:
        worksheet = workbook.add_worksheet(title=name, rows=1000, cols=max(len(columns), 10))
        worksheet.update([columns], value_input_option="USER_ENTERED")
        return worksheet

    header = worksheet.row_values(1)
    if not header:
        worksheet.update([columns], value_input_option="USER_ENTERED")
    else:
        missing = [col for col in columns if col not in header]
        if missing:
            new_header = header + missing
            worksheet.update("1:1", [new_header], value_input_option="USER_ENTERED")
    return worksheet


def read_google_sheet_table(name: str, columns: List[str]) -> pd.DataFrame:
    worksheet = get_or_create_worksheet(name, columns)
    records = worksheet.get_all_records()
    if not records:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(records)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def write_google_sheet_table(name: str, df: pd.DataFrame, columns: List[str]) -> None:
    worksheet = get_or_create_worksheet(name, columns)

    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns].fillna("")

    values = [columns] + df.astype(str).values.tolist()
    worksheet.clear()
    worksheet.update(values, value_input_option="USER_ENTERED")
    st.cache_data.clear()


def read_table(name: str, columns: List[str]) -> pd.DataFrame:
    seed_data_if_missing()

    if use_google_sheets():
        try:
            return read_google_sheet_table(name, columns)
        except Exception as exc:
            st.warning(f"Could not read Google worksheet '{name}'. Using local CSV instead. Detail: {_format_exception(exc)}")
            with st.expander(f"Google Sheets debug for '{name}'", expanded=False):
                st.code(traceback.format_exc())

    path = DATA_DIR / f"{name}.csv"
    ensure_csv(path, columns, [])
    df = pd.read_csv(path)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df[columns]


def write_table(name: str, df: pd.DataFrame, columns: List[str]) -> None:
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns]

    if use_google_sheets():
        try:
            write_google_sheet_table(name, df, columns)
            return
        except Exception as exc:
            st.warning(f"Could not update Google worksheet '{name}'. Saving to local CSV instead. Detail: {_format_exception(exc)}")
            with st.expander(f"Google Sheets write debug for '{name}'", expanded=False):
                st.code(traceback.format_exc())

    path = DATA_DIR / f"{name}.csv"
    df.to_csv(path, index=False)
    st.cache_data.clear()


@st.cache_data(ttl=10)
def load_data() -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    goals = read_table("goals", GOALS_COLUMNS)
    logs = read_table("logs", LOGS_COLUMNS)
    milestones = read_table("milestones", MILESTONES_COLUMNS)
    weekly_reflections = read_table("weekly_reflections", WEEKLY_REFLECTIONS_COLUMNS)
    monthly_reviews = read_table("monthly_reviews", MONTHLY_REVIEWS_COLUMNS)

    goals = coerce_numeric(goals, ["target_value", "weekly_target_hours"])
    goals = parse_dates(goals, ["start_date", "target_date", "created_at", "updated_at"])

    logs = coerce_numeric(logs, ["hours_spent", "quantity"])
    logs = parse_dates(logs, ["log_date", "created_at"])
    logs["leverage_type"] = logs.get("leverage_type", "").replace("", "Maintenance / Admin")
    logs["leverage_type"] = logs["leverage_type"].replace("Maintenance Only", "Maintenance / Admin")

    milestones = coerce_numeric(milestones, ["impact_score"])
    milestones = parse_dates(milestones, ["milestone_date", "created_at"])

    weekly_reflections = coerce_numeric(weekly_reflections, ["focus_score"])
    weekly_reflections = parse_dates(weekly_reflections, ["week_start", "created_at"])

    monthly_reviews = parse_dates(monthly_reviews, ["month_start", "created_at"])
    return goals, logs, milestones, weekly_reflections, monthly_reviews


def clear_and_rerun(message: str):
    st.cache_data.clear()
    st.success(message)
    st.rerun()


# -----------------------------------------------------------------------------
# Diagnostics and auth
# -----------------------------------------------------------------------------
def render_google_sheets_diagnostics() -> None:
    with st.sidebar.expander("Google Sheets connection", expanded=False):
        st.write(f"Google Sheets mode: `{use_google_sheets()}`")
        st.write(f"GOOGLE_SHEET_URL present: `{bool(get_spreadsheet_url())}`")
        svc = _secret_get("gcp_service_account", default=None)
        st.write(f"Service account block present: `{bool(svc)}`")
        if svc:
            st.write(f"Service account email: `{dict(svc).get('client_email', 'Not found')}`")

        if st.button("Test Google Sheets connection", width='stretch'):
            try:
                workbook = get_gspread_workbook()
                worksheet_titles = [ws.title for ws in workbook.worksheets()]
                st.success("Google Sheets connection successful.")
                st.write("Worksheets:", worksheet_titles)
            except Exception as exc:
                st.error(f"Google Sheets connection failed: {_format_exception(exc)}")
                st.code(traceback.format_exc())


def check_password() -> bool:
    expected_user = _secret_get("APP_USERNAME", default="admin")
    expected_pass = _secret_get("APP_PASSWORD", default="change-me")

    if st.session_state.get("goal_tracker_authenticated"):
        with st.sidebar:
            st.success("Authenticated")
            if st.button("Log out", width='stretch'):
                st.session_state["goal_tracker_authenticated"] = False
                st.rerun()
        return True

    st.title("🔐 Personal Goal Progress Dashboard")
    st.caption("Login required before viewing or editing your goal data.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary")

    if submitted:
        if username == expected_user and password == expected_pass:
            st.session_state["goal_tracker_authenticated"] = True
            st.rerun()
        else:
            st.error("Invalid username or password.")

    with st.expander("First-time local demo login"):
        st.info("Default demo login is username `admin` and password `change-me`. Change this in Streamlit secrets before real use.")
    return False


# -----------------------------------------------------------------------------
# Calculations
# -----------------------------------------------------------------------------
def active_goals(goals: pd.DataFrame) -> pd.DataFrame:
    return goals[goals["status"].astype(str).str.lower() == "active"].copy()


def logs_with_goal_info(goals: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    if logs.empty:
        return pd.DataFrame(columns=list(logs.columns) + ["title", "category", "priority", "status", "type"])
    info_cols = ["goal_id", "title", "category", "priority", "status", "type"]
    return logs.merge(goals[info_cols], on="goal_id", how="left")


def enrich_goals(goals: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    df = goals.copy()
    if df.empty:
        return df

    today = date.today()
    ws = week_start(today)
    ms = month_start(today)

    logs_valid = logs.dropna(subset=["goal_id", "log_date"]).copy()
    if logs_valid.empty:
        df["hours_this_week"] = 0.0
        df["hours_this_month"] = 0.0
        df["hours_all_time"] = 0.0
        df["last_logged_date"] = pd.NaT
        df["total_logs"] = 0
        df["days_since_last_log"] = None
        df["progress_pct"] = None
        return df

    logs_valid["log_day"] = logs_valid["log_date"].dt.date

    def sum_hours(goal_id: str, start: Optional[date] = None) -> float:
        sub = logs_valid[logs_valid["goal_id"] == goal_id]
        if start is not None:
            sub = sub[sub["log_day"] >= start]
        return float(sub["hours_spent"].sum())

    def last_log(goal_id: str):
        sub = logs_valid[logs_valid["goal_id"] == goal_id]
        if sub.empty:
            return pd.NaT
        return sub["log_date"].max()

    def total_logs(goal_id: str) -> int:
        return int((logs_valid["goal_id"] == goal_id).sum())

    df["hours_this_week"] = df["goal_id"].apply(lambda x: sum_hours(x, ws))
    df["hours_this_month"] = df["goal_id"].apply(lambda x: sum_hours(x, ms))
    df["hours_all_time"] = df["goal_id"].apply(lambda x: sum_hours(x, None))
    df["last_logged_date"] = df["goal_id"].apply(last_log)
    df["total_logs"] = df["goal_id"].apply(total_logs)
    df["days_since_last_log"] = df["last_logged_date"].apply(lambda x: None if pd.isna(x) else (today - x.date()).days)
    df["progress_pct"] = df.apply(
        lambda r: min(100.0, (float(r["hours_all_time"]) / float(r["target_value"]) * 100))
        if str(r.get("target_unit", "")) == "Hours" and float(r.get("target_value", 0) or 0) > 0 else None,
        axis=1,
    )
    return df


def calculate_execution_score(goals: pd.DataFrame, logs: pd.DataFrame) -> Tuple[float, pd.DataFrame]:
    today = date.today()
    ws = week_start(today)
    logs_week = logs.copy().dropna(subset=["log_date"])
    logs_week = logs_week[logs_week["log_date"].dt.date >= ws]
    merged = logs_with_goal_info(goals, logs_week)

    rows = []
    total_score = 0.0
    for category, weight in EXECUTION_WEIGHTS.items():
        target = WEEKLY_TARGET_HOURS.get(category, 1.0)
        actual = float(merged.loc[merged["category"] == category, "hours_spent"].sum()) if not merged.empty else 0.0
        achievement = min(actual / target, 1.0) if target > 0 else 0
        score = achievement * weight
        total_score += score
        rows.append({
            "Category": category,
            "Weight": weight,
            "Weekly Target Hours": target,
            "Actual Hours This Week": actual,
            "Achievement %": round(achievement * 100, 1),
            "Score": round(score, 1),
        })
    return round(total_score, 1), pd.DataFrame(rows)


def get_current_week_logs(goals: pd.DataFrame, logs: pd.DataFrame) -> pd.DataFrame:
    today = date.today()
    ws = week_start(today)
    logs_week = logs.dropna(subset=["log_date"]).copy()
    logs_week = logs_week[logs_week["log_date"].dt.date >= ws]
    return logs_with_goal_info(goals, logs_week)


def next_best_action(goals: pd.DataFrame, logs: pd.DataFrame, enriched: pd.DataFrame) -> str:
    score, score_df = calculate_execution_score(goals, logs)
    active = enriched[enriched["status"] == "Active"].copy() if not enriched.empty else pd.DataFrame()

    if active.empty:
        return "Create or reactivate one important goal. Without an active goal, the dashboard cannot guide your execution."

    client_row = score_df[score_df["Category"] == "Client Zero / AI Tools"]
    if not client_row.empty and float(client_row.iloc[0]["Actual Hours This Week"]) < 5:
        return "Book one 90-minute Client Zero build session. This is your highest-leverage category and it is still below the weekly target."

    reflection_row = score_df[score_df["Category"] == "Reflection"]
    if not reflection_row.empty and float(reflection_row.iloc[0]["Actual Hours This Week"]) <= 0:
        return "Complete a 30-minute weekly reflection. The point is to check what created leverage, what distracted you, and what to focus on next."

    wealth_row = score_df[score_df["Category"] == "Wealth and Assets"]
    if not wealth_row.empty and float(wealth_row.iloc[0]["Actual Hours This Week"]) <= 0:
        return "Do one small wealth action this week: update net worth, review debt, check investment contribution, or record property/rental progress."

    health_row = score_df[score_df["Category"] == "Health and Energy"]
    if not health_row.empty and float(health_row.iloc[0]["Actual Hours This Week"]) < 1.5:
        return "Protect your energy: log at least one health action this week, such as walking, running, strength training, or sleep recovery."

    stale = active.dropna(subset=["days_since_last_log"]).sort_values("days_since_last_log", ascending=False)
    stale_high = stale[(stale["priority"] == "High") & (stale["days_since_last_log"] >= 14)]
    if not stale_high.empty:
        g = stale_high.iloc[0]
        return f"Restart or archive '{g['title']}'. It is high priority but has not been logged for {int(g['days_since_last_log'])} days."

    if score >= 80:
        return "You are executing well this week. Keep momentum and choose one meaningful milestone to document as evidence."

    lowest = score_df.sort_values("Score", ascending=True).iloc[0]
    return f"Focus on {lowest['Category']} next. It has the weakest score against your weekly execution model."


def make_insights(enriched: pd.DataFrame, goals: pd.DataFrame, logs: pd.DataFrame) -> List[str]:
    insights: List[str] = []
    if goals.empty:
        return ["Add your first goal to start building your execution evidence system."]

    active = enriched[enriched["status"] == "Active"].copy()
    if active.empty:
        return ["You currently have no active goals. Move one goal to Active to start tracking execution."]

    top_month = active.sort_values("hours_this_month", ascending=False).head(1)
    if not top_month.empty and float(top_month.iloc[0]["hours_this_month"]) > 0:
        insights.append(
            f"Your highest-effort area this month is '{top_month.iloc[0]['title']}' with {top_month.iloc[0]['hours_this_month']:.1f} hours."
        )

    score, _ = calculate_execution_score(goals, logs)
    insights.append(f"Your current weekly execution score is {score}/100.")

    stale = active.dropna(subset=["days_since_last_log"]).copy()
    stale = stale[stale["days_since_last_log"] >= 7].sort_values("days_since_last_log", ascending=False)
    if not stale.empty:
        r = stale.iloc[0]
        insights.append(f"'{r['title']}' has not been logged for {int(r['days_since_last_log'])} days. Decide whether to restart, reduce, or archive it.")

    merged = logs_with_goal_info(goals, logs.dropna(subset=["log_date"]))
    if not merged.empty and "leverage_type" in merged.columns:
        high_lev_hours = float(merged.loc[merged["leverage_type"].isin(HIGH_LEVERAGE_TYPES), "hours_spent"].sum())
        total_hours = float(merged["hours_spent"].sum())
        if total_hours > 0:
            insights.append(f"{high_lev_hours / total_hours:.0%} of your logged time is currently high-leverage work.")

    if not insights:
        insights.append("Start logging progress. The dashboard becomes useful once it has a few entries.")
    return insights


def priority_vs_effort_data(goals: pd.DataFrame, logs: pd.DataFrame, start: date, end: date) -> pd.DataFrame:
    categories = list(EXECUTION_WEIGHTS.keys())
    weight_total = sum(EXECUTION_WEIGHTS.values())
    base = pd.DataFrame({
        "Category": categories,
        "Priority Weight %": [EXECUTION_WEIGHTS[c] / weight_total * 100 for c in categories],
    })

    logs_range = logs.dropna(subset=["log_date"]).copy()
    logs_range = logs_range[(logs_range["log_date"].dt.date >= start) & (logs_range["log_date"].dt.date <= end)]
    merged = logs_with_goal_info(goals, logs_range)
    by_cat = merged.groupby("category", as_index=False)["hours_spent"].sum().rename(columns={"category": "Category"}) if not merged.empty else pd.DataFrame(columns=["Category", "hours_spent"])

    out = base.merge(by_cat, on="Category", how="left")
    out["hours_spent"] = out["hours_spent"].fillna(0.0)
    total_hours = float(out["hours_spent"].sum())
    out["Actual Effort %"] = out["hours_spent"] / total_hours * 100 if total_hours > 0 else 0.0
    out["Gap %"] = out["Actual Effort %"] - out["Priority Weight %"]
    return out


# -----------------------------------------------------------------------------
# UI helpers
# -----------------------------------------------------------------------------
def period_logs(logs: pd.DataFrame, start: Optional[date] = None, end: Optional[date] = None) -> pd.DataFrame:
    logs_valid = logs.dropna(subset=["log_date"]).copy()
    if logs_valid.empty:
        return logs_valid
    if start is not None:
        logs_valid = logs_valid[logs_valid["log_date"].dt.date >= start]
    if end is not None:
        logs_valid = logs_valid[logs_valid["log_date"].dt.date <= end]
    return logs_valid


def safe_sum_hours(df: pd.DataFrame) -> float:
    if df.empty or "hours_spent" not in df.columns:
        return 0.0
    return float(pd.to_numeric(df["hours_spent"], errors="coerce").fillna(0).sum())


def top_item_label(df: pd.DataFrame, group_col: str, value_col: str = "hours_spent", fallback: str = "No activity yet") -> str:
    if df.empty or group_col not in df.columns or value_col not in df.columns:
        return fallback
    grouped = df.groupby(group_col, as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
    if grouped.empty or float(grouped.iloc[0][value_col]) <= 0:
        return fallback
    return f"{grouped.iloc[0][group_col]} ({float(grouped.iloc[0][value_col]):.1f} h)"


def render_metric_insight_cards(enriched: pd.DataFrame, logs: pd.DataFrame) -> None:
    today = date.today()
    ws = week_start(today)
    logs_week = period_logs(logs, ws, today)
    merged_week = logs_with_goal_info(enriched, logs_week) if not logs_week.empty else pd.DataFrame()

    week_hours = safe_sum_hours(logs_week)
    days_active = logs_week["log_date"].dt.date.nunique() if not logs_week.empty else 0
    consistency_pct = days_active / 7 if days_active else 0

    high_priority_ids = set(enriched.loc[(enriched["status"] == "Active") & (enriched["priority"] == "High"), "goal_id"]) if not enriched.empty else set()
    high_priority_week_hours = safe_sum_hours(logs_week[logs_week["goal_id"].isin(high_priority_ids)]) if not logs_week.empty else 0.0
    high_priority_share = high_priority_week_hours / week_hours if week_hours > 0 else 0

    high_lev_share = 0.0
    if not logs_week.empty and "leverage_type" in logs_week.columns:
        high_lev_hours = safe_sum_hours(logs_week[logs_week["leverage_type"].isin(HIGH_LEVERAGE_TYPES)])
        high_lev_share = high_lev_hours / week_hours if week_hours > 0 else 0

    stale_high = pd.DataFrame()
    if not enriched.empty and "days_since_last_log" in enriched.columns:
        stale_high = enriched[
            (enriched["status"] == "Active")
            & (enriched["priority"] == "High")
            & (enriched["days_since_last_log"].fillna(9999) >= 7)
        ].sort_values("days_since_last_log", ascending=False)

    top_category = top_item_label(merged_week, "category") if not merged_week.empty else "No activity yet"

    def status_word(value: float, good: float, okay: float) -> str:
        if value >= good:
            return "Strong"
        if value >= okay:
            return "Watch"
        return "Weak"

    alignment_status = status_word(high_priority_share, 0.65, 0.40)
    leverage_status = status_word(high_lev_share, 0.55, 0.30)
    consistency_status = status_word(consistency_pct, 0.57, 0.29)  # 4 days / 2 days

    st.markdown("#### What the numbers are telling you")
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(f"""<div class='section-card'><b>Priority Alignment</b><br><span style='font-size:1.6rem'>{alignment_status}</span><br><span class='small-muted'>{high_priority_share:.0%} of this week's time went to High priority items.</span></div>""", unsafe_allow_html=True)
    c2.markdown(f"""<div class='section-card'><b>Leverage Quality</b><br><span style='font-size:1.6rem'>{leverage_status}</span><br><span class='small-muted'>{high_lev_share:.0%} of this week's time was high-leverage work.</span></div>""", unsafe_allow_html=True)
    c3.markdown(f"""<div class='section-card'><b>Consistency</b><br><span style='font-size:1.6rem'>{consistency_status}</span><br><span class='small-muted'>You logged progress on {days_active}/7 days this week.</span></div>""", unsafe_allow_html=True)
    c4.markdown(f"""<div class='section-card'><b>Focus Area</b><br><span style='font-size:1.05rem'>{top_category}</span><br><span class='small-muted'>{len(stale_high)} high-priority item(s) need attention.</span></div>""", unsafe_allow_html=True)


def metric_row(enriched: pd.DataFrame, logs: pd.DataFrame) -> None:
    today = date.today()
    ws = week_start(today)
    ms = month_start(today)

    logs_week = period_logs(logs, ws, today)
    logs_month = period_logs(logs, ms, today)
    logs_all = period_logs(logs)

    merged_week = logs_with_goal_info(enriched, logs_week) if not logs_week.empty else pd.DataFrame()
    merged_month = logs_with_goal_info(enriched, logs_month) if not logs_month.empty else pd.DataFrame()
    merged_all = logs_with_goal_info(enriched, logs_all) if not logs_all.empty else pd.DataFrame()

    goals_active = enriched[(enriched["status"] == "Active") & (enriched["type"] == "Goal")] if not enriched.empty else pd.DataFrame()
    habits_active = enriched[(enriched["status"] == "Active") & (enriched["type"] == "Habit")] if not enriched.empty else pd.DataFrame()

    goal_week_hours = safe_sum_hours(merged_week[merged_week["type"] == "Goal"]) if not merged_week.empty else 0.0
    goal_month_hours = safe_sum_hours(merged_month[merged_month["type"] == "Goal"]) if not merged_month.empty else 0.0
    goal_all_hours = safe_sum_hours(merged_all[merged_all["type"] == "Goal"]) if not merged_all.empty else 0.0

    habit_week_hours = safe_sum_hours(merged_week[merged_week["type"] == "Habit"]) if not merged_week.empty else 0.0
    habit_month_hours = safe_sum_hours(merged_month[merged_month["type"] == "Habit"]) if not merged_month.empty else 0.0
    habit_all_hours = safe_sum_hours(merged_all[merged_all["type"] == "Habit"]) if not merged_all.empty else 0.0

    score, _ = calculate_execution_score(enriched, logs)
    total_week_hours = safe_sum_hours(logs_week)
    total_month_hours = safe_sum_hours(logs_month)
    total_all_hours = safe_sum_hours(logs_all)

    last_log_date = "No log yet"
    if not logs_all.empty:
        last_log_date = str(logs_all["log_date"].max().date())

    habit_days_this_week = 0
    if not merged_week.empty:
        habit_days_this_week = merged_week[merged_week["type"] == "Habit"]["log_date"].dt.date.nunique()

    stale_goals = int((goals_active["days_since_last_log"].fillna(9999) >= 7).sum()) if not goals_active.empty and "days_since_last_log" in goals_active.columns else 0
    stale_habits = int((habits_active["days_since_last_log"].fillna(9999) >= 7).sum()) if not habits_active.empty and "days_since_last_log" in habits_active.columns else 0

    high_leverage_hours = 0.0
    if not logs_week.empty and "leverage_type" in logs_week.columns:
        high_leverage_hours = safe_sum_hours(logs_week[logs_week["leverage_type"].isin(HIGH_LEVERAGE_TYPES)])
    high_leverage_share = high_leverage_hours / total_week_hours if total_week_hours > 0 else 0.0

    st.markdown("### Executive Snapshot")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Execution Score", f"{score}/100")
    c2.metric("This Week", f"{total_week_hours:.1f} h")
    c3.metric("This Month", f"{total_month_hours:.1f} h")
    c4.metric("All Time", f"{total_all_hours:.1f} h")
    c5.metric("Last Log", last_log_date)

    st.markdown("### Goals")
    g1, g2, g3, g4, g5 = st.columns(5)
    g1.metric("Active Goals", len(goals_active))
    g2.metric("Goal Hours This Week", f"{goal_week_hours:.1f} h")
    g3.metric("Goal Hours This Month", f"{goal_month_hours:.1f} h")
    g4.metric("Goal Hours All Time", f"{goal_all_hours:.1f} h")
    g5.metric("Goals Needing Attention", stale_goals)

    st.markdown("### Habits")
    h1, h2, h3, h4, h5 = st.columns(5)
    h1.metric("Active Habits", len(habits_active))
    h2.metric("Habit Hours This Week", f"{habit_week_hours:.1f} h")
    h3.metric("Habit Hours This Month", f"{habit_month_hours:.1f} h")
    h4.metric("Habit Days This Week", f"{habit_days_this_week}/7")
    h5.metric("Habits Needing Attention", stale_habits)

    st.markdown("### Quality of Effort")
    q1, q2, q3, q4 = st.columns(4)
    q1.metric("High-Leverage Time", f"{high_leverage_share:.0%}", f"{high_leverage_hours:.1f} h this week")
    q2.metric("Top Goal / Habit", top_item_label(merged_week, "title"))
    q3.metric("Top Category", top_item_label(merged_week, "category"))
    q4.metric("Goal vs Habit Split", f"{goal_week_hours:.1f}h / {habit_week_hours:.1f}h")

    render_metric_insight_cards(enriched, logs)


def sidebar_filters(enriched: pd.DataFrame) -> Dict:
    st.sidebar.header("Filters")
    status = st.sidebar.multiselect("Status", STATUS_OPTIONS, default=["Active"])
    type_filter = st.sidebar.multiselect("Type", TYPE_OPTIONS, default=TYPE_OPTIONS)
    categories = sorted(enriched["category"].dropna().unique().tolist()) if not enriched.empty else CATEGORY_OPTIONS
    category = st.sidebar.multiselect("Category", categories, default=categories)
    priority = st.sidebar.multiselect("Priority", PRIORITY_OPTIONS, default=PRIORITY_OPTIONS)
    search = st.sidebar.text_input("Search goal / habit")

    today = date.today()
    preset = st.sidebar.selectbox("Date range preset", ["This week", "This month", "Last 30 days", "This quarter", "This year", "Custom"], index=1)
    if preset == "This week":
        start_date = week_start(today)
        end_date = today
    elif preset == "This month":
        start_date = month_start(today)
        end_date = today
    elif preset == "Last 30 days":
        start_date = today - timedelta(days=30)
        end_date = today
    elif preset == "This quarter":
        quarter_month = ((today.month - 1) // 3) * 3 + 1
        start_date = today.replace(month=quarter_month, day=1)
        end_date = today
    elif preset == "This year":
        start_date = today.replace(month=1, day=1)
        end_date = today
    else:
        start_date = st.sidebar.date_input("Start date", today - timedelta(days=30))
        end_date = st.sidebar.date_input("End date", today)

    return {
        "status": status,
        "type": type_filter,
        "category": category,
        "priority": priority,
        "search": search,
        "start_date": start_date,
        "end_date": end_date,
    }


def apply_goal_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        return out
    if filters["status"]:
        out = out[out["status"].isin(filters["status"])]
    if filters["type"]:
        out = out[out["type"].isin(filters["type"])]
    if filters["category"]:
        out = out[out["category"].isin(filters["category"])]
    if filters["priority"]:
        out = out[out["priority"].isin(filters["priority"])]
    search = str(filters.get("search", "")).strip().lower()
    if search:
        out = out[out["title"].astype(str).str.lower().str.contains(search, na=False) | out["description"].astype(str).str.lower().str.contains(search, na=False)]
    return out


def filter_logs_by_date(logs: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    logs_filtered = logs.dropna(subset=["log_date"]).copy()
    if logs_filtered.empty:
        return logs_filtered
    start = filters["start_date"]
    end = filters["end_date"]
    return logs_filtered[(logs_filtered["log_date"].dt.date >= start) & (logs_filtered["log_date"].dt.date <= end)]


def goal_options_dict(goals: pd.DataFrame, active_only: bool = False) -> Dict[str, str]:
    df = goals.copy()
    if active_only:
        df = df[df["status"] == "Active"]
    df = df.sort_values(["priority", "title"], ascending=[True, True])
    return {f"{r['title']} — {r['category']}": r["goal_id"] for _, r in df.iterrows()}


def reflection_habit_options(goals: pd.DataFrame, review_type: str = "weekly") -> Dict[str, str]:
    """Return Reflection habit options, prioritising weekly/monthly review habits.

    This lets the review form create a normal habit log without requiring duplicate manual entry.
    """
    if goals.empty:
        return {}

    df = goals.copy()
    for col in ["type", "category", "status", "title"]:
        if col not in df.columns:
            df[col] = ""

    df["_title_l"] = df["title"].astype(str).str.lower()
    df["_category_l"] = df["category"].astype(str).str.lower()
    df["_type_l"] = df["type"].astype(str).str.lower()
    df["_status_l"] = df["status"].astype(str).str.lower()

    reflection = df[(df["_type_l"] == "habit") & (df["_category_l"] == "reflection")].copy()
    if reflection.empty:
        reflection = df[df["_category_l"] == "reflection"].copy()
    if reflection.empty:
        return {}

    keyword = "monthly" if review_type == "monthly" else "weekly"
    reflection["_sort"] = 50
    reflection.loc[reflection["_status_l"] == "active", "_sort"] -= 20
    reflection.loc[reflection["_title_l"].str.contains(keyword, na=False), "_sort"] -= 20
    reflection.loc[reflection["_title_l"].str.contains("strategic", na=False), "_sort"] -= 5
    reflection.loc[reflection["_title_l"].str.contains("reflection", na=False), "_sort"] -= 5
    reflection = reflection.sort_values(["_sort", "title"])

    return {f"{r['title']} — {r['category']}": r["goal_id"] for _, r in reflection.iterrows()}


def build_review_habit_log_row(goal_id: str, log_date: date, hours_spent: float, review_type: str, summary: str) -> Dict:
    review_label = "Monthly Review" if review_type == "monthly" else "Weekly Review"
    return create_log_row(
        goal_id=goal_id,
        log_date=log_date,
        hours_spent=hours_spent,
        quantity=1,
        quantity_unit="Review",
        leverage_type="Reflect & Reprioritize",
        progress_note=summary,
        achievement=f"Completed {review_label}",
        difficulty="Normal",
        energy_level="Medium",
        mood="Good",
    )


def has_review_habit_log_for_period(goals: pd.DataFrame, logs: pd.DataFrame, review_type: str, period_start: date) -> bool:
    """Detect whether a review habit log already exists for the selected week/month."""
    if logs.empty:
        return False

    options = set(reflection_habit_options(goals, review_type=review_type).values())
    if not options:
        return False

    logs_valid = logs.dropna(subset=["log_date"]).copy()
    if logs_valid.empty:
        return False

    logs_valid["log_day"] = logs_valid["log_date"].dt.date
    logs_valid = logs_valid[logs_valid["goal_id"].isin(options)]

    if review_type == "monthly":
        return not logs_valid[
            (logs_valid["log_day"] >= period_start)
            & (logs_valid["log_day"] < (period_start + pd.DateOffset(months=1)).date())
        ].empty

    return not logs_valid[
        (logs_valid["log_day"] >= period_start)
        & (logs_valid["log_day"] <= period_start + timedelta(days=6))
    ].empty


def get_goal_weekly_target(goal_row: pd.Series) -> float:
    """Use goal-level weekly target when available; otherwise fall back to category defaults."""
    try:
        target = float(goal_row.get("weekly_target_hours", 0) or 0)
        if target > 0:
            return target
    except Exception:
        pass
    return float(WEEKLY_TARGET_HOURS.get(str(goal_row.get("category", "")), 0.0))


def active_week_range() -> Tuple[date, date]:
    today = date.today()
    return week_start(today), today


def current_month_range() -> Tuple[date, date]:
    today = date.today()
    return month_start(today), today


def log_selector_labels(goals: pd.DataFrame, logs: pd.DataFrame) -> Dict[str, str]:
    if logs.empty:
        return {}
    merged = logs_with_goal_info(goals, logs).copy()
    merged = merged.dropna(subset=["log_date"]).sort_values("log_date", ascending=False)
    labels = {}
    for _, r in merged.head(200).iterrows():
        log_id = str(r.get("log_id", ""))
        if not log_id:
            continue
        label = f"{r['log_date'].date()} | {r.get('title', 'Unknown')} | {float(r.get('hours_spent', 0) or 0):.2f}h | {str(r.get('achievement', '') or '')[:45]}"
        labels[label] = log_id
    return labels


# -----------------------------------------------------------------------------
# Forms and actions
# -----------------------------------------------------------------------------
def create_log_row(goal_id: str, log_date: date, hours_spent: float, quantity: float, quantity_unit: str,
                   leverage_type: str, progress_note: str, achievement: str, difficulty: str,
                   energy_level: str, mood: str) -> Dict:
    return {
        "log_id": new_id("log"),
        "goal_id": goal_id,
        "log_date": str(log_date),
        "hours_spent": hours_spent,
        "quantity": quantity,
        "quantity_unit": quantity_unit,
        "leverage_type": leverage_type,
        "progress_note": progress_note,
        "achievement": achievement,
        "difficulty": difficulty,
        "energy_level": energy_level,
        "mood": mood,
        "created_at": now_ts(),
    }


def quick_log_form(goals: pd.DataFrame, logs: pd.DataFrame, location: str = "main") -> None:
    st.markdown("#### ⚡ Quick Log")
    goal_options = goal_options_dict(goals, active_only=True)
    if not goal_options:
        st.info("Add or reactivate a goal before logging progress.")
        return

    form_key = f"quick_log_{location}"
    with st.form(form_key, clear_on_submit=True):
        c1, c2, c3 = st.columns([2.2, 0.8, 1.2])
        selected_label = c1.selectbox("Goal / habit", list(goal_options.keys()), key=f"quick_goal_{location}")
        selected_goal_id = goal_options[selected_label]
        selected_goal_row = goals[goals["goal_id"] == selected_goal_id]
        if not selected_goal_row.empty:
            description = str(selected_goal_row.iloc[0].get("description", "") or "").strip()
            if description:
                c1.caption(f"Purpose: {description}")
        hours_spent = c2.number_input("Hours", min_value=0.0, max_value=24.0, value=1.0, step=0.25, key=f"quick_hours_{location}")
        leverage_type = c3.selectbox("Leverage type", LEVERAGE_TYPE_OPTIONS, index=0, key=f"quick_lev_{location}")
        achievement = st.text_input("What did you achieve?", placeholder="Example: Added Google Sheets writeback and tested logging")
        submitted = st.form_submit_button("Save Quick Log", type="primary", width='stretch')

    if submitted:
        new_row = create_log_row(
            goal_id=goal_options[selected_label],
            log_date=date.today(),
            hours_spent=hours_spent,
            quantity=0,
            quantity_unit="",
            leverage_type=leverage_type,
            progress_note="",
            achievement=achievement,
            difficulty="Normal",
            energy_level="Medium",
            mood="Good",
        )
        updated = pd.concat([logs, pd.DataFrame([new_row])], ignore_index=True)
        write_table("logs", updated, LOGS_COLUMNS)
        clear_and_rerun("Quick log saved successfully.")

    with st.expander("Duplicate last log", expanded=False):
        if logs.dropna(subset=["log_date"]).empty:
            st.caption("No previous log to duplicate yet.")
        else:
            merged = logs_with_goal_info(goals, logs).dropna(subset=["log_date"]).sort_values("log_date", ascending=False)
            last = merged.iloc[0]
            st.caption(f"Last log: {last.get('title', 'Unknown')} | {last['hours_spent']}h | {last.get('leverage_type', '')}")
            if st.button("Duplicate last log for today", width='stretch', key=f"dup_last_{location}"):
                new_row = create_log_row(
                    goal_id=last["goal_id"],
                    log_date=date.today(),
                    hours_spent=float(last.get("hours_spent", 0) or 0),
                    quantity=float(last.get("quantity", 0) or 0),
                    quantity_unit=str(last.get("quantity_unit", "") or ""),
                    leverage_type=str(last.get("leverage_type", "Maintenance / Admin") or "Maintenance / Admin"),
                    progress_note=str(last.get("progress_note", "") or ""),
                    achievement=str(last.get("achievement", "") or ""),
                    difficulty=str(last.get("difficulty", "Normal") or "Normal"),
                    energy_level=str(last.get("energy_level", "Medium") or "Medium"),
                    mood=str(last.get("mood", "Good") or "Good"),
                )
                updated = pd.concat([logs, pd.DataFrame([new_row])], ignore_index=True)
                write_table("logs", updated, LOGS_COLUMNS)
                clear_and_rerun("Last log duplicated for today.")


def log_progress_form(goals: pd.DataFrame, logs: pd.DataFrame) -> None:
    st.subheader("📝 Detailed Progress Log")
    goal_options = goal_options_dict(goals, active_only=True)
    if not goal_options:
        st.info("Add or reactivate a goal before logging progress.")
        return

    with st.form("log_progress_form", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        selected_label = c1.selectbox("Goal / Habit", list(goal_options.keys()))
        selected_goal_id = goal_options[selected_label]
        selected_goal_row = goals[goals["goal_id"] == selected_goal_id]
        if not selected_goal_row.empty:
            description = str(selected_goal_row.iloc[0].get("description", "") or "").strip()
            if description:
                c1.caption(f"Purpose: {description}")
        log_date = c2.date_input("Log Date", value=date.today())

        c3, c4, c5 = st.columns(3)
        hours_spent = c3.number_input("Hours Spent", min_value=0.0, max_value=24.0, value=1.0, step=0.25)
        quantity = c4.number_input("Quantity", min_value=0.0, value=0.0, step=1.0)
        quantity_unit = c5.text_input("Quantity Unit", placeholder="Features, steps, km, articles, etc.")

        c6, c7, c8, c9 = st.columns(4)
        leverage_type = c6.selectbox("Leverage Type", LEVERAGE_TYPE_OPTIONS)
        difficulty = c7.selectbox("Difficulty", DIFFICULTY_OPTIONS, index=1)
        energy_level = c8.selectbox("Energy Level", ENERGY_OPTIONS, index=1)
        mood = c9.selectbox("Mood", MOOD_OPTIONS, index=2)

        achievement = st.text_input("Achievement", placeholder="What did you complete or move forward?")
        progress_note = st.text_area("Progress Note / Diary", placeholder="What happened, what worked, what blocked you, what did you learn?")
        submitted = st.form_submit_button("Save Progress Log", type="primary")

    if submitted:
        new_row = create_log_row(
            goal_id=goal_options[selected_label],
            log_date=log_date,
            hours_spent=hours_spent,
            quantity=quantity,
            quantity_unit=quantity_unit,
            leverage_type=leverage_type,
            progress_note=progress_note,
            achievement=achievement,
            difficulty=difficulty,
            energy_level=energy_level,
            mood=mood,
        )
        updated = pd.concat([logs, pd.DataFrame([new_row])], ignore_index=True)
        write_table("logs", updated, LOGS_COLUMNS)
        clear_and_rerun("Progress logged successfully.")


def add_goal_form(goals: pd.DataFrame) -> None:
    st.subheader("➕ Add Goal / Habit")
    with st.form("add_goal_form", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        goal_type = c1.selectbox("Type", TYPE_OPTIONS)
        category = c2.selectbox("Category", CATEGORY_OPTIONS)
        priority = c3.selectbox("Priority", PRIORITY_OPTIONS)

        title = st.text_input("Title")
        description = st.text_area("Description")

        c4, c5, c6 = st.columns(3)
        status = c4.selectbox("Status", STATUS_OPTIONS)
        target_value = c5.number_input("Total Target Value", min_value=0.0, value=0.0, step=1.0)
        target_unit = c6.text_input("Target Unit", value="Hours")

        c9, c10, c11 = st.columns(3)
        default_weekly_target = WEEKLY_TARGET_HOURS.get(category, 1.0)
        weekly_target_hours = c9.number_input("Weekly Target Hours", min_value=0.0, value=float(default_weekly_target), step=0.25)
        review_frequency = c10.selectbox("Review Frequency", ["Weekly", "Monthly", "Quarterly", "Ad hoc"], index=0)
        role_context = c11.text_input("Role / Context", placeholder="Builder, leader, investor, health foundation, etc.")

        success_definition = st.text_area("Success Definition", placeholder="What does success look like for this goal/habit?")

        c7, c8 = st.columns(2)
        start_date = c7.date_input("Start Date", value=date.today())
        target_date = c8.date_input("Target Date", value=date.today().replace(month=12, day=31))
        submitted = st.form_submit_button("Add Goal / Habit", type="primary")

    if submitted:
        if not title.strip():
            st.error("Title is required.")
            return
        new_row = {
            "goal_id": new_id("goal"),
            "type": goal_type,
            "title": title.strip(),
            "category": category,
            "description": description,
            "status": status,
            "priority": priority,
            "target_value": target_value,
            "target_unit": target_unit,
            "weekly_target_hours": weekly_target_hours,
            "success_definition": success_definition,
            "review_frequency": review_frequency,
            "role_context": role_context,
            "start_date": str(start_date),
            "target_date": str(target_date),
            "created_at": now_ts(),
            "updated_at": now_ts(),
        }
        updated = pd.concat([goals, pd.DataFrame([new_row])], ignore_index=True)
        write_table("goals", updated, GOALS_COLUMNS)
        clear_and_rerun("Goal added successfully.")


def manage_goal_status(goals: pd.DataFrame) -> None:
    st.subheader("🛠️ Manage Goal Status")
    if goals.empty:
        return

    goal_options = goal_options_dict(goals, active_only=False)
    selected_label = st.selectbox("Select goal / habit to manage", list(goal_options.keys()), key="manage_goal_select")
    selected_id = goal_options[selected_label]
    row = goals[goals["goal_id"] == selected_id].iloc[0]

    description = str(row.get("description", "") or "").strip()
    if description:
        st.markdown(f"<div class='section-card'><b>Description / Purpose</b><br>{description}</div>", unsafe_allow_html=True)
    success_definition = str(row.get("success_definition", "") or "").strip()
    if success_definition:
        st.markdown(f"<div class='section-card'><b>Success Definition</b><br>{success_definition}</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1, 1])
    current_status = str(row.get("status", "Active"))
    new_status = c1.selectbox("New Status", STATUS_OPTIONS, index=STATUS_OPTIONS.index(current_status) if current_status in STATUS_OPTIONS else 0)

    if c2.button("Update Status", type="primary", width='stretch'):
        updated = goals.copy()
        updated.loc[updated["goal_id"] == selected_id, "status"] = new_status
        updated.loc[updated["goal_id"] == selected_id, "updated_at"] = now_ts()
        write_table("goals", updated, GOALS_COLUMNS)
        clear_and_rerun(f"Status updated to {new_status}.")

    if c3.button("Archive Selected", width='stretch'):
        updated = goals.copy()
        updated.loc[updated["goal_id"] == selected_id, "status"] = "Archived"
        updated.loc[updated["goal_id"] == selected_id, "updated_at"] = now_ts()
        write_table("goals", updated, GOALS_COLUMNS)
        clear_and_rerun("Goal archived successfully.")


def milestone_form(goals: pd.DataFrame, milestones: pd.DataFrame) -> None:
    st.subheader("🏆 Add Milestone")
    goal_options = goal_options_dict(goals, active_only=False)
    if not goal_options:
        st.info("Add a goal before recording milestones.")
        return

    with st.form("milestone_form", clear_on_submit=True):
        c1, c2 = st.columns([2, 1])
        selected_label = c1.selectbox("Linked Goal / Habit", list(goal_options.keys()))
        milestone_date = c2.date_input("Milestone Date", value=date.today())
        milestone_title = st.text_input("Milestone Title")
        milestone_description = st.text_area("Milestone Description")
        impact_score = st.slider("Impact Score", min_value=1, max_value=5, value=3)
        submitted = st.form_submit_button("Save Milestone", type="primary")

    if submitted:
        if not milestone_title.strip():
            st.error("Milestone title is required.")
            return
        new_row = {
            "milestone_id": new_id("mile"),
            "goal_id": goal_options[selected_label],
            "milestone_date": str(milestone_date),
            "milestone_title": milestone_title.strip(),
            "milestone_description": milestone_description,
            "impact_score": impact_score,
            "created_at": now_ts(),
        }
        updated = pd.concat([milestones, pd.DataFrame([new_row])], ignore_index=True)
        write_table("milestones", updated, MILESTONES_COLUMNS)
        clear_and_rerun("Milestone saved successfully.")


# -----------------------------------------------------------------------------
# Charts and sections
# -----------------------------------------------------------------------------
def weekly_command_center(goals: pd.DataFrame, logs: pd.DataFrame, enriched: pd.DataFrame) -> None:
    st.subheader("🧭 Weekly Command Center")
    score, score_df = calculate_execution_score(goals, logs)
    week_logs = get_current_week_logs(goals, logs)

    client_hours = float(score_df.loc[score_df["Category"] == "Client Zero / AI Tools", "Actual Hours This Week"].sum())
    learning_hours = float(score_df.loc[score_df["Category"] == "Learning", "Actual Hours This Week"].sum())
    reflection_hours = float(score_df.loc[score_df["Category"] == "Reflection", "Actual Hours This Week"].sum())
    health_days = 0
    if not week_logs.empty:
        health_days = week_logs[week_logs["category"] == "Health and Energy"]["log_date"].dt.date.nunique()

    if not week_logs.empty:
        by_cat = week_logs.groupby("category", as_index=False)["hours_spent"].sum().sort_values("hours_spent", ascending=False)
        best_area = by_cat.iloc[0]["category"] if not by_cat.empty and by_cat.iloc[0]["hours_spent"] > 0 else "No activity yet"
    else:
        best_area = "No activity yet"

    gap_df = score_df.copy()
    gap_df["Gap Hours"] = gap_df["Weekly Target Hours"] - gap_df["Actual Hours This Week"]
    gap_df = gap_df[gap_df["Gap Hours"] > 0].sort_values("Gap Hours", ascending=False)
    neglected = gap_df.iloc[0]["Category"] if not gap_df.empty else "None"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Execution Score", f"{score}/100")
    c2.metric("Client Zero", f"{client_hours:.1f} / {WEEKLY_TARGET_HOURS['Client Zero / AI Tools']:.1f} h")
    c3.metric("Learning", f"{learning_hours:.1f} / {WEEKLY_TARGET_HOURS['Learning']:.1f} h")
    c4.metric("Health Days", f"{health_days} / 7")

    c5, c6, c7 = st.columns(3)
    c5.metric("Reflection", "Done" if reflection_hours > 0 else "Not yet")
    c6.metric("Best Progress Area", best_area)
    c7.metric("Most Behind", neglected)

    st.markdown(f"<div class='nba-box'><b>Next Best Action:</b> {next_best_action(goals, logs, enriched)}</div>", unsafe_allow_html=True)

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        title={"text": "Weekly Execution Score"},
        gauge={"axis": {"range": [0, 100]}, "bar": {"color": "#2563eb"}},
    ))
    fig.update_layout(height=260, margin=dict(l=20, r=20, t=40, b=10))
    st.plotly_chart(fig, width='stretch')


def priority_vs_effort_chart(goals: pd.DataFrame, logs: pd.DataFrame, filters: Dict) -> None:
    st.subheader("🎚️ Priority vs Actual Effort")
    data = priority_vs_effort_data(goals, logs, filters["start_date"], filters["end_date"])
    if data["hours_spent"].sum() == 0:
        st.info("No logged hours in the selected date range yet.")
        return

    long_df = data.melt(
        id_vars=["Category", "hours_spent", "Gap %"],
        value_vars=["Priority Weight %", "Actual Effort %"],
        var_name="Measure",
        value_name="Percent",
    )
    fig = px.bar(
        long_df,
        x="Category",
        y="Percent",
        color="Measure",
        barmode="group",
        text="Percent",
        title="Are your actions matching your stated priorities?",
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig.update_layout(height=460, xaxis_tickangle=-25, yaxis_title="Share of Effort / Priority")
    st.plotly_chart(fig, width='stretch')

    gap_view = data.sort_values("Gap %")[["Category", "Priority Weight %", "Actual Effort %", "hours_spent", "Gap %"]]
    gap_view = gap_view.rename(columns={"hours_spent": "Hours Logged"})
    st.dataframe(gap_view, width='stretch', hide_index=True)


def overview_charts(goals: pd.DataFrame, logs: pd.DataFrame, filtered_goals: pd.DataFrame, filters: Dict) -> None:
    st.subheader("📊 Visual Progress")
    logs_filtered = filter_logs_by_date(logs, filters)
    if logs_filtered.empty:
        st.info("No logs found for the selected date range. Add a progress log to unlock charts.")
        return

    merged = logs_with_goal_info(goals, logs_filtered)

    c1, c2 = st.columns(2)

    by_goal = merged.groupby("title", as_index=False)["hours_spent"].sum().sort_values("hours_spent", ascending=False)
    fig_goal = px.bar(by_goal, x="hours_spent", y="title", orientation="h", title="Hours by Goal / Habit")
    fig_goal.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
    c1.plotly_chart(fig_goal, width='stretch')

    by_lev = merged.groupby("leverage_type", as_index=False)["hours_spent"].sum().sort_values("hours_spent", ascending=False)
    fig_lev = px.bar(by_lev, x="hours_spent", y="leverage_type", orientation="h", title="Hours by Leverage Type")
    fig_lev.update_layout(yaxis={"categoryorder": "total ascending"}, height=420)
    c2.plotly_chart(fig_lev, width='stretch')

    c3, c4 = st.columns(2)
    by_cat = merged.groupby("category", as_index=False)["hours_spent"].sum().sort_values("hours_spent", ascending=False)
    fig_cat = px.pie(by_cat, names="category", values="hours_spent", title="Effort by Category")
    fig_cat.update_layout(height=420)
    c3.plotly_chart(fig_cat, width='stretch')

    logs_trend = merged.copy()
    logs_trend["week_start"] = logs_trend["log_date"].dt.to_period("W").apply(lambda r: r.start_time)
    weekly = logs_trend.groupby("week_start", as_index=False)["hours_spent"].sum()
    fig_week = px.line(weekly, x="week_start", y="hours_spent", markers=True, title="Weekly Progress Trend")
    fig_week.update_layout(height=420, xaxis_title="Week", yaxis_title="Hours")
    c4.plotly_chart(fig_week, width='stretch')

    score, score_df = calculate_execution_score(goals, logs)
    fig_score = px.bar(
        score_df,
        x="Category",
        y="Score",
        text="Score",
        title=f"Weekly Execution Score Breakdown: {score}/100",
    )
    fig_score.update_layout(height=420, xaxis_tickangle=-25)
    st.plotly_chart(fig_score, width='stretch')


def goal_table_section(enriched: pd.DataFrame, filtered_goals: pd.DataFrame) -> None:
    st.subheader("🎯 Goals & Habits")
    if filtered_goals.empty:
        st.info("No goals match the current filters.")
        return

    view_cols = [
        "title", "description", "type", "category", "status", "priority", "hours_this_week",
        "hours_this_month", "hours_all_time", "last_logged_date", "days_since_last_log",
        "total_logs", "progress_pct", "weekly_target_hours", "success_definition", "target_date",
    ]
    table = filtered_goals[view_cols].copy()
    table = table.rename(columns={
        "title": "Goal / Habit",
        "description": "Description",
        "type": "Type",
        "category": "Category",
        "status": "Status",
        "priority": "Priority",
        "hours_this_week": "Hours This Week",
        "hours_this_month": "Hours This Month",
        "hours_all_time": "Hours All Time",
        "last_logged_date": "Last Logged Date",
        "days_since_last_log": "Days Since Last Log",
        "total_logs": "Total Logs",
        "progress_pct": "Progress %",
        "weekly_target_hours": "Weekly Target Hours",
        "success_definition": "Success Definition",
        "target_date": "Target Date",
    })
    st.dataframe(table, width='stretch', hide_index=True)


def goal_detail_section(goals: pd.DataFrame, logs: pd.DataFrame, milestones: pd.DataFrame) -> None:
    st.subheader("🔎 Goal Detail View")
    if goals.empty:
        return

    goal_options = goal_options_dict(goals, active_only=False)
    selected_label = st.selectbox("Select goal / habit for detail", list(goal_options.keys()))
    selected_id = goal_options[selected_label]
    selected_goal = goals[goals["goal_id"] == selected_id].iloc[0]
    sub_logs = logs[logs["goal_id"] == selected_id].dropna(subset=["log_date"]).copy()

    description = str(selected_goal.get("description", "") or "").strip()
    if description:
        st.markdown(f"<div class='section-card'><b>Description / Purpose</b><br>{description}</div>", unsafe_allow_html=True)
    success_definition = str(selected_goal.get("success_definition", "") or "").strip()
    if success_definition:
        st.markdown(f"<div class='section-card'><b>Success Definition</b><br>{success_definition}</div>", unsafe_allow_html=True)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Hours", f"{sub_logs['hours_spent'].sum():.1f}" if not sub_logs.empty else "0.0")
    c2.metric("Total Logs", len(sub_logs))
    c3.metric("Target", f"{selected_goal.get('target_value', 0):.0f} {selected_goal.get('target_unit', '')}")
    last_date = sub_logs["log_date"].max().date() if not sub_logs.empty else "No log yet"
    c4.metric("Last Log", str(last_date))

    if not sub_logs.empty:
        sub_logs = sub_logs.sort_values("log_date")
        sub_logs["cumulative_hours"] = sub_logs["hours_spent"].cumsum()
        fig = px.line(sub_logs, x="log_date", y="cumulative_hours", markers=True, title="Cumulative Hours Over Time")
        st.plotly_chart(fig, width='stretch')

        by_lev = sub_logs.groupby("leverage_type", as_index=False)["hours_spent"].sum().sort_values("hours_spent", ascending=False)
        fig_lev = px.bar(by_lev, x="hours_spent", y="leverage_type", orientation="h", title="Leverage Type Mix for Selected Goal")
        st.plotly_chart(fig_lev, width='stretch')

        diary = sub_logs[["log_date", "hours_spent", "leverage_type", "achievement", "progress_note", "difficulty", "energy_level", "mood"]].sort_values("log_date", ascending=False)
        st.dataframe(diary, width='stretch', hide_index=True)

    sub_miles = milestones[milestones["goal_id"] == selected_id].copy()
    if not sub_miles.empty:
        st.markdown("#### Milestones")
        st.dataframe(
            sub_miles[["milestone_date", "milestone_title", "milestone_description", "impact_score"]].sort_values("milestone_date", ascending=False),
            width='stretch',
            hide_index=True,
        )


def diary_section(goals: pd.DataFrame, logs: pd.DataFrame, filters: Dict) -> None:
    st.subheader("📓 Progress Diary")
    logs_filtered = filter_logs_by_date(logs, filters)
    if logs_filtered.empty:
        st.info("No diary entries in this date range.")
        return

    diary = logs_with_goal_info(goals, logs_filtered)
    diary = diary[[
        "log_date", "title", "category", "hours_spent", "quantity", "quantity_unit", "leverage_type",
        "achievement", "progress_note", "difficulty", "energy_level", "mood",
    ]].sort_values("log_date", ascending=False)
    diary = diary.rename(columns={"title": "Goal / Habit", "category": "Category", "leverage_type": "Leverage Type"})
    st.dataframe(diary, width='stretch', hide_index=True)


def insights_section(enriched: pd.DataFrame, goals: pd.DataFrame, logs: pd.DataFrame) -> None:
    st.subheader("🧠 Insight Engine")
    for insight in make_insights(enriched, goals, logs):
        st.markdown(f"<div class='insight-box'>{insight}</div>", unsafe_allow_html=True)




def target_vs_actual_by_goal_section(enriched: pd.DataFrame, logs: pd.DataFrame) -> None:
    st.subheader("🎯 Target vs Actual by Goal")
    active = enriched[enriched["status"] == "Active"].copy() if not enriched.empty else pd.DataFrame()
    if active.empty:
        st.info("No active goals or habits to compare against targets.")
        return

    ws, today = active_week_range()
    week_logs = period_logs(logs, ws, today)
    rows = []
    for _, r in active.iterrows():
        goal_id = r["goal_id"]
        actual = safe_sum_hours(week_logs[week_logs["goal_id"] == goal_id]) if not week_logs.empty else 0.0
        target = get_goal_weekly_target(r)
        achievement = actual / target * 100 if target > 0 else 0.0
        if target <= 0:
            status = "No Target"
        elif achievement >= 100:
            status = "On Track"
        elif achievement >= 70:
            status = "Slightly Behind"
        elif achievement > 0:
            status = "Behind"
        else:
            status = "No Progress"
        rows.append({
            "Goal / Habit": r.get("title", ""),
            "Type": r.get("type", ""),
            "Category": r.get("category", ""),
            "Priority": r.get("priority", ""),
            "Weekly Target Hours": target,
            "Actual This Week": actual,
            "Achievement %": min(achievement, 999),
            "Status": status,
        })

    data = pd.DataFrame(rows).sort_values(["Priority", "Achievement %"], ascending=[True, True])
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.dataframe(data, width='stretch', hide_index=True)
    with c2:
        chart_df = data[data["Weekly Target Hours"] > 0].copy()
        if not chart_df.empty:
            long_df = chart_df.melt(
                id_vars=["Goal / Habit", "Category", "Status"],
                value_vars=["Weekly Target Hours", "Actual This Week"],
                var_name="Measure",
                value_name="Hours",
            )
            fig = px.bar(long_df, x="Goal / Habit", y="Hours", color="Measure", barmode="group", title="Weekly Target vs Actual")
            fig.update_layout(height=430, xaxis_tickangle=-35)
            st.plotly_chart(fig, width='stretch')


def weekly_reflection_section(goals: pd.DataFrame, logs: pd.DataFrame, weekly_reflections: pd.DataFrame) -> None:
    st.subheader("🪞 Weekly Reflection")
    this_week_start = week_start(date.today())
    existing = weekly_reflections.dropna(subset=["week_start"]).copy() if not weekly_reflections.empty else pd.DataFrame(columns=WEEKLY_REFLECTIONS_COLUMNS)
    if not existing.empty:
        existing["week_day"] = existing["week_start"].dt.date
    already_done = not existing[existing["week_day"] == this_week_start].empty if not existing.empty and "week_day" in existing.columns else False

    if already_done:
        st.markdown("<div class='success-box'><b>This week's reflection is already recorded.</b> You can still add another note if you want to capture a new decision.</div>", unsafe_allow_html=True)

    reflection_options = reflection_habit_options(goals, review_type="weekly")
    already_logged_habit = has_review_habit_log_for_period(goals, logs, "weekly", this_week_start)

    with st.form("weekly_reflection_form", clear_on_submit=True):
        c1, c2 = st.columns([1, 1])
        reflection_week = c1.date_input("Week Start", value=this_week_start)
        focus_score = c2.slider("Focus Score", min_value=1, max_value=10, value=7, help="How focused was this week against your roadmap?")
        what_i_built = st.text_area("What did I build this week?", placeholder="Tools, dashboards, processes, documents, assets, systems...")
        what_created_leverage = st.text_area("What created leverage?", placeholder="What will keep paying back later?")
        what_distracted_me = st.text_area("What distracted me?", placeholder="Low-value work, context switching, unnecessary polishing...")
        what_to_stop_doing = st.text_area("What should I stop doing?", placeholder="Be honest. What is consuming effort without building future advantage?")
        nba = st.text_area("Next most important action", placeholder="One action that matters most next week")

        st.markdown("#### Habit log link")
        if reflection_options:
            selected_reflection_habit = st.selectbox(
                "Reflection habit to log against",
                list(reflection_options.keys()),
                help="This reuses your existing Reflection habit, for example Weekly Strategic Reflection — Reflection.",
            )
            auto_log_habit = st.checkbox(
                "Also create a habit log for this weekly review",
                value=not already_logged_habit,
                help="Tick this if you want this review to count toward Reflection hours, habit consistency, and the weekly execution score.",
            )
            if already_logged_habit:
                st.caption("A Reflection habit log already appears to exist for this week. Untick this box to avoid double logging.")
            habit_hours = st.number_input("Habit log hours", min_value=0.0, max_value=8.0, value=0.5, step=0.25)
        else:
            selected_reflection_habit = None
            auto_log_habit = False
            habit_hours = 0.0
            st.warning("No Reflection habit was found. Create a Habit in the Reflection category first, such as 'Weekly Strategic Reflection'.")

        submitted = st.form_submit_button("Save Weekly Reflection", type="primary")

    if submitted:
        new_row = {
            "reflection_id": new_id("refl"),
            "week_start": str(reflection_week),
            "what_i_built": what_i_built,
            "what_created_leverage": what_created_leverage,
            "what_distracted_me": what_distracted_me,
            "what_to_stop_doing": what_to_stop_doing,
            "next_best_action": nba,
            "focus_score": focus_score,
            "created_at": now_ts(),
        }
        updated_reflections = pd.concat([weekly_reflections, pd.DataFrame([new_row])], ignore_index=True)
        write_table("weekly_reflections", updated_reflections, WEEKLY_REFLECTIONS_COLUMNS)

        if auto_log_habit and selected_reflection_habit:
            summary = (
                f"What I built: {what_i_built}\n\n"
                f"Created leverage: {what_created_leverage}\n\n"
                f"Distraction: {what_distracted_me}\n\n"
                f"Stop doing: {what_to_stop_doing}\n\n"
                f"Next action: {nba}"
            ).strip()
            log_row = build_review_habit_log_row(
                goal_id=reflection_options[selected_reflection_habit],
                log_date=reflection_week,
                hours_spent=float(habit_hours or 0),
                review_type="weekly",
                summary=summary,
            )
            updated_logs = pd.concat([logs, pd.DataFrame([log_row])], ignore_index=True)
            write_table("logs", updated_logs, LOGS_COLUMNS)
            clear_and_rerun("Weekly reflection saved and Reflection habit log created.")

        clear_and_rerun("Weekly reflection saved successfully.")

    st.markdown("#### Reflection History")
    if weekly_reflections.empty:
        st.info("No weekly reflections yet.")
    else:
        table = weekly_reflections.sort_values("week_start", ascending=False)[[
            "week_start", "focus_score", "what_i_built", "what_created_leverage", "what_distracted_me", "what_to_stop_doing", "next_best_action"
        ]]
        st.dataframe(table, width='stretch', hide_index=True)

def monthly_review_section(goals: pd.DataFrame, logs: pd.DataFrame, weekly_reflections: pd.DataFrame, monthly_reviews: pd.DataFrame) -> None:
    st.subheader("📅 Monthly Review")
    ms, today = current_month_range()
    month_logs = period_logs(logs, ms, today)
    merged = logs_with_goal_info(goals, month_logs) if not month_logs.empty else pd.DataFrame()

    total_hours = safe_sum_hours(month_logs)
    high_lev_hours = safe_sum_hours(month_logs[month_logs["leverage_type"].isin(HIGH_LEVERAGE_TYPES)]) if not month_logs.empty and "leverage_type" in month_logs.columns else 0.0
    high_lev_pct = high_lev_hours / total_hours if total_hours > 0 else 0
    top_category = top_item_label(merged, "category") if not merged.empty else "No activity yet"
    top_goal = top_item_label(merged, "title") if not merged.empty else "No activity yet"

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Month Hours", f"{total_hours:.1f} h")
    c2.metric("High-Leverage Share", f"{high_lev_pct:.0%}", f"{high_lev_hours:.1f} h")
    c3.metric("Top Category", top_category)
    c4.metric("Top Goal", top_goal)

    reflection_options = reflection_habit_options(goals, review_type="monthly")
    already_logged_habit = has_review_habit_log_for_period(goals, logs, "monthly", ms)

    with st.form("monthly_review_form", clear_on_submit=True):
        review_month = st.date_input("Month Start", value=ms)
        top_achievements = st.text_area("Top achievements", placeholder="What actually moved your life/career/business forward this month?")
        best_leverage_activity = st.text_area("Best leverage activity", placeholder="Which activity created the most future advantage?")
        biggest_distraction = st.text_area("Biggest distraction", placeholder="What consumed effort without enough value?")
        most_neglected_area = st.text_input("Most neglected area", placeholder="Example: Wealth, Health, Client Zero...")
        what_to_double_down = st.text_area("What to double down on next month")
        what_to_stop = st.text_area("What to stop doing")
        next_month_focus = st.text_area("Next month focus", placeholder="1-3 focus areas only")

        st.markdown("#### Habit log link")
        if reflection_options:
            selected_reflection_habit = st.selectbox(
                "Reflection habit to log against",
                list(reflection_options.keys()),
                help="If you do not have a Monthly Strategic Review habit, this can reuse your existing Weekly Strategic Reflection habit.",
            )
            auto_log_habit = st.checkbox(
                "Also create a habit log for this monthly review",
                value=not already_logged_habit,
                help="Tick this if you want this review to count toward Reflection hours and habit consistency.",
            )
            if already_logged_habit:
                st.caption("A Reflection habit log already appears to exist for this month. Untick this box to avoid double logging.")
            habit_hours = st.number_input("Habit log hours", min_value=0.0, max_value=8.0, value=1.0, step=0.25)
        else:
            selected_reflection_habit = None
            auto_log_habit = False
            habit_hours = 0.0
            st.warning("No Reflection habit was found. Create a Habit in the Reflection category first, such as 'Weekly Strategic Reflection'.")

        submitted = st.form_submit_button("Save Monthly Review", type="primary")

    if submitted:
        review_month_start = review_month.replace(day=1)
        new_row = {
            "review_id": new_id("mrev"),
            "month_start": str(review_month_start),
            "top_achievements": top_achievements,
            "best_leverage_activity": best_leverage_activity,
            "biggest_distraction": biggest_distraction,
            "most_neglected_area": most_neglected_area,
            "what_to_double_down": what_to_double_down,
            "what_to_stop": what_to_stop,
            "next_month_focus": next_month_focus,
            "created_at": now_ts(),
        }
        updated_reviews = pd.concat([monthly_reviews, pd.DataFrame([new_row])], ignore_index=True)
        write_table("monthly_reviews", updated_reviews, MONTHLY_REVIEWS_COLUMNS)

        if auto_log_habit and selected_reflection_habit:
            summary = (
                f"Top achievements: {top_achievements}\n\n"
                f"Best leverage activity: {best_leverage_activity}\n\n"
                f"Biggest distraction: {biggest_distraction}\n\n"
                f"Most neglected area: {most_neglected_area}\n\n"
                f"Double down: {what_to_double_down}\n\n"
                f"Stop: {what_to_stop}\n\n"
                f"Next month focus: {next_month_focus}"
            ).strip()
            log_row = build_review_habit_log_row(
                goal_id=reflection_options[selected_reflection_habit],
                log_date=review_month_start,
                hours_spent=float(habit_hours or 0),
                review_type="monthly",
                summary=summary,
            )
            updated_logs = pd.concat([logs, pd.DataFrame([log_row])], ignore_index=True)
            write_table("logs", updated_logs, LOGS_COLUMNS)
            clear_and_rerun("Monthly review saved and Reflection habit log created.")

        clear_and_rerun("Monthly review saved successfully.")

    st.markdown("#### Monthly Review History")
    if monthly_reviews.empty:
        st.info("No monthly reviews yet.")
    else:
        st.dataframe(
            monthly_reviews.sort_values("month_start", ascending=False)[[
                "month_start", "top_achievements", "best_leverage_activity", "biggest_distraction",
                "most_neglected_area", "what_to_double_down", "what_to_stop", "next_month_focus"
            ]],
            width='stretch',
            hide_index=True,
        )

def edit_delete_log_section(goals: pd.DataFrame, logs: pd.DataFrame) -> None:
    st.subheader("✏️ Edit / Delete Log")
    if logs.empty:
        st.info("No logs to edit yet.")
        return

    labels = log_selector_labels(goals, logs)
    if not labels:
        st.info("No valid logs found.")
        return

    selected_label = st.selectbox("Select a recent log", list(labels.keys()))
    selected_log_id = labels[selected_label]
    row_df = logs[logs["log_id"] == selected_log_id]
    if row_df.empty:
        st.warning("Selected log could not be found.")
        return
    row = row_df.iloc[0]

    goal_options = goal_options_dict(goals, active_only=False)
    goal_id_to_label = {v: k for k, v in goal_options.items()}
    current_goal_label = goal_id_to_label.get(row.get("goal_id"), list(goal_options.keys())[0] if goal_options else "")

    with st.form("edit_log_form"):
        c1, c2, c3 = st.columns([2, 1, 1])
        goal_label = c1.selectbox("Goal / Habit", list(goal_options.keys()), index=list(goal_options.keys()).index(current_goal_label) if current_goal_label in goal_options else 0)
        log_date_value = safe_to_date(row.get("log_date")) or date.today()
        new_log_date = c2.date_input("Log Date", value=log_date_value)
        hours = c3.number_input("Hours", min_value=0.0, max_value=24.0, value=float(row.get("hours_spent", 0) or 0), step=0.25)

        c4, c5, c6, c7 = st.columns(4)
        leverage_current = str(row.get("leverage_type", "Maintenance / Admin") or "Maintenance / Admin")
        leverage_index = LEVERAGE_TYPE_OPTIONS.index(leverage_current) if leverage_current in LEVERAGE_TYPE_OPTIONS else 0
        leverage_type = c4.selectbox("Leverage Type", LEVERAGE_TYPE_OPTIONS, index=leverage_index)
        difficulty = c5.selectbox("Difficulty", DIFFICULTY_OPTIONS, index=DIFFICULTY_OPTIONS.index(str(row.get("difficulty", "Normal"))) if str(row.get("difficulty", "Normal")) in DIFFICULTY_OPTIONS else 1)
        energy = c6.selectbox("Energy", ENERGY_OPTIONS, index=ENERGY_OPTIONS.index(str(row.get("energy_level", "Medium"))) if str(row.get("energy_level", "Medium")) in ENERGY_OPTIONS else 1)
        mood = c7.selectbox("Mood", MOOD_OPTIONS, index=MOOD_OPTIONS.index(str(row.get("mood", "Good"))) if str(row.get("mood", "Good")) in MOOD_OPTIONS else 2)

        c8, c9 = st.columns(2)
        quantity = c8.number_input("Quantity", min_value=0.0, value=float(row.get("quantity", 0) or 0), step=1.0)
        quantity_unit = c9.text_input("Quantity Unit", value=str(row.get("quantity_unit", "") or ""))
        achievement = st.text_input("Achievement", value=str(row.get("achievement", "") or ""))
        progress_note = st.text_area("Progress Note", value=str(row.get("progress_note", "") or ""))
        save = st.form_submit_button("Save Log Changes", type="primary")

    if save:
        updated = logs.copy()
        idx = updated.index[updated["log_id"] == selected_log_id]
        if len(idx) > 0:
            i = idx[0]
            updated.loc[i, "goal_id"] = goal_options[goal_label]
            updated.loc[i, "log_date"] = str(new_log_date)
            updated.loc[i, "hours_spent"] = hours
            updated.loc[i, "quantity"] = quantity
            updated.loc[i, "quantity_unit"] = quantity_unit
            updated.loc[i, "leverage_type"] = leverage_type
            updated.loc[i, "achievement"] = achievement
            updated.loc[i, "progress_note"] = progress_note
            updated.loc[i, "difficulty"] = difficulty
            updated.loc[i, "energy_level"] = energy
            updated.loc[i, "mood"] = mood
            write_table("logs", updated, LOGS_COLUMNS)
            clear_and_rerun("Log updated successfully.")

    if st.button("Delete Selected Log", type="secondary", width='stretch'):
        updated = logs[logs["log_id"] != selected_log_id].copy()
        write_table("logs", updated, LOGS_COLUMNS)
        clear_and_rerun("Log deleted successfully.")

def roadmap_section() -> None:
    st.subheader("🗺️ Roadmap Timeline")
    roadmap = pd.DataFrame([
        {"Year": "2026", "Theme": "Build the Core", "Main Output": "One serious operational dashboard/tool, reputation as automation systems person, financial base, health foundation"},
        {"Year": "2027", "Theme": "Become Dangerous", "Main Output": "PgMP, AI intelligence layer, RAG/manual search bot, operational copilot prototype"},
        {"Year": "2028", "Theme": "Productize Capability", "Main Output": "Clear external offer, pilot users or small clients, reusable templates and systems"},
        {"Year": "2029", "Theme": "Scale Optionality", "Main Output": "Meaningful consulting/tool income, known for industrial AI and operational transformation"},
        {"Year": "2030", "Theme": "Freedom Through Leverage", "Main Output": "Selective work, stronger assets, system income, health and family stability"},
    ])
    st.dataframe(roadmap, width='stretch', hide_index=True)


def export_section(goals: pd.DataFrame, logs: pd.DataFrame, milestones: pd.DataFrame, weekly_reflections: pd.DataFrame, monthly_reviews: pd.DataFrame) -> None:
    st.subheader("⬇️ Export")
    c1, c2, c3 = st.columns(3)
    c1.download_button("Download Goals CSV", goals.to_csv(index=False), file_name="goals.csv", mime="text/csv")
    c2.download_button("Download Logs CSV", logs.to_csv(index=False), file_name="logs.csv", mime="text/csv")
    c3.download_button("Download Milestones CSV", milestones.to_csv(index=False), file_name="milestones.csv", mime="text/csv")
    c4, c5 = st.columns(2)
    c4.download_button("Download Weekly Reflections CSV", weekly_reflections.to_csv(index=False), file_name="weekly_reflections.csv", mime="text/csv")
    c5.download_button("Download Monthly Reviews CSV", monthly_reviews.to_csv(index=False), file_name="monthly_reviews.csv", mime="text/csv")


# -----------------------------------------------------------------------------
# Main app
# -----------------------------------------------------------------------------
def main() -> None:
    if not check_password():
        return

    render_google_sheets_diagnostics()

    goals, logs, milestones, weekly_reflections, monthly_reviews = load_data()
    enriched = enrich_goals(goals, logs)
    filters = sidebar_filters(enriched)
    filtered_goals = apply_goal_filters(enriched, filters)

    top_col1, top_col2 = st.columns([4, 1])

    with top_col1:
        st.title("🎯 Personal Goal Progress Dashboard")
        st.caption("Your personal command center for tracking effort, leverage, consistency, and achievement.")

    with top_col2:
        st.markdown("<div style='height: 2.2rem;'></div>", unsafe_allow_html=True)
        sheet_url = get_spreadsheet_url()
        if sheet_url:
            st.link_button("📄 Google Sheet", sheet_url, width='stretch')

    metric_row(enriched, logs)

    tabs = st.tabs([
        "Command Center",
        "Quick Log",
        "Overview",
        "Goals",
        "Goal Detail",
        "Diary",
        "Milestones",
        "Weekly Review",
        "Monthly Review",
        "Roadmap",
        "Export",
    ])

    with tabs[0]:
        weekly_command_center(goals, logs, enriched)
        quick_log_form(goals, logs, location="command")
        insights_section(enriched, goals, logs)

    with tabs[1]:
        quick_log_form(goals, logs, location="quick_tab")
        st.divider()
        log_progress_form(goals, logs)
        st.divider()
        edit_delete_log_section(goals, logs)

    with tabs[2]:
        target_vs_actual_by_goal_section(enriched, logs)
        st.divider()
        priority_vs_effort_chart(goals, logs, filters)
        overview_charts(goals, logs, filtered_goals, filters)
        goal_table_section(enriched, filtered_goals)

    with tabs[3]:
        add_goal_form(goals)
        st.divider()
        manage_goal_status(goals)
        st.divider()
        goal_table_section(enriched, filtered_goals)

    with tabs[4]:
        goal_detail_section(goals, logs, milestones)

    with tabs[5]:
        diary_section(goals, logs, filters)

    with tabs[6]:
        milestone_form(goals, milestones)

    with tabs[7]:
        weekly_reflection_section(goals, logs, weekly_reflections)

    with tabs[8]:
        monthly_review_section(goals, logs, weekly_reflections, monthly_reviews)

    with tabs[9]:
        roadmap_section()

    with tabs[10]:
        export_section(goals, logs, milestones, weekly_reflections, monthly_reviews)


if __name__ == "__main__":
    main()
