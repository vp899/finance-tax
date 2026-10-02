"""默认数据：2013 小企业会计准则科目表、现金流量项目、设置等"""
from .database import Base, engine, SessionLocal, ensure_schema
from .models import (
    Setting, Account, VoucherType, CashflowItem, AccountCashflowMap,
    Unit, Currency, Period,
)

# (code, name, parent_code, direction, category, pinyin)
ACCOUNTS = [
    # ---- 资产 ----
    ("1001", "库存现金", None, "D", "asset", "kcxj kucunxianjin"),
    ("1002", "银行存款", None, "D", "asset", "yhck yinhangcunkuan"),
    ("1012", "其他货币资金", None, "D", "asset", "qthbzj qitahuobizijin"),
    ("1101", "短期投资", None, "D", "asset", "dqtz duanqitouzi"),
    ("1121", "应收票据", None, "D", "asset", "yspj yingshoupiaojv"),
    ("1122", "应收账款", None, "D", "asset", "yszk yingshouzhangkuan"),
    ("1123", "预付账款", None, "D", "asset", "yfzk yufuzhangkuan"),
    ("1131", "应收股利", None, "D", "asset", "ysgl yingshouguli"),
    ("1132", "应收利息", None, "D", "asset", "yslx yingshoulixi"),
    ("1221", "其他应收款", None, "D", "asset", "qtysk qitayingshoukuan"),
    ("1401", "材料采购", None, "D", "asset", "clcg cailiaocaigou"),
    ("1402", "在途物资", None, "D", "asset", "ztwz zaituwuzi"),
    ("1403", "原材料", None, "D", "asset", "ycl yuan cailiao"),
    ("1404", "材料成本差异", None, "D", "asset", "clcbyc"),
    ("1405", "库存商品", None, "D", "asset", "kcsp kucunshangpin"),
    ("1406", "商品进销差价", None, "D", "asset", "spjxcj"),
    ("1407", "发出商品", None, "D", "asset", "fcsp fachushangpin"),
    ("1408", "委托加工物资", None, "D", "asset", "wtjgwz"),
    ("1411", "周转材料", None, "D", "asset", "zzcl zhouzhuancailiao"),
    ("1501", "长期债券投资", None, "D", "asset", "cqzqtz"),
    ("1511", "长期股权投资", None, "D", "asset", "cqgqtz"),
    ("1601", "固定资产", None, "D", "asset", "gdzc gudingzichan"),
    ("1602", "累计折旧", None, "D", "asset", "ljzj leijizhejiu"),
    ("1604", "在建工程", None, "D", "asset", "zjgc zaijiangongcheng"),
    ("1605", "工程物资", None, "D", "asset", "gcwz gongchengwuzi"),
    ("1606", "固定资产清理", None, "D", "asset", "gdzcql"),
    ("1701", "无形资产", None, "D", "asset", "wxzc wuxingzichan"),
    ("1702", "累计摊销", None, "D", "asset", "ljtx leijitanxiao"),
    ("1801", "长期待摊费用", None, "D", "asset", "cqdtfy"),
    ("1901", "待处理财产损溢", None, "D", "asset", "dcldcsy"),
    # ---- 负债 ----
    ("2001", "短期借款", None, "C", "liability", "dqjk duanqijiekuan"),
    ("2201", "应付票据", None, "C", "liability", "yfpj yingfupiaojv"),
    ("2202", "应付账款", None, "C", "liability", "yfzk yingfuzhangkuan"),
    ("2203", "预收账款", None, "C", "liability", "yszk yushouzhangkuan"),
    ("2211", "应付职工薪酬", None, "C", "liability", "yfzggxc"),
    ("2221", "应交税费", None, "C", "liability", "yjsf yingjiaoshuifei"),
    ("2231", "应付利息", None, "C", "liability", "yflx yingfulixi"),
    ("2232", "应付股利", None, "C", "liability", "yfgl yingfuguli"),
    ("2241", "其他应付款", None, "C", "liability", "qtyfk qitayingfukuan"),
    ("2401", "递延收益", None, "C", "liability", "diyanshouyi dysy"),
    ("2501", "长期借款", None, "C", "liability", "cqjk changqijiekuan"),
    ("2701", "长期应付款", None, "C", "liability", "cqyfk"),
    # ---- 权益 ----
    ("3001", "实收资本", None, "C", "equity", "szzb shoushouziben"),
    ("3002", "资本公积", None, "C", "equity", "zbgj zibengongji"),
    ("3101", "盈余公积", None, "C", "equity", "yygj yingyugongji"),
    ("3103", "本年利润", None, "C", "equity", "bnlr bennianlirun"),
    ("3104", "利润分配", None, "C", "equity", "lrfp lirunfenpei"),
    # ---- 成本 ----
    ("4001", "生产成本", None, "D", "cost", "sccb shengchancheengben"),
    ("4051", "制造费用", None, "D", "cost", "zzfy zhizaofeiyong"),
    # ---- 收入 ----
    ("5001", "主营业务收入", None, "C", "income", "zyywsr"),
    ("5051", "其他业务收入", None, "C", "income", "qtywsr"),
    ("5111", "投资收益", None, "C", "income", "tzsy touzishouyi"),
    ("5301", "营业外收入", None, "C", "income", "yywsr yingyewaishouru"),
    # ---- 成本费用 ----
    ("5401", "主营业务成本", None, "D", "expense", "zyywcb"),
    ("5402", "其他业务成本", None, "D", "expense", "qtywcb"),
    ("5403", "税金及附加", None, "D", "expense", "sjjf shuijinjifujia"),
    ("5601", "销售费用", None, "D", "expense", "xsfy xiaoshoufeiyong"),
    ("5602", "管理费用", None, "D", "expense", "glfy guanlifeiyong"),
    ("5603", "财务费用", None, "D", "expense", "cwfy caiwufeiyong"),
    ("5711", "营业外支出", None, "D", "expense", "yywzc"),
    ("5801", "所得税费用", None, "D", "expense", "sdsfy suodeshuifeiyong"),
    # ---- 常用明细科目 ----
    ("222101", "应交增值税", "2221", "C", "liability", "yjzzs yingjiaozengzhishui"),
    ("222102", "未交增值税", "2221", "C", "liability", "wjzzs weijiaozengzhishui"),
    ("222106", "应交城市维护建设税", "2221", "C", "liability", "yjcshwjs"),
    ("222108", "应交教育费附加", "2221", "C", "liability", "yjjyffj"),
    ("222109", "应交地方教育附加", "2221", "C", "liability", "yjdfjyffj"),
    ("222112", "应交所得税", "2221", "C", "liability", "yjsds yingjiaosuodeshui"),
    ("222113", "应交个人所得税", "2221", "C", "liability", "yjgrsds"),
    ("222114", "应交印花税", "2221", "C", "liability", "yiyhsh"),
    ("221101", "工资", "2211", "C", "liability", "gz gongzi"),
    ("221102", "职工福利费", "2211", "C", "liability", "zgflf"),
    ("221103", "社会保险费", "2211", "C", "liability", "shbxf"),
    ("540301", "城市维护建设税", "5403", "D", "expense", "cshwjs"),
    ("540302", "教育费附加", "5403", "D", "expense", "jyffj"),
    ("540303", "地方教育附加", "5403", "D", "expense", "dfjyffj"),
    ("540304", "印花税", "5403", "D", "expense", "yhs yinhuashui"),
    ("560101", "工资", "5601", "D", "expense", "gz gongzi"),
    ("560102", "广告宣传费", "5601", "D", "expense", "ggxcf"),
    ("560103", "运输费", "5601", "D", "expense", "ysf yunshufei"),
    ("560109", "其他", "5601", "D", "expense", "qt qita"),
    ("560201", "工资", "5602", "D", "expense", "gz gongzi"),
    ("560202", "折旧费", "5602", "D", "expense", "zjf zhejiufei"),
    ("560203", "摊销费", "5602", "D", "expense", "txf tanxiaofei"),
    ("560204", "办公费", "5602", "D", "expense", "bgf bangongfei"),
    ("560205", "水电费", "5602", "D", "expense", "sdf shuidianfei"),
    ("560206", "差旅费", "5602", "D", "expense", "clf chailvfei"),
    ("560207", "业务招待费", "5602", "D", "expense", "ywzdf"),
    ("560209", "其他", "5602", "D", "expense", "qt qita"),
    ("560301", "利息支出", "5603", "D", "expense", "lxzc lixizhichu"),
    ("560302", "手续费", "5603", "D", "expense", "sxf shouxufei"),
    ("560303", "利息收入", "5603", "C", "expense", "lxsr lixishouru"),
    ("571101", "罚没支出", "5711", "D", "expense", "fmzc"),
    ("571102", "捐赠支出", "5711", "D", "expense", "jzzc"),
    # ---- 标准报表明细项（小企业会计准则利润表“其中”项）----
    ("540305", "消费税", "5403", "D", "expense", "xf xiaofeishui"),
    ("540306", "营业税", "5403", "D", "expense", "yys yingyeshui"),
    ("540307", "资源税", "5403", "D", "expense", "zys ziyuanshui"),
    ("540308", "土地增值税", "5403", "D", "expense", "tdzzs"),
    ("540309", "城镇土地使用税、房产税、车船税", "5403", "D", "expense", "csfcs"),
    ("560104", "商品维修费", "5601", "D", "expense", "spwxf"),
    ("560210", "开办费", "5602", "D", "expense", "kbf kaibanfei"),
    ("560211", "研究费用", "5602", "D", "expense", "yjfy yanjiufei"),
    ("530101", "政府补助", "5301", "C", "income", "zfbz zhengfubuzhu"),
    ("571103", "坏账损失", "5711", "D", "expense", "hzss huaizhangsunshi"),
    ("571104", "无法收回的长期债券投资损失", "5711", "D", "expense", "wfshcqzqtz"),
    ("571105", "无法收回的长期股权投资损失", "5711", "D", "expense", "wfshcqgqtz"),
    ("571106", "自然灾害等不可抗力因素造成的损失", "5711", "D", "expense", "zrzhbkk"),
    ("571107", "税收滞纳金", "5711", "D", "expense", "ssznj shuishouzhinajin"),
]

