import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta, date
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
        max-width: 96rem;
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
st.caption("Plán smien od februára do augusta, mesačný fond hodín a náhrady pri výpadku")

DEFAULT_YEAR = 2026
MONTHS_TO_PLAN = [2, 3, 4, 5, 6, 7, 8]
MONTH_NAME_SK = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl",
    5: "Máj", 6: "Jún", 7: "Júl", 8: "August",
    9: "September", 10: "Október", 11: "November", 12: "December"
}

def month_start_end(year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)

def get_weekly_hours(name: str) -> int:
    if name.startswith("FT"):
        return 36
    return 18

def monthly_fund_hours(year: int, month: int, weekly_hours: float) -> float:
    weeks_in_month = calendar.monthcalendar(year, month)
    weekday_count = sum(1 for week in weeks_in_month for day in week[:5] if day != 0)
    daily_hours = weekly_hours / 5
    return round(weekday_count * daily_hours, 1)

def get_employee_type(name: str) -> str:
    if name.startswith("FT"):
        return "Fulltime"
    if name.startswith("PT"):
        return "Parttime"
    return "Brigádnik"

def is_weekend(date_value) -> bool:
    return pd.Timestamp(date_value).weekday() >= 5

def build_monthly_fund_table(source_df: pd.DataFrame, employees_df: pd.DataFrame, months: list[int], year: int) -> pd.DataFrame:
    rows = []

    monthly_hours = (
        source_df.groupby(["employee", "year", "month"], as_index=False)["hours"]
        .sum()
        .rename(columns={"hours": "planned_hours"})
    )

    for emp in employees_df["name"]:
        weekly_hours = get_weekly_hours(emp)
        emp_type = get_employee_type(emp)

        for month in months:
            planned_match = monthly_hours[
                (monthly_hours["employee"] == emp) &
                (monthly_hours["year"] == year) &
                (monthly_hours["month"] == month)
            ]["planned_hours"]

            planned_hours = float(planned_match.iloc[0]) if not planned_match.empty else 0.0
            target_fund = monthly_fund_hours(year, month, weekly_hours)
            difference = round(target_fund - planned_hours, 1)

            if difference > 10:
                status = "Pod fondom"
            elif difference < -10:
                status = "Nad fondom"
            else:
                status = "V norme"

            rows.append({
                "employee": emp,
                "employee_type": emp_type,
                "year": year,
                "month": month,
                "month_name": MONTH_NAME_SK[month],
                "planned_hours": planned_hours,
                "target_fund_hours": target_fund,
                "difference": difference,
                "status": status
            })

    return pd.DataFrame(rows)

employees = []

for i in range(6):
    employees.append({
        "name": f"FT_{i+1}",
        "employee_type": "Fulltime",
        "weekly_hours": 36
    })

for i in range(4):
    employees.append({
        "name": f"PT_{i+1}",
        "employee_type": "Parttime",
        "weekly_hours": 18
    })

for i in range(4):
    employees.append({
        "name": f"BR_{i+1}",
        "employee_type": "Brigádnik",
        "weekly_hours": 18
    })

employees = pd.DataFrame(employees)

st.sidebar.header("Nastavenia")

selected_year = st.sidebar.selectbox("Rok", [2025, 2026, 2027], index=1)

selected_groups = st.sidebar.multiselect(
    "Zobraziť typy smien",
    ["Fulltime", "Parttime", "Brigádnik ráno", "Brigádnik večer", "Náhrada"],
    default=["Fulltime", "Parttime", "Brigádnik ráno", "Brigádnik večer", "Náhrada"]
)

selected_months = st.sidebar.multiselect(
    "Zobraziť mesiace",
    [MONTH_NAME_SK[m] for m in MONTHS_TO_PLAN],
    default=[MONTH_NAME_SK[m] for m in MONTHS_TO_PLAN]
)
selected_month_numbers = [m for m in MONTHS_TO_PLAN if MONTH_NAME_SK[m] in selected_months]

