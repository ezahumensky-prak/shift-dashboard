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
st.caption("Heatmapa pokrytia, simulácia výpadkov, náhrady a dobehnutie hodín v mesiaci")

MONTH_NAME_SK = {
    1: "Január", 2: "Február", 3: "Marec", 4: "Apríl",
    5: "Máj", 6: "Jún", 7: "Júl", 8: "August",
    9: "September", 10: "Október", 11: "November", 12: "December"
}
PLANNED_MONTHS = [2, 3, 4, 5, 6, 7, 8]

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

def monthly_fund_hours(year: int, month: int, weekly_hours: float) -> float:
    weeks_in_month = calendar.monthcalendar(year, month)
    weekday_count = sum(1 for week in weeks_in_month for day in week[:5] if day != 0)
    daily_hours = weekly_hours / 5
    return round(weekday_count * daily_hours, 1)

def is_weekend(d: date) -> bool:
    return pd.Timestamp(d).weekday() >= 5

def day_requirement(d: date) -> int:
    # Piatok, sobota, nedeľa => min 6, inak min 5
    wd = pd.Timestamp(d).weekday()
    if wd in [4, 5, 6]:
        return 6
    return 5

def preferred_extra_headcount(d: date) -> int:
    wd = pd.Timestamp(d).weekday()
    if wd in [4, 5, 6]:
        return 7
    return 5

def employee_shift_template(name: str, parity: int):
    # parity používame na rotáciu BR ráno/večer
    t = get_employee_type(name)
    if t == "FT":
        return {"group": "Fulltime", "start_hour": 9, "end_hour": 21, "hours": 12}
    if t == "PT":
        return {"group": "Parttime", "start_hour": 12, "end_hour": 17, "hours": 5}
    # BR
    if parity % 2 == 0:
        return {"group": "Brigádnik ráno", "start_hour": 9, "end_hour": 13, "hours": 4}
    return {"group": "Brigádnik večer", "start_hour": 17, "end_hour": 21, "hours": 4}

def build_monthly_fund_table(source_df: pd.DataFrame, employees_df: pd.DataFrame, year: int, month: int) -> pd.DataFrame:
    rows = []
    month_df = source_df[(source_df["year"] == year) & (source_df["month"] == month)].copy()
    planned = month_df.groupby("employee", as_index=False)["hours"].sum().rename(columns={"hours": "planned_hours"})

    for emp in employees_df["name"]:
        wh = get_weekly_hours(emp)
        target = monthly_fund_hours(year, month, wh)
        match = planned[planned["employee"] == emp]["planned_hours"]
        ph = float(match.iloc[0]) if not match.empty else 0.0
        diff = round(target - ph, 1)

        if diff > 10:
            status = "Pod fondom"
        elif diff < -10:
            status = "Nad fondom"
        else:
            status = "V norme"

        rows.append({
            "employee": emp,
            "employee_type": get_employee_type(emp),
            "planned_hours": ph,
            "target_fund_hours": target,
            "difference": diff,
            "status": status
        })

    return pd.DataFrame(rows)

def staffing_score_color(actual: int, required: int):
    if actual < required:
        return 0  # červená
    if actual == required:
        return 1  # zelená
    if actual == required + 1:
        return 2  # modrá (mierny prebytok)
    return 3      # modrá silnejšie / nadstav