CASHFLOW_ITEMS = [
    ("101", "销售商品、提供劳务收到的现金", "operating", "D"),
    ("102", "收到的税费返还", "operating", "D"),
    ("103", "收到其他与经营活动有关的现金", "operating", "D"),
    ("201", "购买商品、接受劳务支付的现金", "operating", "C"),
    ("202", "支付给职工以及为职工支付的现金", "operating", "C"),
    ("203", "支付的各项税费", "operating", "C"),
    ("204", "支付其他与经营活动有关的现金", "operating", "C"),
    ("301", "收回投资收到的现金", "investing", "D"),
    ("302", "取得投资收益收到的现金", "investing", "D"),
    ("303", "处置固定资产、无形资产和其他非流动资产收回的现金净额", "investing", "D"),
    ("304", "处置子公司及其他营业单位收到的现金净额", "investing", "D"),
    ("305", "收到其他与投资活动有关的现金", "investing", "D"),
    ("401", "购建固定资产、无形资产和其他非流动资产支付的现金", "investing", "C"),
    ("402", "投资支付的现金", "investing", "C"),
    ("403", "取得子公司及其他营业单位支付的现金净额", "investing", "C"),
    ("404", "支付其他与投资活动有关的现金", "investing", "C"),
    ("501", "吸收投资收到的现金", "financing", "D"),
    ("502", "取得借款收到的现金", "financing", "D"),
    ("503", "收到其他与筹资活动有关的现金", "financing", "D"),
    ("601", "偿还债务支付的现金", "financing", "C"),
    ("602", "分配股利、利润或偿付利息支付的现金", "financing", "C"),
    ("603", "支付其他与筹资活动有关的现金", "financing", "C"),
    ("604", "偿还借款利息支付的现金", "financing", "C"),
    ("605", "分配利润支付的现金", "financing", "C"),
]