show_weekends_only = st.sidebar.checkbox("Zobraziť len víkendy", value=False)

employee_options_base = sorted(employees["name"].tolist())
selected_employees = st.sidebar.multiselect(
    "Výpadok zamestnancov",
    employee_options_base
)

absence_start_date = st.sidebar.date_input(
    "Začiatok výpadku",
    date(selected_year, 2, 1)
)

absence_days = st.sidebar.slider(
    "Počet dní výpadku",
    min_value=1,
    max_value=14,
    value=1
)

absence_end_date = absence_start_date + timedelta(days=absence_days - 1)
st.sidebar.caption(f"Výpadok bude od {absence_start_date} do {absence_end_date}")

shifts = []

ft_names = employees[employees["employee_type"] == "Fulltime"]["name"].tolist()
pt_names = employees[employees["employee_type"] == "Parttime"]["name"].tolist()
br_names = employees[employees["employee_type"] == "Brigádnik"]["name"].tolist()

day_index = 0
for month in MONTHS_TO_PLAN:
    start_d, end_d = month_start_end(selected_year, month)
    current_date = start_d

    while current_date <= end_d:
        ft_today = [ft_names[(2 * day_index) % len(ft_names)], ft_names[(2 * day_index + 1) % len(ft_names)]]
        pt_today = [pt_names[(2 * day_index) % len(pt_names)], pt_names[(2 * day_index + 1) % len(pt_names)]]
        br_today = [br_names[(2 * day_index) % len(br_names)], br_names[(2 * day_index + 1) % len(br_names)]]

        for name in ft_today:
            shifts.append({
                "employee": name,
                "date": current_date,
                "start": datetime.combine(current_date, datetime.min.time()).replace(hour=9, minute=0),
                "end": datetime.combine(current_date, datetime.min.time()).replace(hour=21, minute=0),
                "group": "Fulltime",
                "hours": 12,
                "year": current_date.year,
                "month": current_date.month,
                "month_name": MONTH_NAME_SK[current_date.month]
            })

        for name in pt_today:
            shifts.append({
                "employee": name,
                "date": current_date,
                "start": datetime.combine(current_date, datetime.min.time()).replace(hour=12, minute=0),
                "end": datetime.combine(current_date, datetime.min.time()).replace(hour=17, minute=0),
                "group": "Parttime",
                "hours": 5,
                "year": current_date.year,
                "month": current_date.month,
                "month_name": MONTH_NAME_SK[current_date.month]
            })

        for idx, name in enumerate(br_today):
            if idx == 0:
                shifts.append({
                    "employee": name,
                    "date": current_date,
                    "start": datetime.combine(current_date, datetime.min.time()).replace(hour=9, minute=0),
                    "end": datetime.combine(current_date, datetime.min.time()).replace(hour=13, minute=0),
                    "group": "Brigádnik ráno",
                    "hours": 4,
                    "year": current_date.year,
                    "month": current_date.month,
                    "month_name": MONTH_NAME_SK[current_date.month]
                })
            else:
                shifts.append({
                    "employee": name,
                    "date": current_date,
                    "start": datetime.combine(current_date, datetime.min.time()).replace(hour=17, minute=0),
                    "end": datetime.combine(current_date, datetime.min.time()).replace(hour=21, minute=0),
                    "group": "Brigádnik večer",
                    "hours": 4,
                    "year": current_date.year,
                    "month": current_date.month,
                    "month_name": MONTH_NAME_SK[current_date.month]
                })

        current_date += timedelta(days=1)
        day_index += 1

df = pd.DataFrame(shifts)
df["day_type"] = df["date"].apply(lambda x: "Víkend" if is_weekend(x) else "Pracovný deň")

filtered_df = df.copy()

if selected_month_numbers:
    filtered_df = filtered_df[filtered_df["month"].isin(selected_month_numbers)].copy()

if show_weekends_only:
    filtered_df = filtered_df[filtered_df["day_type"] == "Víkend"].copy()

