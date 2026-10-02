# -*- coding: utf-8 -*-
"""版本号与版权信息（唯一权威来源）。

命名规则：
    vMAJOR.MINOR.PATCH  —— 第二位数字为大版本迭代位，第三位数字为小版本迭代位，
                           第一位数字仅在产品形态发生根本性变化时变动。
    BUILD               —— 10 位内部构建号，规则为 YYMMDD + 4 位当日迭代序号，
                           如 2609010026 = 2026-09-01 第 26 次构建。
"""

APP_NAME = "证书管理库"
APP_NAME_EN = "CertVault"
APP_SLOGAN = "证书有效期 · 分类归档 · 考试计划 · 资料整理"

APP_VERSION = "v1.6.0"
BUILD = "2610020016"
BUILD_DATE = "2026-10-02"

AUTHOR = "肆月Aperture"
COPYRIGHT = "Copyright 2026 肆月Aperture"
LICENSE_LINE = "本软件为开源软件，没有授权禁止用于商业用途。"

FULL_VERSION = f"{APP_VERSION} ({BUILD})"

# 联系方式 —— 「关于与声明」页的联系卡片与下方声明正文共用这一份，避免两处各写一遍。
# 每项：(图标名, 平台名, 页面上显示的地址, 点击时打开的目标, 品牌色)
CONTACTS = [
    ("github", "GitHub", "github.com/zouzuo1994321",
     "https://github.com/zouzuo1994321", "#24292f"),
    ("bilibili", "哔哩哔哩", "space.bilibili.com/13715",
     "https://space.bilibili.com/13715", "#00aeec"),
    ("weibo", "微博", "weibo.com/u/5189652182",
     "https://weibo.com/u/5189652182", "#e6162d"),
    ("mail", "邮箱", "921103025@qq.com",
     "mailto:921103025@qq.com", "#c9a227"),
]

_CONTACT_TEXT = "\n".join(f"{name}：{addr}" for _, name, addr, _, _ in CONTACTS)

# 关于页面使用的声明正文
DISCLAIMER = f"""一、版权归属
本软件（证书管理库 / CertVault）的源码、界面设计、图标与文档，版权均归 肆月Aperture 所有。
Copyright 2026 肆月Aperture. All rights reserved.

二、开源与商用
本软件为开源软件，没有授权禁止用于商业用途。
在保留本声明与版权信息完整的前提下，允许个人免费使用、学习与研究。

三、免责声明
1. 本软件按「现状」提供，作者不对使用或无法使用本软件所造成的任何直接、间接损失承担责任。
2. 本软件为 100% 离线单机程序，证书数据、附件与考试计划仅保存在本机数据目录，不会上传任何服务器。
3. 证书有效期、到期天数与提醒均依据用户自行录入的日期计算，仅作个人管理辅助，
   不构成任何法律、行政或职业资格认定依据，最终以发证机构口径为准。
4. 请用户定期备份 data 目录；因误删、磁盘损坏、系统重装导致的数据丢失，作者无法恢复。
5. 用户应遵守相关法律法规及证书颁发机构的规定，不得利用本软件从事任何违法违规活动。

四、联系作者
使用中遇到问题、想提建议，或希望合作 / 转载 / 二次分发，欢迎通过以下任一方式联系：
{_CONTACT_TEXT}

五、最终解释权
本声明的最终解释权归作者所有。
"""