# 对方科目 -> 现金流量项目（默认对照表，可在设置中修改）
DEFAULT_CASHFLOW_MAP = {
    "1122": "101", "1121": "101", "2203": "101", "5001": "101", "5051": "101",
    "1403": "201", "1405": "201", "1401": "201", "1402": "201", "2202": "201",
    "2201": "201",
    "2211": "202", "221101": "202", "221102": "202", "221103": "202",
    "2221": "203", "222101": "203", "222102": "203", "222106": "203",
    "222108": "203", "222109": "203", "222112": "203", "222113": "203",
    "222114": "203", "5403": "203",
    "5601": "204", "5602": "204", "560109": "204", "560209": "204",
    "1221": "204", "2241": "204", "5301": "103", "5711": "204",
    "1601": "401", "1604": "401", "1701": "401", "1605": "401",
    "1101": "402", "1501": "402", "1511": "402",
    "2001": "502", "2501": "502",
    "3001": "501",
    "2232": "605", "2231": "604", "5603": "604", "560301": "604",
}

DEFAULT_SETTINGS = {
    "taxpayer_type": "small",              # small=小规模纳税人 general=一般纳税人
    "accounting_standard": "xqy2013",      # 2013 小企业会计准则
    "company_name": "示例有限公司",
    "tax_no": "",
    "vat_rate": "0.03",                    # 小规模征收率
    "city_tax_rate": "0.07",               # 城建税税率（市区）
    "edu_rate": "0.03",                    # 教育费附加
    "local_edu_rate": "0.02",              # 地方教育附加
    "income_tax_rate": "0.25",             # 所得税税率
    "vat_free_month_limit": "100000",      # 小规模月销售额免征额
    "vat_free_quarter_limit": "300000",    # 小规模季销售额免征额
    "vat_free_basis": "month",             # 免征判定口径：month=按月 quarter=按季
    "depreciation_expense_account": "560202",
    "amortization_expense_account": "560203",
    "salary_expense_account": "560201",
    "sales_cost_expense_account": "5401",
    "sales_cost_credit_account": "1405",
    "payable_salary_account": "221101",
    "profit_account": "3103",
    "vat_account": "222101",
    "number_rule": "period",               # 凭证号规则：period=按月编号
    # 财务人员
    "staff_bookkeeper": "",                # 记账人
    "staff_reviewer": "",                  # 审核人
    "staff_cashier": "",                   # 出纳人
    "staff_supervisor": "",                # 会计主管
    # 小数位设置
    "decimal_qty": "2",                    # 数量最多 2 位小数（不足补零显示）
    "decimal_price": "2",                  # 单价最多 2 位小数（不足补零显示）
    "decimal_rate": "6",                    # 汇率最多 6 位小数
    # 辅助核算全局开关：1=启用 0=停用
    "aux_switch_project": "1",
    "aux_switch_customer": "1",
    "aux_switch_supplier": "1",
    "aux_switch_dept": "1",
    "aux_switch_employee": "1",
    "aux_switch_inventory": "1",
}


