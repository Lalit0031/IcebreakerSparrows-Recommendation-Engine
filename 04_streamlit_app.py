import streamlit as st
import pandas as pd
from snowflake.snowpark.context import get_active_session
from snowflake.snowpark.functions import col, listagg, lit
import altair as alt

# Snowflake Native App session
session = get_active_session()

st.logo("Icebreaker_Sparrows_logo.png", size="large", link=None, icon_image=None)
# st.image("Icebreaker_Sparrows_logo.png", width=200, caption="Icebreaker Sparrows")

st.title("Dealer Product Recommendation")

# --------------------------------
# Load Region Filter
# --------------------------------
region_df = (
    session.table("SNOWFLAKE_LEARNING_DB.DWH.RECOMMENDATION_DASHBOARD")
    .select("REGION")
    .distinct()
    .sort("REGION")
    .to_pandas()
)
region = st.sidebar.selectbox("Select Region", region_df["REGION"])

# --------------------------------
# Load Dealer Filter with NO
# --------------------------------
dealer_df = (
    session.table("SNOWFLAKE_LEARNING_DB.DWH.RECOMMENDATION_DASHBOARD")
    .filter(col("REGION") == region)
    .select("DEALER_NO", "DEALER_NAME")
    .distinct()
    .sort("DEALER_NAME")
    .to_pandas()
)

dealer_df["DISPLAY_NAME"] = dealer_df["DEALER_NAME"] + " (" + dealer_df["DEALER_NO"] + ")"
dealer_display = st.sidebar.selectbox("Select Dealer", dealer_df["DISPLAY_NAME"])
dealer_no = dealer_df[dealer_df["DISPLAY_NAME"] == dealer_display]["DEALER_NO"].values[0]
dealer_name = dealer_df[dealer_df["DISPLAY_NAME"] == dealer_display]["DEALER_NAME"].values[0]

# --------------------------------
# Top-N Selection
# --------------------------------
top_n = st.sidebar.slider("Select Top N Recommendations", min_value=1, max_value=20, value=5)

# --------------------------------
# Load Top-N Recommendations
# --------------------------------
recommendations_df = (
    session.table("SNOWFLAKE_LEARNING_DB.DWH.RECOMMENDATION_DASHBOARD")
    .filter((col("REGION") == region) & (col("DEALER_NO") == dealer_no))
    .sort(col("RECOMMENDATION_SCORE").desc())
    .limit(top_n)
    .to_pandas()
)

# --------------------------------
# Get peer buyers (other dealers in same region who bought these SKUs)
# --------------------------------
from snowflake.snowpark.functions import listagg

if not recommendations_df.empty:
    sku_list = recommendations_df["SKU"].tolist()

    # Group by SKU and aggregate DEALER_NAME with a comma separator
    peer_df = session.sql(f"""
        SELECT 
            SKU,
            LISTAGG(DISTINCT DEALER_NAME, ', ') AS OTHER_DEALERS_BUYING
            -- count(DISTINCT DEALER_NAME) as O_DEALERS_CNT
        FROM SNOWFLAKE_LEARNING_DB.DWH.RECOMMENDATION_DASHBOARD
        WHERE REGION = '{region}'
          AND DEALER_NO != '{dealer_no}'
          AND SKU IN ({','.join([f"'{sku}'" for sku in sku_list])})
        GROUP BY SKU
    """).to_pandas()

    # Merge with recommendations
    recommendations_df = recommendations_df.merge(peer_df, on="SKU", how="left")


# --------------------------------
# Display Results
# --------------------------------
st.subheader(f"Top {top_n} Product Recommendations for {dealer_name} ({dealer_no})")

display_cols = [
    "PRODUCT_NAME",
    "SKU",
    "PROD_CATEGORY",
    "PROD_SUBCATEGORY",
    "RECOMMENDATION_SCORE",
    # "O_DEALERS_CNT",
    "OTHER_DEALERS_BUYING"
]

st.dataframe(recommendations_df[display_cols])

# --------------------------------
# Visualize 
# --------------------------------
if not recommendations_df.empty:
    st.subheader("Recommendation Score per Product")

    chart_df = recommendations_df[["PRODUCT_NAME", "RECOMMENDATION_SCORE"]]

    bar_chart = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X("PRODUCT_NAME:N", sort="-y", title="Product"),
        y=alt.Y("RECOMMENDATION_SCORE:Q", title="Score"),
        color=alt.Color("PRODUCT_NAME:N", legend=None), 
        tooltip=["PRODUCT_NAME", "RECOMMENDATION_SCORE"]
    ).properties(width=700, height=400)

    st.altair_chart(bar_chart, use_container_width=True)


st.subheader("Top Products to Upsell")
top_upsell = recommendations_df[["SKU", "PRODUCT_NAME", "RECOMMENDATION_SCORE"]].sort_values("RECOMMENDATION_SCORE", ascending=False).head(10)

st.dataframe(top_upsell)

if not recommendations_df.empty:
    st.subheader("Cross-Selling Opportunities by Product Category")

    category_df = recommendations_df["PROD_CATEGORY"].value_counts().reset_index()
    category_df.columns = ["Category", "Count"]

    pie = alt.Chart(category_df).mark_arc().encode(
        theta="Count:Q",
        color="Category:N",
        tooltip=["Category", "Count"]
    ).properties(width=400, height=400)

    st.altair_chart(pie, use_container_width=True)

if "OTHER_DEALERS_BUYING" in recommendations_df.columns:
    st.subheader("Peer Influence per Product")

    peer_df = recommendations_df.copy()
    peer_df["PEER_COUNT"] = peer_df["OTHER_DEALERS_BUYING"].fillna("").apply(lambda x: len(x.split(", ")) if x else 0)

    peer_chart = alt.Chart(peer_df).mark_bar().encode(
        x=alt.X("PRODUCT_NAME:N", sort="-y"),
        y="PEER_COUNT:Q",
        color=alt.Color("PEER_COUNT:Q", scale=alt.Scale(scheme="blues")),
        tooltip=["PRODUCT_NAME", "PEER_COUNT"]
    ).properties(width=700, height=400)

    st.altair_chart(peer_chart, use_container_width=True)
