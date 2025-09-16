# app.py
import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import date, datetime
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="Accounting — gsheets-connection", layout="centered")

st.title("Quick Accounting — Streamlit GSheetsConnection")

# Create connection object (this reads the connection configured in Streamlit secrets)
conn = st.connection("gsheets", type=GSheetsConnection)

# Helper: read the entire worksheet as a DataFrame
def load_sheet_df():
    # read entire worksheet "Transactions" (worksheet argument expects a title or gid)
    try:
        df = conn.read(worksheet="Transactions")
    except Exception as e:
        st.error(f"Could not read sheet: {e}")
        st.stop()
    # ensure columns exist and dtypes
    if df is None or df.empty:
        df = pd.DataFrame(columns=["txn_date","type","amount","payment_mode","description","account","sub_account","created_at"])
    else:
        if "txn_date" in df.columns:
            df["txn_date"] = pd.to_datetime(df["txn_date"], errors="coerce").dt.date
        if "amount" in df.columns:
            df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df

# Make entry form compact for mobile
st.markdown("**New transaction**")
with st.form("txn_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        txn_date = st.date_input("Date", value=date.today())
        txn_type = st.selectbox("Type", ["debit", "credit"])
        amount = st.number_input("Amount", min_value=0.0, format="%.2f", step=1.0)
    with c2:
        payment_mode = st.selectbox("Mode", ["cash", "bank", "upi", "card", "other"])
        account_choice = st.text_input("Account (type here)", value="")
        sub_account = st.text_input("Sub-account (optional)")
        description = st.text_input("Description")
    submitted = st.form_submit_button("Save")

    if submitted:
        account = account_choice.strip()
        created_at = datetime.utcnow().isoformat()
        # Row must align with header order used in sheet
        row = {
            "txn_date": txn_date.isoformat(),
            "type": txn_type,
            "amount": f"{amount:.2f}",
            "payment_mode": payment_mode,
            "description": description,
            "account": account,
            "sub_account": sub_account,
            "created_at": created_at,
        }
        try:
            # Append row to the Transactions worksheet. `conn.append` will add as a new row.
            conn.append(worksheet="Transactions", values=[row])
            st.success("Saved to Google Sheets ✅")
        except Exception as e:
            st.error(f"Failed to append to sheet: {e}")

# --- Summary area (carry forward + month totals) ---
st.markdown("---")
st.subheader("Summary")

df = load_sheet_df()
if not df.empty:
    accounts = sorted(df["account"].dropna().unique().tolist())
    sel_account = st.selectbox("Account", ["-- All --"] + accounts)
    month_picker = st.date_input("Month (pick any date in month)", value=date.today())

    first_day = month_picker.replace(day=1)
    next_month = (first_day + relativedelta(months=1)).replace(day=1)

    if sel_account == "-- All --":
        df_account = df
    else:
        df_account = df[df["account"] == sel_account]

    df_before = df_account[df_account["txn_date"] < first_day]
    df_month = df_account[(df_account["txn_date"] >= first_day) & (df_account["txn_date"] < next_month)]

    if not df_before.empty:
        df_before = df_before.copy()
        df_before["signed"] = df_before.apply(lambda r: float(r["amount"]) if r["type"]=="credit" else -float(r["amount"]), axis=1)
    else:
        df_before = pd.DataFrame(columns=df.columns.tolist()+["signed"])
    if not df_month.empty:
        df_month = df_month.copy()
        df_month["signed"] = df_month.apply(lambda r: float(r["amount"]) if r["type"]=="credit" else -float(r["amount"]), axis=1)
    else:
        df_month = pd.DataFrame(columns=df.columns.tolist()+["signed"])

    carry_forward = df_before["signed"].sum() if not df_before.empty else 0.0
    month_net = df_month["signed"].sum() if not df_month.empty else 0.0
    new_balance = carry_forward + month_net

    st.metric("Carry forward", f"{carry_forward:.2f}")
    st.metric("This month net", f"{month_net:.2f}")
    st.metric("New balance", f"{new_balance:.2f}")

    st.markdown("---")
    st.subheader("Recent transactions")
    show_df = df.sort_values(by=["txn_date"], ascending=False).head(200)
    st.dataframe(show_df.reset_index(drop=True))
else:
    st.info("No transactions yet.")