def ensure_standard_accounts(db):
    """幂等补齐标准科目/现金流量项目（老库升级用），并维护末级标记与层级"""
    existing = {a.code: a for a in db.query(Account).all()}
    for code, name, parent, direction, cat, py in ACCOUNTS:
        if code in existing:
            continue
        acc = Account(code=code, name=name, parent_code=parent,
                      direction=direction, category=cat, pinyin=py, is_leaf=1)
        db.add(acc)
        existing[code] = acc
    db.flush()
    for code, acc in existing.items():
        parent = existing.get(acc.parent_code) if acc.parent_code else None
        acc.level = (parent.level + 1) if parent else 1
        acc.is_leaf = 0 if any(a.parent_code == code for a in existing.values()) else 1
    # 现金流量项目补齐
    cf_existing = {c.code for c in db.query(CashflowItem).all()}
    for code, name, cat, direction in CASHFLOW_ITEMS:
        if code not in cf_existing:
            db.add(CashflowItem(code=code, name=name, category=cat, direction=direction))
    db.flush()


def ensure_seed():
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    db = SessionLocal()
    try:
        if db.query(Setting).count() == 0:
            for k, v in DEFAULT_SETTINGS.items():
                db.add(Setting(key=k, value=v))
        if db.query(Account).count() == 0:
            code_map = {}
            for code, name, parent, direction, cat, py in ACCOUNTS:
                acc = Account(
                    code=code, name=name, parent_code=parent,
                    direction=direction, category=cat, pinyin=py,
                )
                db.add(acc)
                code_map[code] = acc
            db.flush()
            for code, acc in code_map.items():
                parent = acc.parent_code
                if parent and parent in code_map:
                    code_map[parent].is_leaf = 0
                    acc.level = code_map[parent].level + 1
            # 应交增值税 明细
            zzs = code_map.get("222101")
            if zzs:
                zzs.is_leaf = 1
        if db.query(CashflowItem).count() == 0:
            for code, name, cat, direction in CASHFLOW_ITEMS:
                db.add(CashflowItem(code=code, name=name, category=cat, direction=direction))
        db.flush()
        if db.query(AccountCashflowMap).count() == 0:
            for acc_code, cf_code in DEFAULT_CASHFLOW_MAP.items():
                acc = db.query(Account).filter(Account.code == acc_code).first()
                if acc and db.query(CashflowItem).filter(CashflowItem.code == cf_code).first():
                    db.add(AccountCashflowMap(account_id=acc.id, cashflow_code=cf_code))
        if db.query(VoucherType).count() == 0:
            db.add(VoucherType(name="记账凭证", prefix="记", is_default=1))
            db.add(VoucherType(name="收款凭证", prefix="收"))
            db.add(VoucherType(name="付款凭证", prefix="付"))
            db.add(VoucherType(name="转账凭证", prefix="转"))
        if db.query(Unit).count() == 0:
            for n, s in [("个", "个"), ("台", "台"), ("件", "件"), ("千克", "kg"),
                         ("吨", "t"), ("米", "m"), ("套", "套"), ("箱", "箱")]:
                db.add(Unit(name=n, symbol=s))
        if db.query(Currency).count() == 0:
            db.add(Currency(code="CNY", name="人民币", rate=1.0, is_default=1))
            db.add(Currency(code="USD", name="美元", rate=7.2))
            db.add(Currency(code="EUR", name="欧元", rate=7.8))
            db.add(Currency(code="HKD", name="港币", rate=0.92))
        ensure_standard_accounts(db)
        db.commit()
    finally:
        db.close()
