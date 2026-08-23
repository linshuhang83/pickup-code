from server.parser import parse_sms, parse_sms_multi


class TestCainiao:
    def test_standard_with_location(self):
        sms = "【菜鸟驿站】您的包裹已到朝阳花园南门店，请凭取件码 4-1-2345 在18:00前及时取件。驿站电话：010-88888888。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "4-1-2345"
        assert "菜鸟驿站" in r.station and "朝阳花园南门店" in r.station

    def test_colon_separated_code(self):
        sms = "【菜鸟驿站】您的包裹已到公司前台，取件码：AB1234，请及时取件。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "AB1234"
        assert "公司前台" in r.station

    def test_cainiao_header_only(self):
        sms = "【菜鸟驿站】取件码 7-2-9999，您的包裹已到达，请及时取件。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "7-2-9999"
        assert "菜鸟驿站" in r.station


class TestMamaStation:
    def test_standard(self):
        sms = "【妈妈驿站】您的快递已到阳光家园3号楼妈妈驿站，取件码：6-2-8888，请及时领取。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "6-2-8888"
        assert "妈妈驿站" in r.station

    def test_enter_code_to_pickup(self):
        sms = "【妈妈驿站】您的快递已到店，请输入8888取件，请及时领取。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "8888"


class TestTuxi:
    def test_standard(self):
        sms = "【兔喜快递超市】您的包裹已到兔喜快递超市(学府路店)，取件码 5-1-2222，请及时取件。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "5-1-2222"
        assert "学府路店" in r.station


class TestFengchao:
    def test_locker_code(self):
        sms = "【丰巢】您的包裹已入柜，取件码：345678，请凭码至丰巢智能柜取件。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "345678"
        assert "丰巢" in r.station

    def test_locker_with_pickup_hint(self):
        sms = "【丰巢智能柜】包裹已入柜，请凭123456取件，柜机：小区东门。"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "123456"


class TestExpressCompany:
    def test_express_extracted(self):
        sms = "【妈妈驿站】您的中通快递已到阳光家园，取件码：6-2-8888。"
        r = parse_sms(sms)
        assert r is not None
        assert r.express == "中通"


class TestNegative:
    def test_shipment_notice(self):
        sms = "【淘宝】您购买的宝贝已发货，物流单号：SF1234567890，请耐心等待。"
        assert parse_sms(sms) is None

    def test_signed_notice(self):
        sms = "【拼多多】您的订单已签收，感谢惠顾，欢迎再次购买。"
        assert parse_sms(sms) is None

    def test_verification_code(self):
        sms = "【美团】您的验证码为123456，5分钟内有效，请勿泄露。"
        assert parse_sms(sms) is None

    def test_normal_friend_message(self):
        sms = "晚上一起吃饭吗？"
        assert parse_sms(sms) is None

    def test_express_but_no_pickup_code(self):
        sms = "【菜鸟驿站】您的包裹已出发派送，请注意查收。"
        assert parse_sms(sms) is None