replacement_rows = []
absence_messages = []

if selected_employees:
    absence_dates = [absence_start_date + timedelta(days=i) for i in range(absence_days)]

    for current_absence_date in absence_dates:
        for selected_employee in selected_employees:
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
                    "status": "Nemal smenu"
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

            candidates = employees.copy()
            candidates = candidates[~candidates["name"].isin(used_today)].copy()
            candidates["candidate_type"] = candidates["name"].apply(get_employee_type)
            candidates = candidates[candidates["candidate_type"].isin(allowed_candidate_types)].copy()
            candidates = candidates[~candidates["name"].isin(selected_employees)].copy()

            candidate_rows = []

            for _, row in candidates.iterrows():
                c_name = row["name"]
                c_type = row["candidate_type"]
                c_wh = get_weekly_hours(c_name)

                planned_match = filtered_df[
                    (filtered_df["employee"] == c_name) &
                    (filtered_df["year"] == current_absence_date.year) &
                    (filtered_df["month"] == current_absence_date.month)
                ]["hours"].sum()

                month_fund = monthly_fund_hours(current_absence_date.year, current_absence_date.month, c_wh)
                fund_gap = month_fund - planned_match
                priority_score = 2 if c_type == get_employee_type(selected_employee) else 1

                candidate_rows.append({
                    "name": c_name,
                    "candidate_type": c_type,
                    "planned_hours": planned_match,
                    "current_month_fund": month_fund,
                    "fund_gap": fund_gap,
                    "priority_score": priority_score
                })

            candidates = pd.DataFrame(candidate_rows)

            if not candidates.empty:
                candidates = candidates.sort_values(
                    ["priority_score", "fund_gap", "planned_hours"],
                    ascending=[False, False, True]
                ).copy()

                top_candidates = candidates[["name", "candidate_type", "planned_hours", "current_month_fund", "fund_gap"]].head(3).copy()
                top_candidates["date"] = current_absence_date
                top_candidates["missing_employee"] = selected_employee
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
                        "year": current_absence_date.year,
                        "month": current_absence_date.month,
                        "month_name": MONTH_NAME_SK[current_absence_date.month],
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

filtered_df = filtered_df[filtered_df["group"].isin(selected_groups)].copy()

col1, col2, col3, col4 = st.columns(4)

total_shifts = len(filtered_df)
total_hours = int(filtered_df["hours"].sum())
scheduled_people = filtered_df["employee"].nunique()
weekend_shifts = len(filtered_df[filtered_df["day_type"] == "Víkend"])

col1.metric("Naplánované smeny", total_shifts)
col2.metric("Naplánované hodiny", total_hours)
col3.metric("Nasadení ľudia", scheduled_people)
col4.metric("Víkendové smeny", weekend_shifts)

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
        "planned_hours": "Naplánované hodiny v mesiaci",
        "current_month_fund": "Mesačný fond",
        "fund_gap": "Rezerva do fondu",
        "date": "Dátum",
        "missing_employee": "Vypadol"
    })
    st.subheader("Top odporúčaní náhradníci podľa dní")
    st.dataframe(replacement_table, use_container_width=True)

fund_df = build_monthly_fund_table(filtered_df, employees, selected_month_numbers, selected_year)

st.subheader("Mesačné alerty fondu hodín")

month_alerts = fund_df.groupby(["month_name", "status"], as_index=False).size().rename(columns={"size": "count"})
st.dataframe(month_alerts, use_container_width=True)

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
    hover_data=["date", "hours", "day_type", "month_name"],
    color_discrete_map=employee_colors
)

fig.update_traces(textposition="inside", insidetextanchor="middle")
fig.update_yaxes(autorange="reversed")
fig.update_layout(
    title=f"Plán smien od februára do augusta {selected_year}",
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

st.subheader("Fond hodín podľa kalendárnych mesiacov")
st.dataframe(
    fund_df.sort_values(["month", "employee_type", "employee"]),
    use_container_width=True
)