def staffing_label(actual: int, required: int):
    if actual < required:
        return "Nepokryté"
    if actual == required:
        return "OK"
    if actual == required + 1:
        return "Prebytok"
    return "Vyšší prebytok"

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

    # 1 riadok, dni v mesiaci na osi x
    z = [heatmap_df["score"].tolist()]
    text = [[f"{row['date']}<br>Ľudia: {row['actual']}<br>Min: {row['required']}<br>Stav: {row['label']}" for _, row in heatmap_df.iterrows()]]

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=heatmap_df["day"].tolist(),
        y=["Pokrytie"],
        text=text,
        hoverinfo="text",
        colorscale=[
            [0.00, "#ef4444"],  # červená
            [0.33, "#f59e0b"],  # oranžová
            [0.66, "#22c55e"],  # zelená
            [1.00, "#3b82f6"]   # modrá
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

def generate_base_schedule(year: int, month: int, employees_df: pd.DataFrame):
    ft_names = employees_df[employees_df["employee_type"] == "Fulltime"]["name"].tolist()
    pt_names = employees_df[employees_df["employee_type"] == "Parttime"]["name"].tolist()
    br_names = employees_df[employees_df["employee_type"] == "Brigádnik"]["name"].tolist()

    shifts = []
    start_d, end_d = month_start_end(year, month)
    current_date = start_d
    day_index = 0

    while current_date <= end_d:
        # baseline: 2 FT, 2 PT, 2 BR
        ft_today = [ft_names[(2 * day_index) % len(ft_names)], ft_names[(2 * day_index + 1) % len(ft_names)]]
        pt_today = [pt_names[(2 * day_index) % len(pt_names)], pt_names[(2 * day_index + 1) % len(pt_names)]]
        br_today = [br_names[(2 * day_index) % len(br_names)], br_names[(2 * day_index + 1) % len(br_names)]]

        for name in ft_today:
            tpl = employee_shift_template(name, day_index)
            shifts.append({
                "employee": name,
                "date": current_date,
                "start": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["start_hour"]),
                "end": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["end_hour"]),
                "group": tpl["group"],
                "hours": tpl["hours"],
                "year": current_date.year,
                "month": current_date.month,
                "month_name": MONTH_NAME_SK[current_date.month],
                "day_type": "Víkend" if is_weekend(current_date) else "Pracovný deň"
            })

        for name in pt_today:
            tpl = employee_shift_template(name, day_index)
            shifts.append({
                "employee": name,
                "date": current_date,
                "start": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["start_hour"]),
                "end": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["end_hour"]),
                "group": tpl["group"],
                "hours": tpl["hours"],
                "year": current_date.year,
                "month": current_date.month,
                "month_name": MONTH_NAME_SK[current_date.month],
                "day_type": "Víkend" if is_weekend(current_date) else "Pracovný deň"
            })

        for idx, name in enumerate(br_today):
            parity = day_index + idx
            tpl = employee_shift_template(name, parity)
            shifts.append({
                "employee": name,
                "date": current_date,
                "start": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["start_hour"]),
                "end": datetime.combine(current_date, datetime.min.time()).replace(hour=tpl["end_hour"]),
                "group": tpl["group"],
                "hours": tpl["hours"],
                "year": current_date.year,
                "month": current_date.month,
                "month_name": MONTH_NAME_SK[current_date.month],
                "day_type": "Víkend" if is_weekend(current_date) else "Pracovný deň"
            })

        current_date += timedelta(days=1)
        day_index += 1

    return pd.DataFrame(shifts)

def parse_date_lines(text: str):
    dates = set()
    if not text.strip():
        return dates
    for part in text.replace(";", "\n").splitlines():
        part = part.strip()
        if not part:
            continue
        try:
            dates.add(pd.to_datetime(part).date())
        except Exception:
            pass
    return dates

def build_unavailability_map(employees_list, vacations_text_map, offdays_text_map):
    unavailable = {emp: set() for emp in employees_list}
    for emp in employees_list:
        unavailable[emp].update(parse_date_lines(vacations_text_map.get(emp, "")))
        unavailable[emp].update(parse_date_lines(offdays_text_map.get(emp, "")))
    return unavailable

def apply_manual_unavailability(df: pd.DataFrame, unavailable_map: dict):
    out = df.copy()
    mask_remove = out.apply(lambda r: r["date"] in unavailable_map.get(r["employee"], set()), axis=1)
    removed = out[mask_remove].copy()
    out = out[~mask_remove].copy()
    return out, removed

def find_best_candidates(df_current: pd.DataFrame, employees_df: pd.DataFrame, missing_shift_row: pd.Series, absent_people: list):
    missing_employee = missing_shift_row["employee"]
    missing_type = get_employee_type(missing_employee)
    current_date = missing_shift_row["date"]
    current_month = missing_shift_row["month"]
    current_year = missing_shift_row["year"]
    used_today = set(df_current[df_current["date"] == current_date]["employee"].tolist())

    # kto môže nahradiť
    options = []
    for emp in employees_df["name"]:
        if emp in absent_people:
            continue
        if emp in used_today:
            continue
        emp_type = get_employee_type(emp)

        allowed = False
        combo_type = "single"

        if missing_type == "FT":
            if emp_type == "FT":
                allowed = True
                combo_type = "FT"
        elif missing_type == "PT":
            if emp_type in ["PT", "BR"]:
                allowed = True
                combo_type = emp_type
        elif missing_type == "BR":
            if emp_type in ["BR", "PT"]:
                allowed = True
                combo_type = emp_type

        if allowed:
            planned_hours = df_current[
                (df_current["employee"] == emp) &
                (df_current["year"] == current_year) &
                (df_current["month"] == current_month)
            ]["hours"].sum()
            target = monthly_fund_hours(current_year, current_month, get_weekly_hours(emp))
            fund_gap = target - planned_hours

            options.append({
                "employee": emp,
                "employee_type": emp_type,
                "planned_hours": planned_hours,
                "target_fund": target,
                "fund_gap": fund_gap,
                "priority": 2 if emp_type == missing_type else 1,
                "combo_type": combo_type
            })

    candidate_df = pd.DataFrame(options)

    # špeciálne pravidlo FT -> 2 PT
    pair_df = pd.DataFrame()
    if missing_type == "FT":
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
                        "combo_type": "PT_PAIR",
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