class TestSmsSamples:
    """覆盖多平台真实文案结构的虚构短信样本。"""

    def test_cainiao_ping_multi_codes(self):
        sms = "【菜鸟驿站】请凭146-7-7450, 106-2-5266到星河花园东门店菜鸟驿站取件"
        results = parse_sms_multi(sms)
        assert [r.pickup_code for r in results] == ["146-7-7450", "106-2-5266"]
        assert results[0].station == "星河花园东门店菜鸟驿站"

    def test_cainiao_ping_three_codes(self):
        sms = "【菜鸟驿站】请凭50-2-9084, 62-3-4509, 92-2-2292到星河花园东门店菜鸟驿站取件"
        results = parse_sms_multi(sms)
        assert len(results) == 3
        assert results[2].pickup_code == "92-2-2292"

    def test_cainiao_ping_zhi(self):
        sms = "【菜鸟驿站】请凭92-2-2292至星河花园东门店菜鸟驿站尽早取您韵达的包裹"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "92-2-2292"
        assert r.station == "星河花园东门店菜鸟驿站"
        assert r.express == "韵达"

    def test_tuxi_tihuo_code(self):
        sms = "【兔喜生活】您提货码37-12-7031的包裹长时间未取，由星河花园兔喜店代为签收保管，请及时领取"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "37-12-7031"
        assert "星河花园兔喜店" in r.station

    def test_tuxi_arrived_no_extra_da(self):
        # "已到达" 中的 "达" 不应混入站名
        sms = "【兔喜生活】您有包裹已到达星河花园兔喜店，取件码为9-2-0401，地址:星河花园8号楼超市旁"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "9-2-0401"
        assert "达" not in r.station
        assert "星河花园兔喜店" in r.station

    def test_dewu_no_station(self):
        sms = "【得物App】UNKNOWTAL 已在代收点滞留24小时，取件码9-3-6956，请及时取件"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "9-3-6956"
        assert "得物" in r.station

    def test_kuaibao_ping_lai(self):
        sms = "【快宝驿站】您的包裹12345678901234已到星河花园2-103店面便民驿站，请凭K1-9773来取"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "K1-9773"
        assert "星河花园2-103店面便民驿站" in r.station

    def test_kuaibao_ping_dao(self):
        sms = "【快宝驿站】请凭K1-9773到星河花园2-103店面便民驿站取您的中通快递包裹"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "K1-9773"
        assert "星河花园2-103店面便民驿站" in r.station

    def test_pdd_no_code_ignored(self):
        sms = "【拼多多】您的快递1234567890123已到菜鸟驿站星河花园东门店菜鸟驿站，请凭手机号或运单号取件"
        assert parse_sms(sms) is None

    def test_anti_fraud_ad_ignored(self):
        sms = "【某省公安厅 某省通信管理局】提醒您，刷单就是诈骗！警惕快递内红包二维码，不要下载来源不明的APP"
        assert parse_sms(sms) is None

    def test_overdue_no_code_ignored(self):
        sms = "【中通快递】您的快件23456789012345已在兔喜生活星河花园兔喜店存放超过5天，请尽快取件"
        assert parse_sms(sms) is None

    def test_no_header_dai_shou_dian(self):
        sms = "迪士尼 已在代收点滞留24小时，取件码K3-7400，请及时取件"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "K3-7400"
        assert r.station == "代收点"

    def test_arrived_does_not_swallow_qingping(self):
        # 无标点时"已到X请凭取件码"的"请凭"不应混入站名
        sms = "您的包裹已到朝阳花园南门店请凭取件码4-1-2345在18:00前及时取件"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "4-1-2345"
        assert "请凭" not in r.station
        assert "朝阳花园南门店" in r.station

    def test_numeric_station_name_full(self):
        # "金鼎1号驿站"带数字的站名不应残片化成"号驿站"
        sms = "您的包裹已入柜，请凭4-1-2345取件，地址：金鼎1号驿站"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "4-1-2345"
        assert r.station == "金鼎1号驿站"

    def test_entity_location_no_duplicate(self):
        # entity 与 location 互相包含时不应拼接出重复残片
        sms = "您的包裹已到朝阳花园菜鸟驿站，取件码：6-2-8888"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "6-2-8888"
        assert r.station.count("朝阳花园菜鸟驿站") == 1
        assert "已到" not in r.station

    def test_tihuo_code_without_other_keywords(self):
        # KEYWORDS 入口门必须包含"提货码"（与提取正则一致）
        sms = "【兔喜生活】您的提货码为8888，请尽快领取"
        r = parse_sms(sms)
        assert r is not None
        assert r.pickup_code == "8888"
        assert r.station == "兔喜生活"

    def test_multi_clause_station_per_clause(self):
        # 多个"请凭X到Y取件"分句时，每个码归到各自分句的驿站
        sms = "您的包裹已到，请凭1111到小区门口取件，如不便请凭2222到8栋取件"
        results = parse_sms_multi(sms)
        by_code = {r.pickup_code: r.station for r in results}
        assert by_code == {"1111": "小区门口", "2222": "8栋"}
