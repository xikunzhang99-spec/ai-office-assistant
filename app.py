import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(page_title="AI办公助手", page_icon="📋", layout="wide")

from database.init_db import init_database
init_database()

# 使用 st.navigation 定义所有页面，主脚本不显示为独立页面
pg = st.navigation([
    st.Page("pages/01_daily_workspace.py", title="每日工作台", icon="📋"),
    st.Page("pages/05_timeline.py", title="时间轴", icon="📜"),
    st.Page("pages/02_business_management.py", title="业务管理", icon="📊"),
])
pg.run()
