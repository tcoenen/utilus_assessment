import sys
import pandas as pd
import duckdb
from duckdb import IOException
import altair as alt

import datetime as dt
import argparse


SQL_CLEAN_CUSTOMERS = """
CREATE TABLE IF NOT EXISTS customers_clean AS (
SELECT
    customer_id::VARCHAR AS customer_id,
    try_cast(signup_date AS DATE) AS signup_date,  -- this takes out our bad dates
    upper(country)::VARCHAR
FROM customers_raw);
"""
SQL_CLEAN_SUBSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS subscriptions_clean AS (
SELECT
    customer_id::VARCHAR as customer_id,
    try_cast(start_date AS DATE) as start_date,
    try_cast(end_date AS DATE) as end_date,
    upper(plan) as plan,
    try_cast(monthly_price AS INTEGER) as monthly_price
FROM subscriptions_raw);
"""


def load_data(customers_csv: str, subscriptions_csv: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load data CSVs and cast to proper data types
    """
    # Read raw data from CSVs
    conn = duckdb.connect(":memory:")
    try:
        conn.execute("""CREATE TABLE customers_raw AS SELECT * FROM read_csv(?);""", [customers_csv]).df()
    except IOException:
        print(f"File {customers_csv} does not exist")
        sys.exit()
    try:
        conn.execute("""CREATE TABLE subscriptions_raw AS SELECT * FROM read_csv(?);""", [subscriptions_csv]).df()
    except IOException:
        print(f"File {subscriptions_csv} does not exist")
        sys.exit()

    # Clean up data types
    conn.execute(SQL_CLEAN_CUSTOMERS)
    conn.execute(SQL_CLEAN_SUBSCRIPTIONS)

    # generate our dataframes
    customers = conn.execute("SELECT * FROM customers_clean").df()
    subscriptions = conn.execute("SELECT * FROM subscriptions_clean").df()
    
    return customers, subscriptions


if __name__ == "__main__":
    customers, subscriptions = load_data("../data/customers.csv", "../data/subscriptions.csv")
    assert isinstance(customers, pd.DataFrame)
    assert isinstance(subscriptions, pd.DataFrame)