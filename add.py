import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

st.set_page_config(page_title="Shift Calendar", layout="wide")
st.title("Shift Calendar – Supervisor Dashboard")

start_date = datetime(2026, 3, 23)
days = 14

employees = []

for i in range(6):
    employees.append({"name": f"FT_{i+1}", "type": "Fulltime"})

for i in range(4):
    employees.append({"name": f"PT_{i+1}", "type": "Parttime"})

for i in range(4):
    employees.append({"name": f"BR_{i+1}", "type": "Brigade"})

employees = pd.DataFrame(employees)

shifts = []

for d in range(days):
    date = start_date + timedelta(days=d)

    for _, emp in employees.iterrows():
        if emp["type"] == "Fulltime":
            shifts.append({
                "employee": emp["name"],
                "start": date.replace(hour=9),
                "end": date.replace(hour=21),
                "type": "Fulltime"
            })

        elif emp["type"] == "Parttime":
            shifts.append({
                "employee": emp["name"],
                "start": date.replace(hour=12),
                "end": date.replace(hour=17),
                "type": "Parttime"
            })

        elif emp["type"] == "Brigade":
            if d % 2 == 0:
                shifts.append({
                    "employee": emp["name"],
                    "start": date.replace(hour=9),
                    "end": date.replace(hour=13),
                    "type": "Brigade Morning"
                })
            else:
                shifts.append({
                    "employee": emp["name"],
                    "start": date.replace(hour=17),
                    "end": date.replace(hour=21),
                    "type": "Brigade Evening"
                })

df = pd.DataFrame(shifts)

fig = px.timeline(
    df,
    x_start="start",
    x_end="end",
    y="employee",
    color="type"
)

fig.update_yaxes(autorange="reversed")

st.plotly_chart(fig, use_container_width=True)
