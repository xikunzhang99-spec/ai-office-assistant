import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database.init_db import init_database

init_database()

st.set_page_config(page_title="AI办公助理", page_icon="📋", layout="wide")

pages = {
    "每日工作台": "pages.dashboard",
    "任务管理": "pages.tasks",
    "日历视图": "pages.calendar_view",
    "时间轴": "pages.timeline",
    "AI问答": "pages.ai_query",
    "文件上传": "pages.files",
    "每日总结": "pages.daily_summary",
    "项目管理": "pages.projects",
    "客户管理": "pages.clients",
    "数据管理": "pages.data_management",
}

st.sidebar.title("AI办公助理")
st.sidebar.divider()

selected = st.sidebar.radio("导航", list(pages.keys()))

st.sidebar.divider()
with st.sidebar:
    if st.button("备份数据库", type="secondary", use_container_width=True):
        try:
            from services.backup_service import backup_database
            path = backup_database()
            st.success(f"备份完成: {path}")
        except Exception as e:
            st.error(f"备份失败: {str(e)}")

module_name = pages[selected]
try:
    module = __import__(module_name, fromlist=["render"])
    module.render()
except Exception as e:
    st.error(f"页面加载失败: {str(e)}")
