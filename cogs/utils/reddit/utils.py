from datetime import datetime
import re
from typing import Optional, Tuple

URL_RE = re.compile(r'(https?:\/\/(www.)?redd)(.it|it.com)\/r\/(\w*)\/?(\w*)?')
# group 3 is the sub
# group 4 is either the method, empty, or `comments`


def parse_dt(timestamp: float) -> datetime:
    return datetime.fromtimestamp(timestamp)


def is_post(url: str) -> Tuple[bool, str, Optional[str]]:
    # use regex to extract group 3 (sub) and group 4 ([method]), `True, sub None` or False, sub, method
    match = URL_RE.search(url)
    sub, method = match.groups()[3:]
    if method == 'comments':
        return True, sub, None
    return False, sub, method
