import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date
import calendar

st.set_page_config(page_title="Rozvrh pracovníkov", layout="wide")

st.markdown("""
<style>
    .stApp {
        background: linear-gradient(180deg, #0b1020 0%, #11182d 100%);
    }
    .block-container {
        padding-top: 1.2rem;
        padding-bottom: 2rem;
        max-width: 98rem;
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

st.title("Rozvrh pracovníkov")
st.caption("Plánovanie mesiaca, dostupnosť ľudí, dovolenky, náhrady, fairness a fond hodín")

MONTH_NAME_SK = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl",
    5: "Máj", 6: "Jún", 7: "Júl", 8: "August",
    9: "September", 10: "Október", 11: "November", 12: "December"
}
PLANNED_MONTHS = [2, 3, 4, 5, 6, 7, 8]

EMPLOYEES = (
    [{"name": f"FT_{i+1}", "employee_type": "Fulltime"} for i in range(6)]
    + [{"name": f"PT_{i+1}", "employee_type": "Parttime"} for i in range(4)]
    + [{"name": f"BR_{i+1}", "employee_type": "Brigádnik"} for i in range(4)]
)

SHIFT_COLUMNS = [
    "employee", "date", "start", "end", "group", "hours",
    "year", "month", "month_name", "day_type", "assignment_source"
]
WARNING_COLUMNS = ["date", "issue"]
ABSENCE_COLUMNS = ["date", "employee", "status", "replacement"]
REPLACEMENT_COLUMNS = ["date", "missing_employee", "replacement", "replacement_type"]
CATCHUP_COLUMNS = ["employee", "date", "hours_added", "month"]

# -----------------------------------
# Pomocné funkcie
# -----------------------------------
def month_start_end(year: int, month: int):
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)

def get_employee_type(name: str) -> str:
    if name.startswith("FT"):
        return "FT"
    if name.startswith("PT"):
        return "PT"
    return "BR"

def get_weekly_hours(name: str) -> int:
    t = get_employee_type(name)
    if t == "FT":
        return 36
    if t == "PT":
        return 18
    return 16

def get_shift_hours(name: str) -> int:
    t = get_employee_type(name)
    if t == "FT":
        return 12
    if t == "PT":
        return 5
    return 4

def monthly_fund_hours(year: int, month: int, weekly_hours: float) -> float:
    weeks_in_month = calendar.monthcalendar(year, month)
    weekday_count = sum(1 for week in weeks_in_month for day in week[:5] if day != 0)
    daily_hours = weekly_hours / 5
    return round(weekday_count * daily_hours, 1)

def is_weekend(d: date) -> bool:
    return pd.Timestamp(d).weekday() >= 5

def day_requirement(d: date) -> int:
    wd = pd.Timestamp(d).weekday()
    if wd in [4, 5, 6]:
        return 6
    return 5

def preferred_extra_headcount(d: date) -> int:
    wd = pd.Timestamp(d).weekday()
    if wd in [4, 5, 6]:
        return 7
    return 5

def desired_day_mix(d: date):
    wd = pd.Timestamp(d).weekday()
    if wd in [4, 5, 6]:
        return ["FT", "FT", "PT", "PT", "BR", "BR"]
    return ["FT", "FT", "PT", "PT", "BR"]

def employee_shift_template(name: str, parity: int):
    t = get_employee_type(name)
    if t == "FT":
        return {"group": "Fulltime", "start_hour": 9, "end_hour": 21, "hours": 12}
    if t == "PT":
        return {"group": "Parttime", "start_hour": 12, "end_hour": 17, "hours": 5}
    if parity % 2 == 0:
        return {"group": "Brigádnik ráno", "start_hour": 9, "end_hour": 13, "hours": 4}
    return {"group": "Brigádnik večer", "start_hour": 17, "end_hour": 21, "hours": 4}

def staffing_score_color(actual: int, required: int):
    if actual < required:
        return 0
    if actual == required:
        return 1
    if actual == required + 1:
        return 2
    return 3

def staffing_label(actual: int, required: int):
    if actual < required:
        return "Nepokryté"
    if actual == required:
        return "OK"
    if actual == required + 1:
        return "Prebytok"
    return "Vyšší prebytok"

def normalize_range(value, start_d: date, end_d: date):
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return (start_d, start_d)
    s, e = value
    if s is None or e is None:
        return (start_d, start_d)
    if s > e:
        s, e = e, s
    s = max(start_d, min(s, end_d))
    e = max(start_d, min(e, end_d))
    if s > e:
        s = e
    return (s, e)

def daterange_to_set(start_d: date, end_d: date):
    if start_d is None or end_d is None:
        return set()
    if end_d < start_d:
        start_d, end_d = end_d, start_d
    return {start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)}

def slot_preference_rank(slot_type: str, emp_type: str) -> int:
    if slot_type == "FT":
        return 0 if emp_type == "FT" else 99
    if slot_type == "PT":
        return {"PT": 0, "BR": 1, "FT": 2}.get(emp_type, 99)
    return {"BR": 0, "PT": 1, "FT": 2}.get(emp_type, 99)

def projected_consecutive(last_date, current_date, current_consecutive):
    if last_date is not None and (current_date - last_date).days == 1:
        return current_consecutive + 1
    return 1

def make_heatmap_df(source_df: pd.DataFrame, year: int, month: int):
    start_d, end_d = month_start_end(year, month)
    dates = pd.date_range(start_d, end_d, freq="D")

    rows = []
    for dts in dates:
        d = dts.date()
        actual = source_df[source_df["date"] == d]["employee"].nunique()
        required = day_requirement(d)
        preferred = preferred_extra_headcount(d)
        rows.append({
            "date": d,
            "day": d.day,
            "weekday": pd.Timestamp(d).strftime("%a"),
            "actual": actual,
            "required": required,
            "preferred": preferred,
            "score": staffing_score_color(actual, required),
            "label": staffing_label(actual, required)
        })
    return pd.DataFrame(rows)

def render_heatmap(heatmap_df: pd.DataFrame, title: str):
    if heatmap_df.empty:
        st.info("Pre tento výber nie sú dáta.")
        return

    z = [heatmap_df["score"].tolist()]
    text = [[
        f"{row['date']}<br>Ľudia: {row['actual']}<br>Min: {row['required']}<br>Preferované: {row['preferred']}<br>Stav: {row['label']}"
        for _, row in heatmap_df.iterrows()
    ]]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=heatmap_df["day"].tolist(),
        y=["Pokrytie"],
        text=text,
        hoverinfo="text",
        colorscale=[
            [0.00, "#ef4444"],
            [0.33, "#f59e0b"],
            [0.66, "#22c55e"],
            [1.00, "#3b82f6"]
        ],
        zmin=0,
        zmax=3,
        showscale=False
    ))

    fig.update_layout(
        title=title,
        paper_bgcolor="#11182d",
        plot_bgcolor="#11182d",
        font=dict(color="white"),
        height=230,
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis_title="Deň v mesiaci",
        yaxis_title=""
    )
    st.plotly_chart(fig, use_container_width=True)

def build_availability_and_targets(year: int, month: int, employees_df: pd.DataFrame, employee_settings: dict):
    start_d, end_d = month_start_end(year, month)
    month_dates = [start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)]
    month_set = set(month_dates)

    availability_map = {}
    unavailable_map = {}
    target_hours_map = {}
    rows = []

    for emp in employees_df["name"]:
        active = employee_settings[emp]["active"]
        full_target = monthly_fund_hours(year, month, get_weekly_hours(emp))
        daily_target = get_weekly_hours(emp) / 5

        if active:
            vacation_days = set()
            for vac_start, vac_end in employee_settings[emp]["vacations"]:
                vac_start, vac_end = normalize_range((vac_start, vac_end), start_d, end_d)
                vacation_days.update(daterange_to_set(vac_start, vac_end))
            availability = month_set - vacation_days
            unavailable_weekdays = sum(1 for d in vacation_days if d.weekday() < 5)
            adjusted_target = max(0.0, round(full_target - unavailable_weekdays * daily_target, 1))
        else:
            vacation_days = month_set.copy()
            availability = set()
            adjusted_target = 0.0

        availability_map[emp] = availability
        unavailable_map[emp] = month_set - availability
        target_hours_map[emp] = adjusted_target

        rows.append({
            "employee": emp,
            "employee_type": get_employee_type(emp),
            "active": active,
            "vacation_days": len(vacation_days) if active else len(month_set),
            "available_days": len(availability),
            "full_target_hours": full_target,
            "adjusted_target_hours": adjusted_target
        })

    return availability_map, unavailable_map, target_hours_map, pd.DataFrame(rows)

def initialize_stats(employees_df: pd.DataFrame):
    return {
        emp: {
            "hours": 0.0,
            "shifts": 0,
            "weekend_shifts": 0,
            "last_date": None,
            "consecutive": 0
        }
        for emp in employees_df["name"]
    }

def add_shift_record(shifts: list, emp: str, d: date, day_index: int, stats: dict, assignment_source: str = "Plán"):
    parity = day_index + stats[emp]["shifts"]
    tpl = employee_shift_template(emp, parity)
    start_dt = datetime.combine(d, datetime.min.time()).replace(hour=tpl["start_hour"])
    end_dt = datetime.combine(d, datetime.min.time()).replace(hour=tpl["end_hour"])

    shifts.append({
        "employee": emp,
        "date": d,
        "start": start_dt,
        "end": end_dt,
        "group": tpl["group"] if assignment_source == "Plán" else assignment_source,
        "hours": tpl["hours"],
        "year": d.year,
        "month": d.month,
        "month_name": MONTH_NAME_SK[d.month],
        "day_type": "Víkend" if is_weekend(d) else "Pracovný deň",
        "assignment_source": assignment_source
    })

    stats[emp]["hours"] += tpl["hours"]
    stats[emp]["shifts"] += 1
    if is_weekend(d):
        stats[emp]["weekend_shifts"] += 1
    new_consecutive = projected_consecutive(stats[emp]["last_date"], d, stats[emp]["consecutive"])
    stats[emp]["consecutive"] = new_consecutive
    stats[emp]["last_date"] = d

def candidate_sort_key(emp: str, slot_type: str, current_date: date, stats: dict, target_hours_map: dict):
    emp_type = get_employee_type(emp)
    remaining = round(target_hours_map.get(emp, 0.0) - stats[emp]["hours"], 1)
    projected = projected_consecutive(stats[emp]["last_date"], current_date, stats[emp]["consecutive"])
    overload_flag = 0 if remaining > 0 else 1
    weekend_metric = stats[emp]["weekend_shifts"] if pd.Timestamp(current_date).weekday() in [4, 5, 6] else stats[emp]["shifts"]

    return (
        1 if projected > 6 else 0,
        slot_preference_rank(slot_type, emp_type),
        overload_flag,
        -remaining,
        weekend_metric,
        stats[emp]["shifts"],
        stats[emp]["hours"],
        emp
    )

def select_candidate_for_slot(current_date: date, slot_type: str, assigned_today: set, employees_df: pd.DataFrame,
                              availability_map: dict, stats: dict, target_hours_map: dict):
    candidates = []
    for emp in employees_df["name"]:
        if emp in assigned_today:
            continue
        if current_date not in availability_map.get(emp, set()):
            continue
        rank = slot_preference_rank(slot_type, get_employee_type(emp))
        if rank >= 99:
            continue
        candidates.append(emp)

    if not candidates:
        return None

    candidates = sorted(
        candidates,
        key=lambda emp: candidate_sort_key(emp, slot_type, current_date, stats, target_hours_map)
    )
    return candidates[0]

def select_flexible_candidate(current_date: date, assigned_today: set, employees_df: pd.DataFrame,
                              availability_map: dict, stats: dict, target_hours_map: dict):
    candidates = []
    for emp in employees_df["name"]:
        if emp in assigned_today:
            continue
        if current_date not in availability_map.get(emp, set()):
            continue
        remaining = round(target_hours_map.get(emp, 0.0) - stats[emp]["hours"], 1)
        projected = projected_consecutive(stats[emp]["last_date"], current_date, stats[emp]["consecutive"])
        weekend_metric = stats[emp]["weekend_shifts"] if pd.Timestamp(current_date).weekday() in [4, 5, 6] else stats[emp]["shifts"]

        candidates.append((
            1 if projected > 6 else 0,
            0 if remaining > 0 else 1,
            -remaining,
            weekend_metric,
            stats[emp]["shifts"],
            stats[emp]["hours"],
            emp
        ))

    if not candidates:
        return None

    candidates = sorted(candidates)
    return candidates[0][-1]

def generate_monthly_schedule(year: int, month: int, employees_df: pd.DataFrame, availability_map: dict, target_hours_map: dict):
    start_d, end_d = month_start_end(year, month)
    dates = [start_d + timedelta(days=i) for i in range((end_d - start_d).days + 1)]

    stats = initialize_stats(employees_df)
    shifts = []
    warnings = []

    for day_index, current_date in enumerate(dates):
        assigned_today = set()
        required_slots = desired_day_mix(current_date)
        required_headcount = day_requirement(current_date)
        preferred_headcount = preferred_extra_headcount(current_date)

        for slot_type in required_slots:
            candidate = select_candidate_for_slot(
                current_date, slot_type, assigned_today, employees_df, availability_map, stats, target_hours_map
            )
            if candidate is None:
                warnings.append({
                    "date": current_date,
                    "issue": f"Nebolo možné obsadiť slot typu {slot_type}"
                })
                continue

            add_shift_record(shifts, candidate, current_date, day_index, stats, assignment_source="Plán")
            assigned_today.add(candidate)

        while len(assigned_today) < required_headcount:
            candidate = select_flexible_candidate(
                current_date, assigned_today, employees_df, availability_map, stats, target_hours_map
            )
            if candidate is None:
                warnings.append({
                    "date": current_date,
                    "issue": "Nebolo dosť dostupných ľudí na minimálne pokrytie"
                })
                break

            add_shift_record(shifts, candidate, current_date, day_index, stats, assignment_source="Doplnenie pokrytia")
            assigned_today.add(candidate)

        while len(assigned_today) < preferred_headcount:
            candidate = select_flexible_candidate(
                current_date, assigned_today, employees_df, availability_map, stats, target_hours_map
            )
            if candidate is None:
                break

            remaining_gap = target_hours_map.get(candidate, 0.0) - stats[candidate]["hours"]
            if remaining_gap <= 0:
                break

            add_shift_record(shifts, candidate, current_date, day_index, stats, assignment_source="Dobehnutie fondu")
            assigned_today.add(candidate)

    return pd.DataFrame(shifts, columns=SHIFT_COLUMNS), pd.DataFrame(warnings, columns=WARNING_COLUMNS)

def build_monthly_fund_table(source_df: pd.DataFrame, employees_df: pd.DataFrame, year: int, month: int,
                             target_hours_map: dict, availability_summary_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    month_df = source_df[(source_df["year"] == year) & (source_df["month"] == month)].copy()
    planned = month_df.groupby("employee", as_index=False)["hours"].sum().rename(columns={"hours": "planned_hours"})
    availability_lookup = availability_summary_df.set_index("employee").to_dict("index")

    for emp in employees_df["name"]:
        full_target = monthly_fund_hours(year, month, get_weekly_hours(emp))
        adjusted_target = target_hours_map.get(emp, 0.0)
        match = planned[planned["employee"] == emp]["planned_hours"]
        planned_hours = float(match.iloc[0]) if not match.empty else 0.0
        diff = round(adjusted_target - planned_hours, 1)

        if adjusted_target == 0 and planned_hours == 0:
            status = "Neplánuje sa"
        elif diff > 10:
            status = "Pod fondom"
        elif diff < -10:
            status = "Nad fondom"
        else:
            status = "V norme"

        rows.append({
            "employee": emp,
            "employee_type": get_employee_type(emp),
            "active": availability_lookup.get(emp, {}).get("active", True),
            "vacation_days": availability_lookup.get(emp, {}).get("vacation_days", 0),
            "planned_hours": planned_hours,
            "full_target_hours": full_target,
            "adjusted_target_hours": adjusted_target,
            "difference": diff,
            "status": status
        })

    return pd.DataFrame(rows)

def find_best_candidates(df_current: pd.DataFrame, employees_df: pd.DataFrame, missing_shift_row: pd.Series,
                         absent_people: list, unavailable_map: dict, target_hours_map: dict):
    missing_employee = missing_shift_row["employee"]
    missing_type = get_employee_type(missing_employee)
    current_date = missing_shift_row["date"]
    current_month = missing_shift_row["month"]
    current_year = missing_shift_row["year"]
    used_today = set(df_current[df_current["date"] == current_date]["employee"].tolist())

    options = []
    for emp in employees_df["name"]:
        if emp in absent_people:
            continue
        if emp in used_today:
            continue
        if current_date in unavailable_map.get(emp, set()):
            continue

        emp_type = get_employee_type(emp)
        allowed = False

        if missing_type == "FT":
            if emp_type == "FT":
                allowed = True
        elif missing_type == "PT":
            if emp_type in ["PT", "BR"]:
                allowed = True
        elif missing_type == "BR":
            if emp_type in ["BR", "PT"]:
                allowed = True

        if allowed:
            planned_hours = df_current[
                (df_current["employee"] == emp) &
                (df_current["year"] == current_year) &
                (df_current["month"] == current_month)
            ]["hours"].sum()

            target = target_hours_map.get(emp, monthly_fund_hours(current_year, current_month, get_weekly_hours(emp)))
            fund_gap = target - planned_hours

            options.append({
                "employee": emp,
                "employee_type": emp_type,
                "planned_hours": planned_hours,
                "target_fund": target,
                "fund_gap": fund_gap,
                "priority": 2 if emp_type == missing_type else 1
            })

    candidate_df = pd.DataFrame(options)

    pair_df = pd.DataFrame()
    if missing_type == "FT" and not candidate_df.empty:
        pt_candidates = candidate_df[candidate_df["employee_type"] == "PT"].copy()
        if len(pt_candidates) >= 2:
            pair_rows = []
            pt_rows = pt_candidates.to_dict("records")
            for i in range(len(pt_rows)):
                for j in range(i + 1, len(pt_rows)):
                    e1 = pt_rows[i]
                    e2 = pt_rows[j]
                    pair_rows.append({
                        "employee": f"{e1['employee']} + {e2['employee']}",
                        "employee_type": "PT_PAIR",
                        "planned_hours": e1["planned_hours"] + e2["planned_hours"],
                        "target_fund": e1["target_fund"] + e2["target_fund"],
                        "fund_gap": e1["fund_gap"] + e2["fund_gap"],
                        "priority": 1,
                        "emp1": e1["employee"],
                        "emp2": e2["employee"]
                    })
            pair_df = pd.DataFrame(pair_rows)

    if not candidate_df.empty:
        candidate_df = candidate_df.sort_values(
            ["priority", "fund_gap", "planned_hours"],
            ascending=[False, False, True]
        ).copy()

    if not pair_df.empty:
        pair_df = pair_df.sort_values(
            ["fund_gap", "planned_hours"],
            ascending=[False, True]
        ).copy()

    return candidate_df, pair_df

def apply_absences_and_replacements(df_base: pd.DataFrame, employees_df: pd.DataFrame, absent_people: list,
                                    absent_dates: list, unavailable_map: dict, target_hours_map: dict):
    df_after_absence = df_base.copy()
    absence_log = []
    replacement_log = []
    catchup_log = []

    for d in absent_dates:
        for emp in absent_people:
            mask = (df_after_absence["employee"] == emp) & (df_after_absence["date"] == d)
            missing_rows = df_after_absence[mask].copy()

            if missing_rows.empty:
                absence_log.append({
                    "date": d,
                    "employee": emp,
                    "status": "Nemal smenu",
                    "replacement": ""
                })
                continue

            missing_shift = missing_rows.iloc[0]
            df_after_absence = df_after_absence[~mask].copy()

            candidate_df, pair_df = find_best_candidates(
                df_after_absence, employees_df, missing_shift, absent_people, unavailable_map, target_hours_map
            )

            replacement_done = False

            if not candidate_df.empty:
                best = candidate_df.iloc[0]

                if get_employee_type(missing_shift["employee"]) == "FT":
                    use_pair = best["employee_type"] != "FT" and not pair_df.empty
                    if use_pair:
                        pair = pair_df.iloc[0]
                        for emp_pair in [pair["emp1"], pair["emp2"]]:
                            df_after_absence = pd.concat([
                                df_after_absence,
                                pd.DataFrame([{
                                    "employee": emp_pair,
                                    "date": d,
                                    "start": datetime.combine(d, datetime.min.time()).replace(hour=12, minute=0),
                                    "end": datetime.combine(d, datetime.min.time()).replace(hour=17, minute=0),
                                    "group": "Náhrada",
                                    "hours": 5,
                                    "year": d.year,
                                    "month": d.month,
                                    "month_name": MONTH_NAME_SK[d.month],
                                    "day_type": "Víkend" if is_weekend(d) else "Pracovný deň",
                                    "assignment_source": "Náhrada"
                                }])
                            ], ignore_index=True)

                        replacement_log.append({
                            "date": d,
                            "missing_employee": missing_shift["employee"],
                            "replacement": pair["employee"],
                            "replacement_type": "2 PT za 1 FT"
                        })
                        absence_log.append({
                            "date": d,
                            "employee": missing_shift["employee"],
                            "status": "Nahradené",
                            "replacement": pair["employee"]
                        })
                        replacement_done = True

                if not replacement_done:
                    rep_emp = best["employee"]
                    df_after_absence = pd.concat([
                        df_after_absence,
                        pd.DataFrame([{
                            "employee": rep_emp,
                            "date": d,
                            "start": missing_shift["start"],
                            "end": missing_shift["end"],
                            "group": "Náhrada",
                            "hours": missing_shift["hours"],
                            "year": d.year,
                            "month": d.month,
                            "month_name": MONTH_NAME_SK[d.month],
                            "day_type": "Víkend" if is_weekend(d) else "Pracovný deň",
                            "assignment_source": "Náhrada"
                        }])
                    ], ignore_index=True)

                    replacement_log.append({
                        "date": d,
                        "missing_employee": missing_shift["employee"],
                        "replacement": rep_emp,
                        "replacement_type": "1 pracovník"
                    })
                    absence_log.append({
                        "date": d,
                        "employee": missing_shift["employee"],
                        "status": "Nahradené",
                        "replacement": rep_emp
                    })
                    replacement_done = True

            if not replacement_done:
                absence_log.append({
                    "date": d,
                    "employee": missing_shift["employee"],
                    "status": "Nepokryté",
                    "replacement": ""
                })

    for emp in absent_people:
        emp_months = sorted(df_base[df_base["employee"] == emp]["month"].unique().tolist())
        for m in emp_months:
            base_hours = df_base[(df_base["employee"] == emp) & (df_base["month"] == m)]["hours"].sum()
            after_hours = df_after_absence[(df_after_absence["employee"] == emp) & (df_after_absence["month"] == m)]["hours"].sum()
            lost = base_hours - after_hours

            if lost <= 0:
                continue

            month_dates = sorted(df_after_absence[df_after_absence["month"] == m]["date"].unique().tolist())
            for d in month_dates:
                if lost <= 0:
                    break
                if d in unavailable_map.get(emp, set()):
                    continue
                if emp in absent_people and d in absent_dates:
                    continue
                if not df_after_absence[(df_after_absence["employee"] == emp) & (df_after_absence["date"] == d)].empty:
                    continue

                current_hours = df_after_absence[
                    (df_after_absence["employee"] == emp) &
                    (df_after_absence["month"] == m)
                ]["hours"].sum()

                if current_hours >= target_hours_map.get(emp, current_hours):
                    break

                daily_people = df_after_absence[df_after_absence["date"] == d]["employee"].nunique()
                if daily_people >= preferred_extra_headcount(d):
                    continue

                tpl = employee_shift_template(emp, 0)
                df_after_absence = pd.concat([
                    df_after_absence,
                    pd.DataFrame([{
                        "employee": emp,
                        "date": d,
                        "start": datetime.combine(d, datetime.min.time()).replace(hour=tpl["start_hour"]),
                        "end": datetime.combine(d, datetime.min.time()).replace(hour=tpl["end_hour"]),
                        "group": "Dobehnutie hodín",
                        "hours": tpl["hours"],
                        "year": d.year,
                        "month": d.month,
                        "month_name": MONTH_NAME_SK[d.month],
                        "day_type": "Víkend" if is_weekend(d) else "Pracovný deň",
                        "assignment_source": "Dobehnutie hodín"
                    }])
                ], ignore_index=True)

                catchup_log.append({
                    "employee": emp,
                    "date": d,
                    "hours_added": tpl["hours"],
                    "month": m
                })
                lost -= tpl["hours"]

    return (
        df_after_absence.reindex(columns=SHIFT_COLUMNS),
        pd.DataFrame(absence_log, columns=ABSENCE_COLUMNS),
        pd.DataFrame(replacement_log, columns=REPLACEMENT_COLUMNS),
        pd.DataFrame(catchup_log, columns=CATCHUP_COLUMNS)
    )

# -----------------------------------
# Základné nastavenie mesiaca
# -----------------------------------
employees_df = pd.DataFrame(EMPLOYEES)

top1, top2 = st.columns([1, 1])
selected_year = top1.selectbox("Rok plánovania", [2026], index=0)
selected_month = top2.selectbox(
    "Mesiac na plánovanie",
    [MONTH_NAME_SK[m] for m in PLANNED_MONTHS],
    index=0
)
selected_month_num = [m for m, v in MONTH_NAME_SK.items() if v == selected_month][0]
start_d, end_d = month_start_end(selected_year, selected_month_num)

# -----------------------------------
# Sekcia dostupnosti hore
# -----------------------------------
st.subheader("1. Dostupnosť pre plánovaný mesiac")
st.caption("Aktívny pracovník sa plánuje do mesiaca. Dovolenka ho v zadanom intervale úplne vyradí z plánovania a zároveň zníži cieľový fond hodín.")

for emp in employees_df["name"]:
    if f"active_{emp}" not in st.session_state:
        st.session_state[f"active_{emp}"] = True
    if f"vac_count_{emp}" not in st.session_state:
        st.session_state[f"vac_count_{emp}"] = 0
    for i in range(3):
        key = f"vac_range_{emp}_{i}"
        if key not in st.session_state:
            st.session_state[key] = (start_d, start_d)

qa1, qa2, qa3 = st.columns(3)
if qa1.button("Aktivovať všetkých"):
    for emp in employees_df["name"]:
        st.session_state[f"active_{emp}"] = True
if qa2.button("Vypnúť všetkých"):
    for emp in employees_df["name"]:
        st.session_state[f"active_{emp}"] = False
if qa3.button("Vymazať všetky dovolenky"):
    for emp in employees_df["name"]:
        st.session_state[f"vac_count_{emp}"] = 0
        for i in range(3):
            st.session_state[f"vac_range_{emp}_{i}"] = (start_d, start_d)

type_tabs = st.tabs(["FT", "PT", "BR"])
type_map = {
    "FT": [emp for emp in employees_df["name"] if emp.startswith("FT")],
    "PT": [emp for emp in employees_df["name"] if emp.startswith("PT")],
    "BR": [emp for emp in employees_df["name"] if emp.startswith("BR")]
}

for tab, prefix in zip(type_tabs, ["FT", "PT", "BR"]):
    with tab:
        for emp in type_map[prefix]:
            with st.expander(emp, expanded=False):
                c1, c2 = st.columns([1, 2])
                c1.checkbox("Aktívny v mesiaci", key=f"active_{emp}")
                c1.selectbox("Počet dovolenkových intervalov", [0, 1, 2, 3], key=f"vac_count_{emp}")

                vac_count = st.session_state[f"vac_count_{emp}"]
                if vac_count == 0:
                    c2.info("Bez dovolenky v tomto mesiaci.")
                else:
                    for i in range(vac_count):
                        current_value = normalize_range(st.session_state[f"vac_range_{emp}_{i}"], start_d, end_d)
                        st.session_state[f"vac_range_{emp}_{i}"] = current_value
                        c2.date_input(
                            f"Dovolenka {i+1} – {emp}",
                            value=current_value,
                            min_value=start_d,
                            max_value=end_d,
                            key=f"vac_range_{emp}_{i}"
                        )

employee_settings = {}
for emp in employees_df["name"]:
    vacations = []
    vac_count = int(st.session_state[f"vac_count_{emp}"])
    for i in range(vac_count):
        rng = normalize_range(st.session_state[f"vac_range_{emp}_{i}"], start_d, end_d)
        vacations.append(rng)

    employee_settings[emp] = {
        "active": bool(st.session_state[f"active_{emp}"]),
        "vacations": vacations
    }

availability_map, unavailable_map, target_hours_map, availability_summary_df = build_availability_and_targets(
    selected_year, selected_month_num, employees_df, employee_settings
)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Aktívni pracovníci", int(availability_summary_df["active"].sum()))
m2.metric("Dni v mesiaci", (end_d - start_d).days + 1)
m3.metric("Spolu dovolenkových dní", int(availability_summary_df["vacation_days"].sum()))
m4.metric("Plánovaný mesiac", selected_month)

st.dataframe(
    availability_summary_df.sort_values(["employee_type", "employee"]),
    use_container_width=True,
    hide_index=True
)

# -----------------------------------
# Vytvorenie baseline plánu
# -----------------------------------
base_df, planner_warnings_df = generate_monthly_schedule(
    selected_year, selected_month_num, employees_df, availability_map, target_hours_map
)

baseline_heatmap = make_heatmap_df(base_df, selected_year, selected_month_num)

# -----------------------------------
# Sidebar – výpadky a pohľady
# -----------------------------------
st.sidebar.header("Filtrovanie a simulácia")
view_mode = st.sidebar.selectbox("Pohľad kalendára", ["Denný", "Týždenný", "Mesačný", "Celý mesiac"])
selected_day = st.sidebar.date_input(
    "Vybraný deň",
    value=start_d,
    min_value=start_d,
    max_value=end_d
)

employee_list = employees_df["name"].tolist()
available_employee_list = [emp for emp in employee_list if availability_summary_df.set_index("employee").loc[emp, "active"]]

st.sidebar.subheader("Simulácia výpadku pracovníkov")
absent_people = st.sidebar.multiselect("Kto vypadne", available_employee_list, max_selections=3)
absence_range = st.sidebar.date_input(
    "Interval výpadku",
    value=(start_d, start_d),
    min_value=start_d,
    max_value=end_d,
    key="absence_range"
)
absence_start, absence_end = normalize_range(absence_range, start_d, end_d)
absence_dates = sorted(list(daterange_to_set(absence_start, absence_end))) if absent_people else []

# -----------------------------------
# Výpadok bez náhrad
# -----------------------------------
after_absence_df = base_df.copy()
if absent_people:
    mask_absence = after_absence_df.apply(
        lambda r: r["employee"] in absent_people and r["date"] in absence_dates, axis=1
    )
    after_absence_df = after_absence_df[~mask_absence].copy()

after_absence_heatmap = make_heatmap_df(after_absence_df, selected_year, selected_month_num)

# -----------------------------------
# Výpadok + náhrady + dobehnutie
# -----------------------------------
final_df, absence_df, replacement_df, catchup_df = apply_absences_and_replacements(
    base_df, employees_df, absent_people, absence_dates, unavailable_map, target_hours_map
)
final_heatmap = make_heatmap_df(final_df, selected_year, selected_month_num)

# -----------------------------------
# KPI
# -----------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Mesiac", selected_month)
k2.metric("Počet výpadkových ľudí", len(absent_people))
k3.metric("Počet dní výpadku", len(absence_dates))
k4.metric("Naplánovaných smien", len(final_df))

# -----------------------------------
# Upozornenia plánovača
# -----------------------------------
st.subheader("2. Upozornenia plánovača")
if planner_warnings_df.empty:
    st.success("Plánovač nenašiel žiadny zásadný problém pri generovaní základného plánu.")
else:
    st.warning("Niektoré dni alebo sloty nebolo možné obsadiť ideálne. Pozri tabuľku nižšie.")
    st.dataframe(planner_warnings_df, use_container_width=True, hide_index=True)

# -----------------------------------
# Heatmapy
# -----------------------------------
st.subheader("3. Heatmapy pokrytia")
render_heatmap(baseline_heatmap, "1. Základný plán podľa dostupnosti")
render_heatmap(after_absence_heatmap, "2. Stav po výpadku")
render_heatmap(final_heatmap, "3. Stav po náhradách a dobehnutí hodín")

# -----------------------------------
# Denný prehľad
# -----------------------------------
st.subheader("4. Denný prehľad")
daily_df = final_df[final_df["date"] == selected_day].copy()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ľudia v daný deň", daily_df["employee"].nunique())
c2.metric("Smeny v daný deň", len(daily_df))
c3.metric("Hodiny v daný deň", int(daily_df["hours"].sum()) if not daily_df.empty else 0)
c4.metric("Minimálna potreba", day_requirement(selected_day))

st.dataframe(
    daily_df.sort_values(["start", "employee"]),
    use_container_width=True,
    hide_index=True
)

# -----------------------------------
# Coverage tabuľka
# -----------------------------------
st.subheader("5. Coverage podľa dní")
coverage_rows = []
current_date = start_d
while current_date <= end_d:
    actual = final_df[final_df["date"] == current_date]["employee"].nunique()
    required = day_requirement(current_date)
    preferred = preferred_extra_headcount(current_date)
    coverage_rows.append({
        "date": current_date,
        "actual_people": actual,
        "required_people": required,
        "preferred_people": preferred,
        "difference_vs_required": actual - required,
        "difference_vs_preferred": actual - preferred,
        "status": staffing_label(actual, required)
    })
    current_date += timedelta(days=1)

coverage_df = pd.DataFrame(coverage_rows)
st.dataframe(coverage_df, use_container_width=True, hide_index=True)

# -----------------------------------
# Výpadky, náhrady, dobehnutie
# -----------------------------------
st.subheader("6. Výpadky, náhrady a dobehnutie")
left, right = st.columns(2)
with left:
    st.markdown("**Prehľad výpadkov**")
    if absence_df.empty:
        st.info("Žiadne simulované výpadky.")
    else:
        st.dataframe(absence_df, use_container_width=True, hide_index=True)

with right:
    st.markdown("**Odporúčané / použité náhrady**")
    if replacement_df.empty:
        st.info("Žiadne náhrady.")
    else:
        st.dataframe(replacement_df, use_container_width=True, hide_index=True)

st.markdown("**Dobehnutie hodín**")
if catchup_df.empty:
    st.info("Žiadne dobehnutie hodín.")
else:
    st.dataframe(catchup_df, use_container_width=True, hide_index=True)

# -----------------------------------
# Fairness
# -----------------------------------
st.subheader("7. Fairness (spravodlivosť rozdelenia)")
fairness = final_df.groupby("employee").agg(
    total_hours=("hours", "sum"),
    shifts=("employee", "count"),
    weekend_shifts=("day_type", lambda x: (x == "Víkend").sum())
).reset_index()
fairness["employee_type"] = fairness["employee"].apply(get_employee_type)

fairness = fairness.merge(
    availability_summary_df[["employee", "active", "adjusted_target_hours"]],
    on="employee",
    how="left"
)
fairness["difference_vs_target"] = fairness["adjusted_target_hours"] - fairness["total_hours"]

st.dataframe(
    fairness.sort_values(["employee_type", "employee"]),
    use_container_width=True,
    hide_index=True
)

# -----------------------------------
# Fond hodín
# -----------------------------------
st.subheader("8. Fond hodín za mesiac")
fund_df = build_monthly_fund_table(
    final_df, employees_df, selected_year, selected_month_num, target_hours_map, availability_summary_df
)
st.dataframe(
    fund_df.sort_values(["employee_type", "employee"]),
    use_container_width=True,
    hide_index=True
)

total_planned_hours = round(final_df["hours"].sum(), 1)
total_target_hours = round(sum(target_hours_map.values()), 1)
if total_planned_hours < total_target_hours:
    st.warning(
        f"Spolu naplánované hodiny ({total_planned_hours}) sú nižšie ako cieľový fond ({total_target_hours}). "
        "To znamená, že pri aktuálnej dostupnosti a minimálnom pokrytí nie je možné dorovnať všetky fondy úplne."
    )
else:
    st.success(
        f"Spolu naplánované hodiny ({total_planned_hours}) pokrývajú alebo presahujú cieľový fond ({total_target_hours})."
    )

# -----------------------------------
# Export
# -----------------------------------
st.subheader("9. Export")
csv_final = final_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Stiahnuť finálny rozvrh (CSV)",
    data=csv_final,
    file_name=f"rozvrh_{selected_year}_{selected_month_num}.csv",
    mime="text/csv"
)

csv_fund = fund_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Stiahnuť fond hodín (CSV)",
    data=csv_fund,
    file_name=f"fond_hodin_{selected_year}_{selected_month_num}.csv",
    mime="text/csv"
)

# -----------------------------------
# Timeline kalendár dole
# -----------------------------------
st.subheader("10. Timeline kalendár")
plot_df = final_df.copy()

if view_mode == "Denný":
    plot_df = plot_df[plot_df["date"] == selected_day].copy()
elif view_mode == "Týždenný":
    start_week = selected_day - timedelta(days=selected_day.weekday())
    end_week = start_week + timedelta(days=6)
    plot_df = plot_df[(plot_df["date"] >= start_week) & (plot_df["date"] <= end_week)].copy()
elif view_mode == "Mesačný":
    plot_df = plot_df[plot_df["date"].apply(lambda d: d.month == selected_month_num and d.year == selected_year)].copy()

plot_df["color_type"] = plot_df.apply(
    lambda r: "Náhrada" if r["assignment_source"] == "Náhrada"
    else ("Dobehnutie hodín" if r["assignment_source"] == "Dobehnutie hodín" else r["employee"]),
    axis=1
)

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
    "BR_4": "#fca5a5",
    "Náhrada": "#22c55e",
    "Dobehnutie hodín": "#a855f7"
}

if plot_df.empty:
    st.info("Pre tento pohľad nie sú žiadne smeny.")
else:
    fig = px.timeline(
        plot_df.sort_values(["employee", "start"]),
        x_start="start",
        x_end="end",
        y="employee",
        color="color_type",
        text="group",
        hover_data=["date", "hours", "day_type", "month_name", "assignment_source"],
        color_discrete_map=employee_colors
    )

    fig.update_traces(textposition="inside", insidetextanchor="middle")
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(
        title=f"Kalendár smien – {view_mode} pohľad",
        paper_bgcolor="#11182d",
        plot_bgcolor="#11182d",
        font=dict(color="white"),
        height=950,
        legend_title_text="Zamestnanec / typ zásahu",
        xaxis_title="Dátum a čas",
        yaxis_title="Zamestnanec",
        margin=dict(l=20, r=20, t=60, b=20)
    )

    st.plotly_chart(fig, use_container_width=True)