def apply_absences_and_replacements(df_base: pd.DataFrame, employees_df: pd.DataFrame, absent_people: list, absent_dates: list):
    df_after_absence = df_base.copy()
    absence_log = []
    replacement_log = []
    catchup_log = []

    # 1. odstránenie smien vypadnutých ľudí
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

            candidate_df, pair_df = find_best_candidates(df_after_absence, employees_df, missing_shift, absent_people)

            replacement_done = False

            # Preferencia: rovnaký typ, potom fond
            if not candidate_df.empty:
                best = candidate_df.iloc[0]

                # ak FT nie je k dispozícii a existuje pár PT, porovnáme
                if get_employee_type(missing_shift["employee"]) == "FT":
                    use_pair = False
                    if best["employee_type"] != "FT" and not pair_df.empty:
                        use_pair = True

                    if use_pair:
                        pair = pair_df.iloc[0]
                        for emp_pair in [pair["emp1"], pair["emp2"]]:
                            tpl = employee_shift_template(emp_pair, 0)
                            # 2 PT za 1 FT = priradíme obom PT smenu 12-17, plus poznámka náhrada
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
                                    "day_type": "Víkend" if is_weekend(d) else "Pracovný deň"
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
                    # náhradník berie pôvodnú smenu
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
                            "day_type": "Víkend" if is_weekend(d) else "Pracovný deň"
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

    # 2. dobehnutie hodín pre vypadnutých v rámci mesiaca
    # nájdeme, koľko hodín chýba absent people oproti baseline
    for emp in absent_people:
        emp_type = get_employee_type(emp)
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
                if emp in absent_people and d in absent_dates:
                    continue

                # ak ten deň už emp robí, preskočíme
                if not df_after_absence[(df_after_absence["employee"] == emp) & (df_after_absence["date"] == d)].empty:
                    continue

                # len ak je deň pod preferred staffing alebo aspoň priestor
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
                        "day_type": "Víkend" if is_weekend(d) else "Pracovný deň"
                    }])
                ], ignore_index=True)

                catchup_log.append({
                    "employee": emp,
                    "date": d,
                    "hours_added": tpl["hours"],
                    "month": m
                })
                lost -= tpl["hours"]

    return df_after_absence, pd.DataFrame(absence_log), pd.DataFrame(replacement_log), pd.DataFrame(catchup_log)

# -----------------------------------
# Sidebar vstupy
# -----------------------------------
selected_year = st.sidebar.selectbox("Rok", [2025, 2026, 2027], index=1)
selected_month = st.sidebar.selectbox(
    "Mesiac na plánovanie",
    [MONTH_NAME_SK[m] for m in PLANNED_MONTHS],
    index=0
)
selected_month_num = [m for m, v in MONTH_NAME_SK.items() if v == selected_month][0]

view_mode = st.sidebar.selectbox("Pohľad kalendára", ["Denný", "Týždenný", "Mesačný", "Celý mesiac"])
selected_day = st.sidebar.date_input("Vybraný deň", date(selected_year, selected_month_num, 1))

employee_list = [f"FT_{i+1}" for i in range(6)] + [f"PT_{i+1}" for i in range(4)] + [f"BR_{i+1}" for i in range(4)]

st.sidebar.subheader("Výpadok pracovníkov")
absent_people = st.sidebar.multiselect("Kto vypadne", employee_list, max_selections=3)
absence_start = st.sidebar.date_input("Začiatok výpadku", date(selected_year, selected_month_num, 1), key="abs_start")
absence_days = st.sidebar.slider("Počet dní výpadku", 1, 14, 1)
absence_dates = [absence_start + timedelta(days=i) for i in range(absence_days)]

st.sidebar.subheader("Dovolenky / offdays")
with st.sidebar.expander("Ručný vstup dostupnosti"):
    st.caption("Zadávaj po riadkoch vo formáte YYYY-MM-DD")

    vacations_text = {}
    offdays_text = {}
    for emp in employee_list:
        vacations_text[emp] = st.text_area(f"Dovolenka – {emp}", value="", height=80, key=f"vac_{emp}")
        offdays_text[emp] = st.text_area(f"Offday – {emp}", value="", height=80, key=f"off_{emp}")

# -----------------------------------
# Vytvorenie baseline plánu
# -----------------------------------
employees = []
for i in range(6):
    employees.append({"name": f"FT_{i+1}", "employee_type": "Fulltime"})
for i in range(4):
    employees.append({"name": f"PT_{i+1}", "employee_type": "Parttime"})
for i in range(4):
    employees.append({"name": f"BR_{i+1}", "employee_type": "Brigádnik"})
employees_df = pd.DataFrame(employees)

