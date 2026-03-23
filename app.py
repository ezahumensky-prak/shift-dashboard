import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
import calendar

st.set_page_config(page_title="Supervisor Shift Planner", layout="wide")

st.markdown("""
<style>
    .stApp {
        background: linear-gradient(180deg, #0b1020 0%, #11182d 100%);
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
        max-width: 95rem;
    }
    h1, h2, h3, h4, p, label, div {
        color: white;
    }
    div[data-testid="stMetric"] {
        background-color: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        padding: 14px;
        border-radius: 14px;
    }
    div[data-testid="stMetricLabel"] {
        color: #aab4c8;
    }
    div[data-testid="stMetricValue"] {
        color: white;
    }
</style>
""", unsafe_allow_html=True)

st.title("Supervisor Shift Planner")
st.caption("2-mesačný plán smien, vizuálny kalendár, fond hodín a náhrady pri výpadku")

# ---------------------------
# POMOCNÉ FUNKCIE
# ---------------------------
def monthly_fund_hours(year: int, month: int, weekly_hours: float) -> float:
    weeks_in_month = calendar.monthcalendar(year, month)
    weekday_count = sum(1 for week in weeks_in_month for day in week[:5] if day != 0)
    return round((weekly_hours / 5) * weekday_count, 1)

def get_weekly_hours(name: str) -> int:
    if name.startswith("FT"):
        return 40
    if name.startswith("PT"):
        return 20
    return 16

def get_employee_type(name: str) -> str:
    if name.startswith("FT"):
        return "Fulltime"
    if name.startswith("PT"):
        return "Parttime"
    return "Brigádnik"

def is_weekend(date_value) -> bool:
    return pd.Timestamp(date_value).weekday() >= 5

def build_fund_df(source_df: pd.DataFrame, employees_df: pd.DataFrame, start_dt: datetime) -> pd.DataFrame:
    hours_summary = source_df.groupby("employee", as_index=False)["hours"].sum().rename(columns={"hours": "planned_hours"})
    next_month = (start_dt.replace(day=28) + timedelta(days=4)).replace(day=1)

    rows = []
    for emp in employees_df["name"]:
        weekly_hours = get_weekly_hours(emp)

        planned = hours_summary.loc[hours_summary["employee"] == emp, "planned_hours"]
        planned = float(planned.iloc[0]) if not planned.empty else 0.0

        fund_month_1 = monthly_fund_hours(start_dt.year, start_dt.month, weekly_hours)
        fund_month_2 = monthly_fund_hours(next_month.year, next_month.month, weekly_hours)
        target_fund = round(fund_month_1 + fund_month_2, 1)

        difference = round(target_fund - planned, 1)

        if difference > 20:
            status = "Pod fondom"
        elif difference < -20:
            status = "Nad fondom"
        else:
            status = "V norme"

        rows.append({
            "employee": emp,
            "employee_type": get_employee_type(emp),
            "planned_hours": planned,
            "target_fund_hours": target_fund,
            "difference": difference,
            "status": status
        })

    return pd.DataFrame(rows)

# ---------------------------
# DÁTA
# ---------------------------
today = datetime.today()
start_date = datetime(today.year, today.month, 1)
days = 61

employees = []

for i in range(6):
    employees.append({
        "name": f"FT_{i+1}",
        "employee_type": "Fulltime",
        "weekly_hours": 40
    })

for i in range(4):
    employees.append({
        "name": f"PT_{i+1}",
        "employee_type": "Parttime",
        "weekly_hours": 20
    })

for i in range(4):
    employees.append({
        "name": f"BR_{i+1}",
        "employee_type": "Brigádnik",
        "weekly_hours": 16
    })

employees = pd.DataFrame(employees)

# ---------------------------
# GENEROVANIE SMIEN
# denne: 2 FT, 2 PT, 2 BR
# ---------------------------
shifts = []

ft_names = employees[employees["employee_type"] == "Fulltime"]["name"].tolist()
pt_names = employees[employees["employee_type"] == "Parttime"]["name"].tolist()
br_names = employees[employees["employee_type"] == "Brigádnik"]["name"].tolist()

