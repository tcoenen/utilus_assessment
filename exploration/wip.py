import sys
import pandas as pd
import pathlib
import duckdb
from duckdb import DuckDBPyConnection
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


def load_data(conn: DuckDBPyConnection, customers_csv: str, subscriptions_csv: str):
    """
    Load data CSVs and cast to proper data types
    """
    # Read raw data from CSVs
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


def get_mmr(conn: DuckDBPyConnection):
    """
    Calculate monthly recurring revenue.
    """
    # Assumptions
    # - a partial month is counted as a full month for income purposes
    # - subscriptions without an end date is still active at the present
    # - one customer can have several active subscriptions
    # - if subscriber is not in subscribers.csv we filter it out (see below comments in SQL)
    # - if text is present in monthly price in our CSVs we filter it out (see below comments in SQL)

    SQL = """
    -- extend still open subscriptions to today, create a list of months
    with active_months AS (
        SELECT
            subs.customer_id,
            COALESCE(monthly_price, 0) as monthly_price, -- make query safe from null in monthly_price column (there is "thirty" in one cell, we treat that as 0)
            plan,
            generate_series(
                date_trunc('month', start_date),
                date_trunc('month', COALESCE(end_date, today()::DATE)),
                '1 month'::INTERVAL
            ) as months
        FROM
            subscriptions_clean as subs
        INNER JOIN
            customers_clean as custs
        ON
            subs.customer_id = custs.customer_id  -- here we get rid of non-existent subscribers (see C050 and C999 in the excercise data)
        GROUP BY
            ALL
    ),
    -- user the list of months to create a row per active month
    monthly_entries AS (
        SELECT
            customer_id,
            monthly_price,
            plan,
            unnest(months) as month -- start date of an active month
        FROM
            active_months)
    -- calculate 
    SELECT
        month,
        sum(monthly_price) as mmr
    FROM
        monthly_entries
    GROUP BY
        month
    ORDER BY
        month;
    """

    results = conn.sql(SQL).df() # get results as pandas DataFrame
    print(results)
    return alt.Chart(results).mark_line(interpolate="step-after").encode(x="month", y=alt.X("mmr").title("Income (euros)")).properties(width=800, title="MMR")  # Plot MMR over time


def get_mmr(conn: DuckDBPyConnection):
    """
    Calculate monthly recurring revenue.
    """
    # Assumptions
    # - a partial month is counted as a full month for income purposes
    # - subscriptions without an end date is still active at the present
    # - one customer can have several active subscriptions
    # - if subscriber is not in subscribers.csv we filter it out (see below comments in SQL)
    # - if text is present in monthly price in our CSVs we filter it out (see below comments in SQL)

    SQL = """
    CREATE OR REPLACE TABLE mmr AS (
    -- extend still open subscriptions to today, create a list of months
    with active_months AS (
        SELECT
            subs.customer_id,
            COALESCE(monthly_price, 0) as monthly_price, -- make query safe from null in monthly_price column (there is "thirty" in one cell, we treat that as 0)
            plan,
            generate_series(
                date_trunc('month', start_date),
                date_trunc('month', COALESCE(end_date, today()::DATE)),
                '1 month'::INTERVAL
            ) as months
        FROM
            subscriptions_clean as subs
        INNER JOIN
            customers_clean as custs
        ON
            subs.customer_id = custs.customer_id  -- here we get rid of non-existent subscribers (see C050 and C999 in the excercise data)
        GROUP BY
            ALL
    ),
    -- user the list of months to create a row per active month
    monthly_entries AS (
        SELECT
            customer_id,
            monthly_price,
            plan,
            unnest(months) as month -- start date of an active month
        FROM
            active_months)
    -- calculate
    
            SELECT
                month,
                sum(monthly_price) as mmr
            FROM
                monthly_entries
            GROUP BY
                month
            ORDER BY
                month
    );
    """    
    conn.execute(SQL)    


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        prog="wip",
        description="read customer data, produce JSON with KPI's",
    )
    parser.add_argument("--customers_csv", help="CSV with customer data")
    parser.add_argument("--subscriptions_csv", help="CSV with subscriptions data")
    parser.add_argument("--mmr_json", help="Output filename of MMR JSON data file.")

    parsed = parser.parse_args(sys.argv[1:])
    
    # As a small pre-caution, we do not overwrite existing files:
    if pathlib.Path(parsed.mmr_json).exists():
        print(f"Will not overwrite existing data file {parsed.mmr_json}")
        sys.exit()


    # open in memory database (dataset is small, DuckDB is fast)
    conn = duckdb.connect(":memory:")
    load_data(conn, parsed.customers_csv, parsed.subscriptions_csv)
    get_mmr(conn)

    # output JSON:
    conn.execute("""COPY (SELECT * FROM mmr) TO ?;""", [parsed.mmr_json])