base_df = generate_base_schedule(selected_year, selected_month_num, employees_df)

# Aplikácia dovoleniek a offdays ešte pred baseline heatmapou
unavailable_map = build_unavailability_map(employee_list, vacations_text, offdays_text)
base_available_df, removed_manual_df = apply_manual_unavailability(base_df, unavailable_map)

# Heatmapa baseline
baseline_heatmap = make_heatmap_df(base_available_df, selected_year, selected_month_num)

# Výpadok bez náhrad
after_absence_df = base_available_df.copy()
if absent_people:
    mask_absence = after_absence_df.apply(lambda r: r["employee"] in absent_people and r["date"] in absence_dates, axis=1)
    after_absence_df = after_absence_df[~mask_absence].copy()

after_absence_heatmap = make_heatmap_df(after_absence_df, selected_year, selected_month_num)

# Výpadok + náhrady + dobehnutie
final_df, absence_df, replacement_df, catchup_df = apply_absences_and_replacements(
    base_available_df, employees_df, absent_people, absence_dates
)
final_heatmap = make_heatmap_df(final_df, selected_year, selected_month_num)

# -----------------------------------
# KPI
# -----------------------------------
k1, k2, k3, k4 = st.columns(4)
k1.metric("Mesiac", selected_month)
k2.metric("Počet výpadkových ľudí", len(absent_people))
k3.metric("Počet dní výpadku", len(absence_dates))
k4.metric("Ručne zadané nedostupnosti", len(removed_manual_df))

# -----------------------------------
# Heatmapy
# -----------------------------------
st.subheader("Heatmapy pokrytia")

render_heatmap(baseline_heatmap, "1. Baseline stav")
render_heatmap(after_absence_heatmap, "2. Stav po výpadku")
render_heatmap(final_heatmap, "3. Stav po náhradách a dobehnutí hodín")

# -----------------------------------
# Denný prehľad
# -----------------------------------
st.subheader("Denný prehľad")

daily_df = final_df[final_df["date"] == selected_day].copy()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Ľudia v daný deň", daily_df["employee"].nunique())
c2.metric("Smeny v daný deň", len(daily_df))
c3.metric("Hodiny v daný deň", int(daily_df["hours"].sum()) if not daily_df.empty else 0)
c4.metric("Minimálna potreba", day_requirement(selected_day))

st.dataframe(daily_df.sort_values(["start", "employee"]), use_container_width=True)

# -----------------------------------
# Coverage tabuľka
# -----------------------------------
st.subheader("Coverage podľa dní")

coverage_rows = []
start_d, end_d = month_start_end(selected_year, selected_month_num)
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
st.dataframe(coverage_df, use_container_width=True)

# -----------------------------------
# Výpadky, náhrady, dobehnutie
# -----------------------------------
st.subheader("Prehľad výpadkov")
st.dataframe(absence_df, use_container_width=True)

st.subheader("Odporúčané / použité náhrady")
st.dataframe(replacement_df, use_container_width=True)

st.subheader("Dobehnutie hodín")
st.dataframe(catchup_df, use_container_width=True)

# -----------------------------------
# Fairness
# -----------------------------------
st.subheader("Fairness (spravodlivosť rozdelenia)")
fairness = final_df.groupby("employee").agg(
    total_hours=("hours", "sum"),
    shifts=("employee", "count"),
    weekend_shifts=("day_type", lambda x: (x == "Víkend").sum())
).reset_index()
fairness["employee_type"] = fairness["employee"].apply(get_employee_type)
st.dataframe(fairness.sort_values(["employee_type", "employee"]), use_container_width=True)

# -----------------------------------
# Fond hodín
# -----------------------------------
st.subheader("Fond hodín za mesiac")
fund_df = build_monthly_fund_table(final_df, employees_df, [selected_month_num], selected_year)
st.dataframe(fund_df.sort_values(["employee_type", "employee"]), use_container_width=True)

# -----------------------------------
# Export
# -----------------------------------
st.subheader("Export")
csv_final = final_df.to_csv(index=False).encode("utf-8")
st.download_button(
    "Stiahnuť finálny rozvrh (CSV)",
    data=csv_final,
    file_name=f"rozvrh_{selected_year}_{selected_month_num}.csv",
    mime="text/csv"
)

# -----------------------------------
# Timeline kalendár dole
# -----------------------------------
st.subheader("Timeline kalendár")

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
    lambda r: "Náhrada" if r["group"] == "Náhrada"
    else ("Dobehnutie hodín" if r["group"] == "Dobehnutie hodín" else r["employee"]),
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

fig = px.timeline(
    plot_df.sort_values(["employee", "start"]),
    x_start="start",
    x_end="end",
    y="employee",
    color="color_type",
    text="group",
    hover_data=["date", "hours", "day_type", "month_name"],
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