for d in range(days):
    current_date = start_date + timedelta(days=d)

    ft_today = [ft_names[(2 * d) % len(ft_names)], ft_names[(2 * d + 1) % len(ft_names)]]
    pt_today = [pt_names[(2 * d) % len(pt_names)], pt_names[(2 * d + 1) % len(pt_names)]]
    br_today = [br_names[(2 * d) % len(br_names)], br_names[(2 * d + 1) % len(br_names)]]

    for name in ft_today:
        shifts.append({
            "employee": name,
            "date": current_date.date(),
            "start": current_date.replace(hour=9, minute=0),
            "end": current_date.replace(hour=21, minute=0),
            "group": "Fulltime",
            "hours": 12
        })

    for name in pt_today:
        shifts.append({
            "employee": name,
            "date": current_date.date(),
            "start": current_date.replace(hour=12, minute=0),
            "end": current_date.replace(hour=17, minute=0),
            "group": "Parttime",
            "hours": 5
        })

    for idx, name in enumerate(br_today):
        if idx == 0:
            shifts.append({
                "employee": name,
                "date": current_date.date(),
                "start": current_date.replace(hour=9, minute=0),
                "end": current_date.replace(hour=13, minute=0),
                "group": "Brigádnik ráno",
                "hours": 4
            })
        else:
            shifts.append({
                "employee": name,
                "date": current_date.date(),
                "start": current_date.replace(hour=17, minute=0),
                "end": current_date.replace(hour=21, minute=0),
                "group": "Brigádnik večer",
                "hours": 4
            })

df = pd.DataFrame(shifts)
df["day_type"] = df["date"].apply(lambda x: "Víkend" if is_weekend(x) else "Pracovný deň")

# ---------------------------
# SIDEBAR
# ---------------------------
st.sidebar.header("Nastavenia")

selected_groups = st.sidebar.multiselect(
    "Zobraziť typy smien",
    ["Fulltime", "Parttime", "Brigádnik ráno", "Brigádnik večer", "Náhrada"],
    default=["Fulltime", "Parttime", "Brigádnik ráno", "Brigádnik večer", "Náhrada"]
)

show_weekends_only = st.sidebar.checkbox("Zobraziť len víkendy", value=False)

employee_options = sorted(df["employee"].unique())
selected_employee = st.sidebar.selectbox(
    "Výpadok zamestnanca",
    ["Nikto"] + employee_options
)

absence_start_date = st.sidebar.date_input(
    "Začiatok výpadku",
    start_date.date()
)

absence_days = st.sidebar.slider(
    "Počet dní výpadku",
    min_value=1,
    max_value=14,
    value=1
)

absence_end_date = absence_start_date + timedelta(days=absence_days - 1)
st.sidebar.caption(f"Výpadok bude od {absence_start_date} do {absence_end_date}")

# ---------------------------
# FILTER
# ---------------------------
filtered_df = df.copy()

if show_weekends_only:
    filtered_df = filtered_df[filtered_df["day_type"] == "Víkend"].copy()

# ---------------------------
# SIMULÁCIA VÝPADKU + NÁHRADY
# ---------------------------
replacement_rows = []
absence_messages = []

