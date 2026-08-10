import re
from dataclasses import dataclass

# 粗筛关键词：含其一才进入精解析
KEYWORDS = re.compile(r"取件码|取货码|提货码|包裹|快递|驿站|快递柜|丰巢")

# 站名中不应出现的字（"已到X"前缀、取件码、"请凭"等）
_NON_STATION_CHARS = "到请凭已取"

# 站名实体：正文中的驿站词组
STATION_PATTERN = re.compile(
    r"(?:菜鸟驿站|妈妈驿站|兔喜[^\s，。！？；:：】]{0,12}|快递超市[^\s，。！？；:：】]{0,12}"
    r"|丰巢[^\s，。！？；:：】]{0,12}|智能快递柜[^\s，。！？；:：】]{0,12}"
    r"|[^\s，。！？；:：()（）\-到请凭已取]{1,8}驿站[^\s，。！？；:：()（）\-取]{0,8})"
)

HEADER_PATTERN = re.compile(r"【([^】]{1,20})】")

# 正文"已到X"地点提取（如"已到朝阳花园南门店"）；"已到达"整体匹配，排除"请凭在"避免污染站名
ARRIVED_PATTERN = re.compile(r"(?:已到达|已到|到达|到)([^，。！？；:：\s取请凭在]{2,24})")

# "请凭A, B到Y取件/至Y尽早取"：码与驿站名一起提取
PING_PATTERN = re.compile(
    r"(?:请凭|凭)([A-Za-z0-9\-]{3,12}(?:[，、,\s]+[A-Za-z0-9\-]{3,12})*)[到至]"
    r"([^，。！？；:：\s取]{2,24}?)(?:尽早)?取"
)

PICKUP_PATTERNS = [
    re.compile(r"取件码[：:为是]?\s*([A-Za-z0-9\-]{3,12})"),
    re.compile(r"取货码[：:为是]?\s*([A-Za-z0-9\-]{3,12})"),
    re.compile(r"提货码[：:为是]?\s*([A-Za-z0-9\-]{3,12})"),
    re.compile(r"请输入([A-Za-z0-9\-]{3,12})取件"),
    re.compile(r"凭([A-Za-z0-9\-]{3,12})(?:取件|来取)"),
]

EXPRESS_COMPANIES = [
    "中通", "圆通", "申通", "韵达", "极兔", "顺丰速运", "顺丰",
    "京东快递", "京东", "邮政", "EMS", "丹鸟", "菜鸟直送", "德邦",
]

EXPRESS_PATTERN = re.compile("|".join(EXPRESS_COMPANIES))


@dataclass
class ParsedSms:
    station: str
    pickup_code: str
    express: str | None


def _split_codes(raw: str) -> list[str]:
    codes = []
    for code in re.split(r"[，、,\s]+", raw):
        if code and code not in codes:
            codes.append(code)
    return codes


def _extract_station(text: str) -> str | None:
    ping_m = PING_PATTERN.search(text)
    if ping_m:
        return ping_m.group(2)
    by_m = re.search(r"由([^，。！？；:：\s]{2,24})代为", text)
    if by_m:
        return by_m.group(1)
    entity_m = STATION_PATTERN.search(text)
    entity = entity_m.group(0) if entity_m else None
    location_m = ARRIVED_PATTERN.search(text)
    location = location_m.group(1) if location_m else None
    if location:
        if entity:
            if entity in location:
                return location
            if location in entity:
                return entity
            return f"{entity}·{location}"
        return location
    if entity:
        return entity
    # 取件码已提取成功时的兜底：【】标题作为站名（去 App 后缀）
    header = HEADER_PATTERN.search(text)
    if header:
        title = re.sub(r"App$|APP$", "", header.group(1))
        if title:
            return title
    if re.search(r"代收点", text):
        return "代收点"
    return None


def parse_sms_multi(text: str) -> list[ParsedSms]:
    if not KEYWORDS.search(text):
        return []
    express_m = EXPRESS_PATTERN.search(text)
    express = express_m.group(0) if express_m else None
    results: list[ParsedSms] = []
    seen_codes: set[str] = set()
    # "请凭X到Y取件"分句：每个分句的取件码归到该分句自己的驿站名
    for m in PING_PATTERN.finditer(text):
        station = m.group(2)
        for code in _split_codes(m.group(1)):
            if code in seen_codes:
                continue
            seen_codes.add(code)
            results.append(ParsedSms(station=station, pickup_code=code, express=express))
    # 其它模式（"取件码：X"等）的码：归到全局驿站名
    station = _extract_station(text)
    if not station:
        return []
    for pattern in PICKUP_PATTERNS:
        for m in pattern.finditer(text):
            for code in _split_codes(m.group(1)):
                if code in seen_codes:
                    continue
                seen_codes.add(code)
                results.append(ParsedSms(station=station, pickup_code=code, express=express))
    return results


def parse_sms(text: str) -> ParsedSms | None:
    results = parse_sms_multi(text)
    return results[0] if results else None
