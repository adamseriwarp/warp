import streamlit as st
import pandas as pd
import mysql.connector
from datetime import datetime

# Database connection
@st.cache_resource
def get_connection():
    return mysql.connector.connect(
        host="datahub-mysql.wearewarp.link",
        user="datahub-read",
        password="warpdbhub2",
        database="datahub"
    )

# Query data
@st.cache_data(ttl=43200)  # Cache for 12 hours
def load_data(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    return df