if selected_employee != "Nikto":
    absence_dates = [absence_start_date + timedelta(days=i) for i in range(absence_days)]

    for current_absence_date in absence_dates:
        day_mask = (
            (filtered_df["employee"] == selected_employee) &
            (filtered_df["date"] == current_absence_date)
        )

        missing_shift_df = filtered_df[day_mask]

        if missing_shift_df.empty:
            absence_messages.append({
                "date": current_absence_date,
                "missing_employee": selected_employee,
                "replacement": "Bez smeny",
                "status": "V tento deň nemal smenu"
            })
            continue

        missing_shift = missing_shift_df.iloc[0]
        filtered_df = filtered_df[~day_mask].copy()

        missing_group = missing_shift["group"]
        missing_hours = missing_shift["hours"]

        if missing_group == "Fulltime":
            allowed_candidate_types = ["Fulltime"]
        elif missing_group == "Parttime":
            allowed_candidate_types = ["Parttime", "Brigádnik"]
        else:
            allowed_candidate_types = ["Brigádnik", "Parttime"]

        used_today = set(filtered_df[filtered_df["date"] == current_absence_date]["employee"].tolist())
        used_today.discard(selected_employee)

        candidates = employees.copy()
        candidates = candidates[~candidates["name"].isin(used_today)].copy()

        candidates["candidate_type"] = candidates["name"].apply(get_employee_type)
        candidates = candidates[candidates["candidate_type"].isin(allowed_candidate_types)].copy()
        candidates = candidates[candidates["name"] != selected_employee].copy()

        planned_hours = filtered_df.groupby("employee", as_index=False)["hours"].sum()
        planned_hours = planned_hours.rename(columns={"hours": "planned_hours"})

        candidates = candidates.merge(
            planned_hours,
            left_on="name",
            right_on="employee",
            how="left"
        )
        candidates["planned_hours"] = candidates["planned_hours"].fillna(0)

        candidates["current_month_fund"] = candidates["weekly_hours"].apply(
            lambda wh: monthly_fund_hours(current_absence_date.year, current_absence_date.month, wh)
        )
        candidates["fund_gap"] = candidates["current_month_fund"] - candidates["planned_hours"]

        original_type = get_employee_type(selected_employee)
        candidates["priority_score"] = candidates.apply(
            lambda row: 2 if row["candidate_type"] == original_type else 1,
            axis=1
        )

        candidates = candidates.sort_values(
            ["priority_score", "fund_gap", "planned_hours"],
            ascending=[False, False, True]
        ).copy()

        if not candidates.empty:
            top_candidates = candidates[["name", "candidate_type", "planned_hours", "current_month_fund", "fund_gap"]].head(3).copy()
            top_candidates["date"] = current_absence_date
            replacement_rows.append(top_candidates)

            replacement = candidates.iloc[0]["name"]

            filtered_df = pd.concat([
                filtered_df,
                pd.DataFrame([{
                    "employee": replacement,
                    "date": current_absence_date,
                    "start": missing_shift["start"],
                    "end": missing_shift["end"],
                    "group": "Náhrada",
                    "hours": missing_hours,
                    "day_type": "Víkend" if pd.Timestamp(current_absence_date).weekday() >= 5 else "Pracovný deň"
                }])
            ], ignore_index=True)

            absence_messages.append({
                "date": current_absence_date,
                "missing_employee": selected_employee,
                "replacement": replacement,
                "status": "Nahradené"
            })
        else:
            absence_messages.append({
                "date": current_absence_date,
                "missing_employee": selected_employee,
                "replacement": "Nenašla sa náhrada",
                "status": "Nepokryté"
            })

# Po simulácii až aplikuj filter skupín
filtered_df = filtered_df[filtered_df["group"].isin(selected_groups)].copy()

# ---------------------------
# KPI
# ---------------------------
col1, col2, col3, col4 = st.columns(4)

total_shifts = len(filtered_df)
total_hours = int(filtered_df["hours"].sum())
scheduled_people = filtered_df["employee"].nunique()
weekend_shifts = len(filtered_df[filtered_df["day_type"] == "Víkend"])

col1.metric("Naplánované smeny", total_shifts)
col2.metric("Naplánované hodiny", total_hours)
col3.metric("Nasadení ľudia", scheduled_people)
col4.metric("Víkendové smeny", weekend_shifts)

# ---------------------------
# INFO O VÝPADKU
# ---------------------------
if absence_messages:
    absence_df = pd.DataFrame(absence_messages)

    covered_count = len(absence_df[absence_df["status"] == "Nahradené"])
    uncovered_count = len(absence_df[absence_df["status"] == "Nepokryté"])

    if covered_count > 0:
        st.success(f"Nahradené dni výpadku: {covered_count}")

    if uncovered_count > 0:
        st.error(f"Nepokryté dni výpadku: {uncovered_count}")

    st.subheader("Prehľad výpadku a náhrad")
    st.dataframe(absence_df, use_container_width=True)

if replacement_rows:
    replacement_table = pd.concat(replacement_rows, ignore_index=True)
    replacement_table = replacement_table.rename(columns={
        "name": "Zamestnanec",
        "candidate_type": "Typ",
        "planned_hours": "Naplánované hodiny",
        "current_month_fund": "Mesačný fond",
        "fund_gap": "Rezerva do fondu",
        "date": "Dátum"
    })
    st.subheader("Top odporúčaní náhradníci podľa dní")
    st.dataframe(replacement_table, use_container_width=True)

