import streamlit as st
import pandas as pd
import json
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import gspread
from gspread_dataframe import get_as_dataframe, set_with_dataframe

st.set_page_config(page_title="Accounting - Sheets Backend", layout="centered")

# --- Auth: load service account from Streamlit secrets ---
sa_json = st.secrets["GSPREAD_SERVICE_ACCOUNT"]
sa_info = json.loads(sa_json)
# Use gspread service account from dict
gc = gspread.service_account_from_dict(sa_info)

# --- Open sheet ---
SHEET_KEY = st.secrets["SHEET_KEY"]  # set in Streamlit Secrets
SHEET_NAME = "Transactions"         # tab name in your sheet
sh = gc.open_by_key(SHEET_KEY)
try:
    worksheet = sh.worksheet(SHEET_NAME)
except gspread.WorksheetNotFound:
    worksheet = sh.add_worksheet(title=SHEET_NAME, rows="1000", cols="20")
    # create header row if newly created
    worksheet.append_row(["txn_date","type","amount","payment_mode","description","account","sub_account","created_at"])

# --- Helpers ---
@st.cache_data(ttl=30)
def load_transactions_df():
    df = get_as_dataframe(worksheet, evaluate_formulas=True, header=0)
    # Drop fully-empty rows that gspread returns as NaN rows
    if df is None:
        return pd.DataFrame(columns=["txn_date","type","amount","payment_mode","description","account","sub_account","created_at"])
    df = df.dropna(how="all")
    # Ensure proper dtypes
    if "txn_date" in df.columns:
        df["txn_date"] = pd.to_datetime(df["txn_date"], errors="coerce").dt.date
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)
    return df

def append_transaction_row(row_values:list):
    # Append as list: ordering matches header
    worksheet.append_row(row_values)

# --- UI ---
st.title("Quick Accounting — Google Sheets Backend")

# Quick account creation: add to 'account' dropdown via sheet cache (simple; accounts are just strings)
# For speed, we might maintain a separate Accounts sheet; for now we'll infer accounts from existing transactions.
df = load_transactions_df()
account_options = ["-- Select --"] + sorted(df["account"].dropna().unique().tolist()) if not df.empty else ["-- Select --"]

st.markdown("**New transaction**")
with st.form("txn_form", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        txn_date = st.date_input("Date", value=date.today())
        txn_type = st.selectbox("Type", ["debit", "credit"])
        amount = st.number_input("Amount", min_value=0.0, format="%.2f", step=1.0)
    with c2:
        payment_mode = st.selectbox("Mode", ["cash", "bank", "upi", "card", "other"])
        account_choice = st.text_input("Account (type or pick below)", value="")
        sub_account = st.text_input("Sub-account (optional)")
        description = st.text_input("Description")
    submitted = st.form_submit_button("Save")

    if submitted:
        # determine account: prefer typed value; fallback to selection
        account = account_choice.strip() or ("-- Select --" if account_choice=="" else "")
        created_at = datetime.utcnow().isoformat()
        # Prepare row in same header order
        row = [
            txn_date.isoformat(),
            txn_type,
            f"{amount:.2f}",
            payment_mode,
            description,
            account,
            sub_account,
            created_at
        ]
        append_transaction_row(row)
        st.success("Saved to Google Sheets ✅")
        # clear cache so load_transactions_df will fetch fresh data next time
        st.cache_data.clear()

# --- Summary area ---
st.markdown("---")
st.subheader("Summary (pick account & month)")
# reload df after possible write
df = load_transactions_df()
if df.empty:
    st.info("No transactions yet.")
else:
    # prepare account list
    accounts = sorted(df["account"].dropna().unique().tolist())
    sel_account = st.selectbox("Account", ["-- All --"] + accounts)
    month_picker = st.date_input("Month (pick any date in month)", value=date.today())

    first_day = month_picker.replace(day=1)
    next_month = (first_day + relativedelta(months=1)).replace(day=1)

    if sel_account == "-- All --":
        df_account = df
    else:
        df_account = df[df["account"] == sel_account]

    # filter month
    df_before = df_account[df_account["txn_date"] < first_day]
    df_month = df_account[(df_account["txn_date"] >= first_day) & (df_account["txn_date"] < next_month)]

    # compute balances
    # treat credit as positive, debit as negative
    df_before["signed"] = df_before.apply(lambda r: float(r["amount"]) if r["type"]=="credit" else -float(r["amount"]), axis=1)
    df_month["signed"] = df_month.apply(lambda r: float(r["amount"]) if r["type"]=="credit" else -float(r["amount"]), axis=1)

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
