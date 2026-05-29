from datetime import datetime, date, timedelta


def today_str() -> str:
    return date.today().isoformat()


def now_str() -> str:
    return datetime.now().isoformat()


def week_start_date(ref_date=None) -> date:
    d = ref_date or date.today()
    return d - timedelta(days=d.weekday())


def week_end_date(ref_date=None) -> date:
    return week_start_date(ref_date) + timedelta(days=6)


def month_start_date(ref_date=None) -> date:
    d = ref_date or date.today()
    return d.replace(day=1)


def month_end_date(ref_date=None) -> date:
    d = ref_date or date.today()
    next_month = d.replace(day=28) + timedelta(days=4)
    return next_month - timedelta(days=next_month.day)


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def format_date(d):
    if not d:
        return ""
    if isinstance(d, str):
        return d
    return d.strftime("%Y-%m-%d")


def format_datetime(dt):
    if not dt:
        return ""
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%d %H:%M:%S")