# ---------------------------
# ALERTY FONDU HODÍN
# ---------------------------
fund_df = build_fund_df(filtered_df, employees, start_date)

underfund_df = fund_df[fund_df["status"] == "Pod fondom"].copy()
overfund_df = fund_df[fund_df["status"] == "Nad fondom"].copy()

alert_col1, alert_col2, alert_col3 = st.columns(3)
alert_col1.metric("Ľudia pod fondom", len(underfund_df))
alert_col2.metric("Ľudia nad fondom", len(overfund_df))
alert_col3.metric("Ľudia v norme", len(fund_df[fund_df["status"] == "V norme"]))

if len(underfund_df) > 0:
    st.warning("Niektorí zamestnanci sú pod plánovaným fondom hodín.")
    st.dataframe(
        underfund_df[["employee", "employee_type", "planned_hours", "target_fund_hours", "difference", "status"]],
        use_container_width=True
    )

if len(overfund_df) > 0:
    st.error("Niektorí zamestnanci sú nad plánovaným fondom hodín.")
    st.dataframe(
        overfund_df[["employee", "employee_type", "planned_hours", "target_fund_hours", "difference", "status"]],
        use_container_width=True
    )

# ---------------------------
# KALENDÁR SMIEN
# ---------------------------
st.subheader("Kalendár smien")

employee_colors = {
    "FT_1": "#60a5fa",
    "FT_2": "#3b82f6",
    "FT_3": "#2563eb",
    "FT_4": "#1d4ed8",
    "FT_5": "#93c5fd",
    "FT_6": "#1e40af",
    "PT_1": "#f59e0b",
    "PT_2": "#fbbf24",
    "PT_3": "#d97706",
    "PT_4": "#fcd34d",
    "BR_1": "#ef4444",
    "BR_2": "#f87171",
    "BR_3": "#dc2626",
    "BR_4": "#fca5a5"
}

fig = px.timeline(
    filtered_df.sort_values(["employee", "start"]),
    x_start="start",
    x_end="end",
    y="employee",
    color="employee",
    text="group",
    hover_data=["date", "hours", "day_type", "group"],
    color_discrete_map=employee_colors
)

fig.update_traces(
    textposition="inside",
    insidetextanchor="middle"
)

fig.update_yaxes(autorange="reversed")
fig.update_layout(
    title="2-mesačný plán smien",
    paper_bgcolor="#11182d",
    plot_bgcolor="#11182d",
    font=dict(color="white"),
    height=950,
    legend_title_text="Zamestnanec",
    xaxis_title="Dátum a čas",
    yaxis_title="Zamestnanec",
    margin=dict(l=20, r=20, t=60, b=20)
)

st.plotly_chart(fig, use_container_width=True)

# ---------------------------
# PREHĽAD FONDU HODÍN
# ---------------------------
st.subheader("Fond hodín – 2-mesačný prehľad")
st.dataframe(
    fund_df.sort_values(["employee_type", "employee"]),
    use_container_width=True
)

fund_chart = px.bar(
    fund_df.sort_values(["employee_type", "employee"]),
    x="employee",
    y=["planned_hours", "target_fund_hours"],
    barmode="group",
    title="Porovnanie naplánovaných hodín a cieľového fondu",
    color_discrete_sequence=["#60a5fa", "#f59e0b"]
)

fund_chart.update_layout(
    paper_bgcolor="#11182d",
    plot_bgcolor="#11182d",
    font=dict(color="white"),
    height=520,
    xaxis_title="Zamestnanec",
    yaxis_title="Hodiny",
    margin=dict(l=20, r=20, t=60, b=20)
)

st.plotly_chart(fund_chart, use_container_width=True)

# ---------------------------
# SÚHRNNÁ TABUĽKA PODĽA TYPU ZAMESTNANCA
# ---------------------------
st.subheader("Súhrn podľa typu pracovníka")

summary_by_type = fund_df.groupby("employee_type", as_index=False).agg(
    planned_hours=("planned_hours", "sum"),
    target_fund_hours=("target_fund_hours", "sum"),
    employee_count=("employee", "count")
)
summary_by_type["difference"] = summary_by_type["target_fund_hours"] - summary_by_type["planned_hours"]

st.dataframe(summary_by_type, use_container_width=True)
