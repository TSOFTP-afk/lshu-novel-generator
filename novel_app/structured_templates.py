from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


STRUCTURED_TEMPLATE_MIGRATION_ID = "structured_templates_v1_reset_design_text"
BOOK_OUTLINE_FORM_VERSION = "book_outline_form_v1"
BOOK_OUTLINE_FORM_MIGRATION_ID = "book_outline_form_v1"
WORLD_FORM_VERSION = "world_form_v1"
WORLD_FORM_MIGRATION_ID = "world_form_v1"
CHARACTER_PROFILE_FORM_VERSION = "character_profile_form_v1"
CHARACTER_PROFILE_FORM_MIGRATION_ID = "character_profile_form_v1_clear_legacy_text"


BOOK_OUTLINE_FORM_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "basic",
        "title": "1.1 作品基础信息",
        "items": [
            {"id": "working_title", "label": "作品暂定名", "type": "text", "prefill": "title"},
            {"id": "series_name", "label": "别名/系列名", "type": "text"},
            {"id": "one_sentence_hook", "label": "一句话题材", "type": "text"},
            {"id": "core_selling_point", "label": "核心卖点", "type": "text"},
            {"id": "opening_sentence_tone", "label": "首句引诱（开篇第一句话的气质）", "type": "text"},
            {"id": "reference_works", "label": "同类参考作品", "type": "text"},
            {"id": "avoid_like_works", "label": "想避免像哪些作品", "type": "text"},
            {"id": "target_readers", "label": "目标读者", "type": "text"},
            {"id": "reader_age", "label": "读者年龄层", "type": "text"},
            {"id": "target_platform", "label": "目标平台", "type": "text"},
        ],
    },
    {
        "id": "length_structure",
        "title": "1.2 篇幅与结构",
        "items": [
            {"id": "length_short", "label": "短篇（1 万-5 万字）", "type": "checkbox"},
            {"id": "length_middle", "label": "中篇（5 万-20 万字）", "type": "checkbox"},
            {"id": "length_long", "label": "长篇（60 万-200 万字）", "type": "checkbox"},
            {"id": "length_epic", "label": "超长篇（500 万字以上）", "type": "checkbox"},
            {"id": "structure_unit", "label": "单元剧结构", "type": "checkbox"},
            {"id": "structure_instance", "label": "副本结构", "type": "checkbox"},
            {"id": "structure_mainline", "label": "主线推进结构", "type": "checkbox"},
            {"id": "structure_ensemble", "label": "群像结构", "type": "checkbox"},
            {"id": "structure_multiline", "label": "多线并进", "type": "checkbox"},
            {"id": "structure_serial_hook", "label": "连载型强钩子结构", "type": "checkbox"},
            {"id": "structure_publish_complete", "label": "出版型完整结构", "type": "checkbox"},
            {"id": "structure_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "tags_tone",
        "title": "1.3 标签与题材气质",
        "items": [
            {"id": "tone_hotblood", "label": "热血", "type": "checkbox"},
            {"id": "tone_refreshing", "label": "爽文", "type": "checkbox"},
            {"id": "tone_light", "label": "轻松", "type": "checkbox"},
            {"id": "tone_dark", "label": "黑暗", "type": "checkbox"},
            {"id": "tone_suspense", "label": "悬疑", "type": "checkbox"},
            {"id": "tone_burning", "label": "燃向", "type": "checkbox"},
            {"id": "tone_romantic", "label": "浪漫", "type": "checkbox"},
            {"id": "tone_realistic", "label": "写实", "type": "checkbox"},
            {"id": "tone_humor", "label": "幽默", "type": "checkbox"},
            {"id": "tone_fast", "label": "快节奏", "type": "checkbox"},
            {"id": "tone_slow", "label": "慢热", "type": "checkbox"},
            {"id": "tone_healing", "label": "治愈", "type": "checkbox"},
            {"id": "tone_weird", "label": "诡异", "type": "checkbox"},
            {"id": "tone_satire", "label": "讽刺", "type": "checkbox"},
            {"id": "tone_poetic", "label": "诗意", "type": "checkbox"},
            {"id": "tone_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "genre",
        "title": "1.4 主类型与副类型",
        "items": [
            {"id": "main_genre", "label": "主类型", "type": "text"},
            {"id": "sub_genre_1", "label": "副类型 1", "type": "text"},
            {"id": "sub_genre_2", "label": "副类型 2", "type": "text"},
            {"id": "sub_genre_3", "label": "副类型 3", "type": "text"},
        ],
    },
    {
        "id": "story_core",
        "title": "1.5 故事核心设计",
        "items": [
            {"id": "story_type", "label": "故事类型（成长/逆袭/复仇/救赎/冒险/争霸/破案/生存/其他）", "type": "text"},
            {"id": "main_drive", "label": "主线驱动力（主角为什么行动？）", "type": "text"},
            {"id": "plot_structure", "label": "剧情结构（三幕式/英雄旅程/升级打怪/地图推进/副本递进/其他）", "type": "text"},
            {
                "id": "story_core_table",
                "label": "故事核心表",
                "type": "multiline",
                "placeholder": "开篇状态：\n开篇钩子：\n第一幕核心事件：\n主角短期目标：\n主角长期目标：\n中段最大反转：\n主角最低谷：\n终局目标：\n最终对手：\n最终选择：\n结局形态（HE / BE / OE / TE）：\n续作/番外空间：",
            },
        ],
    },
    {
        "id": "volume_plan",
        "title": "1.6 分卷/分阶段规划",
        "items": [],
    },
    {
        "id": "conflict_theme",
        "title": "1.7 核心冲突与主题",
        "items": [
            {"id": "surface_conflict", "label": "表层冲突", "type": "text"},
            {"id": "deep_conflict", "label": "深层冲突", "type": "text"},
            {"id": "protagonist_lie", "label": "主角相信的谎言", "type": "text"},
            {"id": "final_truth", "label": "主角最终理解的真相", "type": "text"},
            {"id": "theme_statement", "label": "作品想表达的主题", "type": "text"},
            {"id": "avoid_values", "label": "不想表达的价值观", "type": "text"},
        ],
    },
    {
        "id": "payoff_pain",
        "title": "1.8 爽点与虐点设计",
        "items": [
            {"id": "payoff_face_slap", "label": "打脸逆袭", "type": "checkbox"},
            {"id": "payoff_hidden_power", "label": "扮猪吃虎", "type": "checkbox"},
            {"id": "payoff_identity_reveal", "label": "身份揭露", "type": "checkbox"},
            {"id": "payoff_level_challenge", "label": "越级挑战", "type": "checkbox"},
            {"id": "payoff_comeback", "label": "绝地翻盘", "type": "checkbox"},
            {"id": "payoff_wit", "label": "智斗胜利", "type": "checkbox"},
            {"id": "payoff_revenge", "label": "复仇成功", "type": "checkbox"},
            {"id": "payoff_recruit", "label": "收服强者", "type": "checkbox"},
            {"id": "payoff_romance", "label": "恋爱发糖", "type": "checkbox"},
            {"id": "payoff_ensemble", "label": "群像燃点", "type": "checkbox"},
            {"id": "pain_misunderstanding", "label": "误会与背叛", "type": "checkbox"},
            {"id": "pain_sacrifice", "label": "牺牲与离别", "type": "checkbox"},
            {"id": "pain_moral_dilemma", "label": "道德两难", "type": "checkbox"},
            {"id": "pain_loss", "label": "失去重要之物", "type": "checkbox"},
            {"id": "pain_unrequited", "label": "爱而不得", "type": "checkbox"},
            {"id": "payoff_custom", "label": "自定义爽点", "type": "checkbox_text"},
            {"id": "pain_custom", "label": "自定义虐点", "type": "checkbox_text"},
        ],
    },
]


BOOK_OUTLINE_VOLUME_PLAN_FIELDS: list[dict[str, str]] = [
    {"id": "core_events", "label": "核心事件"},
    {"id": "stage_goal", "label": "阶段目标"},
    {"id": "character_appearances", "label": "人物出场"},
    {"id": "main_conflict", "label": "主要冲突"},
    {"id": "key_turning", "label": "关键转折"},
    {"id": "ending_hook", "label": "结尾钩子"},
]


BOOK_OUTLINE_TEMPLATE = """# 书籍大纲模板

## 1.1 作品基础信息

- 作品暂定名：____
- 别名/系列名：____
- 一句话题材：____
- 核心卖点：____
- 首句引诱（开篇第一句话的气质）：____
- 同类参考作品：____
- 想避免像哪些作品：____
- 目标读者：____
- 读者年龄层：____
- 目标平台：____

## 1.2 篇幅与结构

- [ ] 短篇（1 万-5 万字）
- [ ] 中篇（5 万-20 万字）
- [ ] 长篇（60 万-200 万字）
- [ ] 超长篇（500 万字以上）
- [ ] 单元剧结构
- [ ] 副本结构
- [ ] 主线推进结构
- [ ] 群像结构
- [ ] 多线并进
- [ ] 连载型强钩子结构
- [ ] 出版型完整结构
- [ ] 自定义：____

## 1.3 标签与题材气质

- [ ] 热血
- [ ] 爽文
- [ ] 轻松
- [ ] 黑暗
- [ ] 悬疑
- [ ] 燃向
- [ ] 浪漫
- [ ] 写实
- [ ] 幽默
- [ ] 快节奏
- [ ] 慢热
- [ ] 治愈
- [ ] 诡异
- [ ] 讽刺
- [ ] 诗意
- [ ] 自定义：____

## 1.4 主类型与副类型

- 主类型：____
- 副类型 1：____
- 副类型 2：____
- 副类型 3：____

## 1.5 故事核心设计

- 故事类型（成长/逆袭/复仇/救赎/冒险/争霸/破案/生存/其他）：____
- 主线驱动力（主角为什么行动？）：____
- 剧情结构（三幕式/英雄旅程/升级打怪/地图推进/副本递进/其他）：____

```text
开篇状态：
开篇钩子：
第一幕核心事件：
主角短期目标：
主角长期目标：
中段最大反转：
主角最低谷：
终局目标：
最终对手：
最终选择：
结局形态（HE / BE / OE / TE）：
续作/番外空间：
```

## 1.6 分卷/分阶段规划

> 当前书籍尚未创建分卷。

## 1.7 核心冲突与主题

- 表层冲突：____
- 深层冲突：____
- 主角相信的谎言：____
- 主角最终理解的真相：____
- 作品想表达的主题：____
- 不想表达的价值观：____

## 1.8 爽点与虐点设计

- [ ] 打脸逆袭
- [ ] 扮猪吃虎
- [ ] 身份揭露
- [ ] 越级挑战
- [ ] 绝地翻盘
- [ ] 智斗胜利
- [ ] 复仇成功
- [ ] 收服强者
- [ ] 恋爱发糖
- [ ] 群像燃点
- [ ] 误会与背叛
- [ ] 牺牲与离别
- [ ] 道德两难
- [ ] 失去重要之物
- [ ] 爱而不得
- [ ] 自定义爽点：____
- [ ] 自定义虐点：____
"""


WORLD_TEMPLATE = """# 世界观设定模板

## 2.1 世界基础形态

- [ ] 现实世界
- [ ] 近现实世界（与现实相似但有微调）
- [ ] 平行世界
- [ ] 架空世界
- [ ] 异世界
- [ ] 虚拟/游戏世界
- [ ] 星际文明
- [ ] 多元宇宙
- [ ] 自定义：____

## 2.2 时代与文明层级

- [ ] 原始部落
- [ ] 神话时代
- [ ] 古代王朝
- [ ] 中世纪
- [ ] 蒸汽工业时代
- [ ] 近代
- [ ] 现代
- [ ] 近未来
- [ ] 远未来
- [ ] 废土
- [ ] 末日之后
- [ ] 多时代并存
- [ ] 自定义：____

## 2.3 超凡与科技水平

- 超凡层级：____
- 超凡者比例：____
- 科技水平：____
- 科技与超凡的关系：____
- 自定义：____

## 2.4 世界规则填报表

```text
世界名称：
世界地图范围（大洲/国家/城市/星球/位面）：
世界总面积与已知区域比例：
主要国家/势力（名称、体制、特色）：
  势力1：
  势力2：
  势力3：
时代背景简史（关键历史事件）：
货币体系：
语言体系：
主要种族/智慧物种：
交通方式（普通人/权贵/超凡者分别如何出行）：
通讯方式：
教育体系：
法律体系：
宗教信仰（神祇是否存在、教会权力）：
阶级结构（各阶层比例与流动可能）：
普通人的一日生活：
超凡者/权力者的一日生活：
世界核心禁忌（绝对不能做的事）：
世界隐藏真相（主角将逐步发现的秘密）：
```

## 2.5 势力与组织

```text
主要势力 1：
  名称：
  类型（帝国/共和国/宗门/公司/教会/公会/其他）：
  领袖：
  核心价值观：
  军事实力：
  经济实力：
  与主角关系：

主要势力 2：
  名称：
  类型：
  领袖：
  核心价值观：
  军事实力：
  经济实力：
  与主角关系：

其他重要组织/势力：
中立/灰色地带势力：
```

## 2.6 世界危机与冲突

- [ ] 外敌入侵
- [ ] 资源枯竭
- [ ] 环境灾变
- [ ] 阶级革命
- [ ] 神明战争
- [ ] AI/科技失控
- [ ] 位面崩坏
- [ ] 瘟疫/丧尸
- [ ] 内部腐败
- [ ] 魔法/灵气异常
- [ ] 无明确世界级危机
- [ ] 自定义：____

```text
当前世界危机描述：
危机的根源：
各方势力对危机的态度：
留给主角的时间窗口：
危机可能的结局：
```
"""


WORLD_FORM_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "base_shape",
        "title": "2.1 世界基础形态",
        "items": [
            {"id": "shape_real", "label": "现实世界", "type": "checkbox"},
            {"id": "shape_near_real", "label": "近现实世界（与现实相似但有微调）", "type": "checkbox"},
            {"id": "shape_parallel", "label": "平行世界", "type": "checkbox"},
            {"id": "shape_fictional", "label": "架空世界", "type": "checkbox"},
            {"id": "shape_otherworld", "label": "异世界", "type": "checkbox"},
            {"id": "shape_virtual", "label": "虚拟/游戏世界", "type": "checkbox"},
            {"id": "shape_space", "label": "星际文明", "type": "checkbox"},
            {"id": "shape_multiverse", "label": "多元宇宙", "type": "checkbox"},
            {"id": "shape_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "civilization",
        "title": "2.2 时代与文明层级",
        "items": [
            {"id": "era_tribal", "label": "原始部落", "type": "checkbox"},
            {"id": "era_mythic", "label": "神话时代", "type": "checkbox"},
            {"id": "era_ancient", "label": "古代王朝", "type": "checkbox"},
            {"id": "era_medieval", "label": "中世纪", "type": "checkbox"},
            {"id": "era_steam", "label": "蒸汽工业时代", "type": "checkbox"},
            {"id": "era_modern_early", "label": "近代", "type": "checkbox"},
            {"id": "era_modern", "label": "现代", "type": "checkbox"},
            {"id": "era_near_future", "label": "近未来", "type": "checkbox"},
            {"id": "era_far_future", "label": "远未来", "type": "checkbox"},
            {"id": "era_wasteland", "label": "废土", "type": "checkbox"},
            {"id": "era_post_apocalypse", "label": "末日之后", "type": "checkbox"},
            {"id": "era_multi", "label": "多时代并存", "type": "checkbox"},
            {"id": "era_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "power_tech",
        "title": "2.3 超凡与科技水平",
        "items": [
            {"id": "supernatural_level", "label": "超凡层级", "type": "text"},
            {"id": "supernatural_ratio", "label": "超凡者比例", "type": "text"},
            {"id": "tech_level", "label": "科技水平", "type": "text"},
            {"id": "tech_supernatural_relation", "label": "科技与超凡的关系", "type": "text"},
            {"id": "power_tech_custom", "label": "自定义", "type": "text"},
        ],
    },
    {
        "id": "rules",
        "title": "2.4 世界规则填报表",
        "items": [
            {
                "id": "world_rules_table",
                "label": "世界规则填报表",
                "type": "multiline",
                "placeholder": "世界名称：\n世界地图范围（大洲/国家/城市/星球/位面）：\n世界总面积与已知区域比例：\n主要国家/势力（名称、体制、特色）：\n  势力1：\n  势力2：\n  势力3：\n时代背景简史（关键历史事件）：\n货币体系：\n语言体系：\n主要种族/智慧物种：\n交通方式（普通人/权贵/超凡者分别如何出行）：\n通讯方式：\n教育体系：\n法律体系：\n宗教信仰（神祇是否存在、教会权力）：\n阶级结构（各阶层比例与流动可能）：\n普通人的一日生活：\n超凡者/权力者的一日生活：\n世界核心禁忌（绝对不能做的事）：\n世界隐藏真相（主角将逐步发现的秘密）：",
            },
        ],
    },
    {
        "id": "factions",
        "title": "2.5 势力与组织",
        "items": [
            {
                "id": "factions_table",
                "label": "势力与组织",
                "type": "multiline",
                "placeholder": "主要势力 1：\n  名称：\n  类型（帝国/共和国/宗门/公司/教会/公会/其他）：\n  领袖：\n  核心价值观：\n  军事实力：\n  经济实力：\n  与主角关系：\n\n主要势力 2：\n  名称：\n  类型：\n  领袖：\n  核心价值观：\n  军事实力：\n  经济实力：\n  与主角关系：\n\n其他重要组织/势力：\n中立/灰色地带势力：",
            },
        ],
    },
    {
        "id": "crisis",
        "title": "2.6 世界危机与冲突",
        "items": [
            {"id": "crisis_invasion", "label": "外敌入侵", "type": "checkbox"},
            {"id": "crisis_resource", "label": "资源枯竭", "type": "checkbox"},
            {"id": "crisis_environment", "label": "环境灾变", "type": "checkbox"},
            {"id": "crisis_revolution", "label": "阶级革命", "type": "checkbox"},
            {"id": "crisis_gods", "label": "神明战争", "type": "checkbox"},
            {"id": "crisis_ai", "label": "AI/科技失控", "type": "checkbox"},
            {"id": "crisis_plane", "label": "位面崩坏", "type": "checkbox"},
            {"id": "crisis_plague", "label": "瘟疫/丧尸", "type": "checkbox"},
            {"id": "crisis_corruption", "label": "内部腐败", "type": "checkbox"},
            {"id": "crisis_magic", "label": "魔法/灵气异常", "type": "checkbox"},
            {"id": "crisis_none", "label": "无明确世界级危机", "type": "checkbox"},
            {"id": "crisis_custom", "label": "自定义", "type": "checkbox_text"},
            {
                "id": "crisis_table",
                "label": "危机细节",
                "type": "multiline",
                "placeholder": "当前世界危机描述：\n危机的根源：\n各方势力对危机的态度：\n留给主角的时间窗口：\n危机可能的结局：",
            },
        ],
    },
]


PROTAGONIST_TEMPLATE = """# 主角设定模板

## 3.1 基础身份

```text
姓名：
别名/称号：
年龄：
性别：
外貌关键词（3-5 个词）：
标志性特征（伤疤/纹身/饰品/口癖/习惯动作）：
```

- 身份/职业：____
- [ ] 普通人
- [ ] 学生
- [ ] 打工人/社畜
- [ ] 医生/律师/警察/侦探
- [ ] 军人/杀手/间谍
- [ ] 商人/企业家
- [ ] 贵族/皇室
- [ ] 穿越者
- [ ] 重生者
- [ ] 修士/魔法师/异能者
- [ ] 非人类/机器人/AI
- [ ] 自定义：____

## 3.2 性格特质

- 主要性格（选 2-3 个）：____
- [ ] 善良
- [ ] 冷静
- [ ] 理性
- [ ] 热血
- [ ] 腹黑
- [ ] 温柔
- [ ] 偏执
- [ ] 乐子人
- [ ] 利己型
- [ ] 反英雄
- [ ] 野心家
- [ ] 咸鱼型
- [ ] 规则破坏者
- [ ] 秩序维护者
- [ ] 社恐
- [ ] 傲娇
- [ ] 毒舌
- [ ] 自定义：____

## 3.3 核心欲望与恐惧

```text
公开目标（主角对外宣称的目标）：
隐藏欲望（主角内心真正渴望但不愿/不敢承认的）：
核心恐惧（主角最害怕发生的事情）：
核心执念（放不下的东西/人/想法）：
底层驱动力（什么推动主角度过最困难的时刻）：
```

## 3.4 缺陷与成长弧

- 核心缺陷/弱点：____
- [ ] 自卑 / 自负
- [ ] 怯懦 / 鲁莽
- [ ] 冷漠 / 控制欲强
- [ ] 不信任他人
- [ ] 害怕亲密关系
- [ ] 创伤后遗症
- [ ] 道德洁癖 / 目的至上
- [ ] 缺乏责任感 / 过度负责
- [ ] 逃避现实 / 执念过深
- [ ] 记忆缺失
- [ ] 自定义：____

```text
缺陷的来源（童年/创伤/经历）：
缺陷在故事中如何影响主角决策：
成长方向（主角需要学会/改变什么）：
成长的关键转折事件：
最终主角是否克服缺陷：
```

## 3.5 能力与金手指

- 能力定位：____
- [ ] 修炼体系
- [ ] 魔法体系
- [ ] 异能体系
- [ ] 科技装备
- [ ] 知识/记忆优势
- [ ] 无特殊能力，靠智慧与经验
- [ ] 自定义：____

```text
金手指类型（系统/面板/神器/血脉/随身空间/前世记忆/其他）：
金手指来源：
金手指优势：
金手指代价/限制：
能力成长方式：
能力上限：
失败风险：
主角最终能力形态：
```

## 3.6 道德边界

```text
道德底线（绝对不能做的事）：
可以被突破的底线（在什么情况下会破例）：
对待敌人的态度：
对待陌生人的态度：
对待朋友/伙伴的态度：
对待背叛者的态度：
是否愿意为大局牺牲少数人：
```

## 3.7 关系与情感

- 感情线强度：____
- 感情对象：____
- 爱情观：____
- 相识契机：____
- 关系走向：____
- 感情线最大阻碍：____
- 感情结局：____

```text
主角与家人的关系：
最重要的朋友/伙伴：
最信任的人：
会背叛主角的人：
主角心中不可触碰的人（软肋）：
```
"""


SUPPORTING_CHARACTER_TEMPLATE = """# 配角设定模板

## 4.1 配角基础信息

```text
姓名：
别名/称号：
年龄：
性别：
外貌关键词：
标志性特征：
身份/职业：
与主角关系（搭档/导师/恋人/宿敌/家人/其他）：
```

## 4.2 配角的角色功能定位

- [ ] 搭档/战友
- [ ] 导师/引路人
- [ ] 恋人/感情对象
- [ ] 挚友/知己
- [ ] 宿敌/竞争者
- [ ] 搞笑担当
- [ ] 智囊
- [ ] 战力担当
- [ ] 治疗/后勤
- [ ] 普通人视角
- [ ] 道德锚点
- [ ] 背叛者
- [ ] 牺牲角色
- [ ] 自定义：____

## 4.3 性格与特质

- 主要性格（2-3 个词）：____
- 口头禅/习惯动作：____
- [ ] 开朗
- [ ] 沉默
- [ ] 毒舌
- [ ] 温柔
- [ ] 腹黑
- [ ] 热血
- [ ] 冷静
- [ ] 傲娇
- [ ] 天然呆
- [ ] 偏执
- [ ] 乐子人
- [ ] 社恐
- [ ] 可靠
- [ ] 天真
- [ ] 自定义：____

## 4.4 动机与欲望

```text
个人目标：
与主角目标一致/冲突的地方：
为什么跟随/对抗主角：
深层次的欲望与恐惧：
```

## 4.5 能力定位

- 能力类型：____
- 实力等级（相对于主角）：____
- 特长/专精领域：____
- 短板/弱点：____

## 4.6 与主角的关系线

```text
初次相遇场景：
关系起点（敌意/陌生/友善/利用）：
关系转折事件：
关系高潮时刻：
当前关系状态：
最终关系走向：
```

## 4.7 配角个人弧光

```text
出场时的状态：
个人成长/堕落的方向：
对其影响最大的事件：
最终结局：
```
"""


PROTAGONIST_FORM_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "basic",
        "title": "3.1 基础身份",
        "items": [
            {"id": "alias", "label": "别名/称号", "type": "text"},
            {"id": "age", "label": "年龄", "type": "text"},
            {"id": "gender", "label": "性别", "type": "text"},
            {"id": "appearance_keywords", "label": "外貌关键词（3-5 个词）", "type": "text"},
            {"id": "signature_feature", "label": "标志性特征（伤疤/纹身/饰品/口癖/习惯动作）", "type": "text"},
            {"id": "identity_occupation", "label": "身份/职业", "type": "text"},
            {"id": "identity_common", "label": "普通人", "type": "checkbox"},
            {"id": "identity_student", "label": "学生", "type": "checkbox"},
            {"id": "identity_worker", "label": "打工人/社畜", "type": "checkbox"},
            {"id": "identity_professional", "label": "医生/律师/警察/侦探", "type": "checkbox"},
            {"id": "identity_soldier", "label": "军人/杀手/间谍", "type": "checkbox"},
            {"id": "identity_merchant", "label": "商人/企业家", "type": "checkbox"},
            {"id": "identity_noble", "label": "贵族/皇室", "type": "checkbox"},
            {"id": "identity_transmigrator", "label": "穿越者", "type": "checkbox"},
            {"id": "identity_reborn", "label": "重生者", "type": "checkbox"},
            {"id": "identity_powered", "label": "修士/魔法师/异能者", "type": "checkbox"},
            {"id": "identity_nonhuman", "label": "非人类/机器人/AI", "type": "checkbox"},
            {"id": "identity_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "personality",
        "title": "3.2 性格特质",
        "items": [
            {"id": "personality_main", "label": "主要性格（选 2-3 个）", "type": "text"},
            {"id": "personality_kind", "label": "善良", "type": "checkbox"},
            {"id": "personality_calm", "label": "冷静", "type": "checkbox"},
            {"id": "personality_rational", "label": "理性", "type": "checkbox"},
            {"id": "personality_hotblood", "label": "热血", "type": "checkbox"},
            {"id": "personality_scheming", "label": "腹黑", "type": "checkbox"},
            {"id": "personality_gentle", "label": "温柔", "type": "checkbox"},
            {"id": "personality_obsessive", "label": "偏执", "type": "checkbox"},
            {"id": "personality_trickster", "label": "乐子人", "type": "checkbox"},
            {"id": "personality_selfish", "label": "利己型", "type": "checkbox"},
            {"id": "personality_antihero", "label": "反英雄", "type": "checkbox"},
            {"id": "personality_ambitious", "label": "野心家", "type": "checkbox"},
            {"id": "personality_slacker", "label": "咸鱼型", "type": "checkbox"},
            {"id": "personality_rulebreaker", "label": "规则破坏者", "type": "checkbox"},
            {"id": "personality_order", "label": "秩序维护者", "type": "checkbox"},
            {"id": "personality_introvert", "label": "社恐", "type": "checkbox"},
            {"id": "personality_tsundere", "label": "傲娇", "type": "checkbox"},
            {"id": "personality_tongue", "label": "毒舌", "type": "checkbox"},
            {"id": "personality_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "desire_fear",
        "title": "3.3 核心欲望与恐惧",
        "items": [
            {
                "id": "desire_fear_table",
                "label": "核心欲望与恐惧",
                "type": "multiline",
                "placeholder": "公开目标（主角对外宣称的目标）：\n隐藏欲望（主角内心真正渴望但不愿/不敢承认的）：\n核心恐惧（主角最害怕发生的事情）：\n核心执念（放不下的东西/人/想法）：\n底层驱动力（什么推动主角度过最困难的时刻）：",
            },
        ],
    },
    {
        "id": "flaw_arc",
        "title": "3.4 缺陷与成长弧",
        "items": [
            {"id": "core_flaw", "label": "核心缺陷/弱点", "type": "text"},
            {"id": "flaw_inferiority", "label": "自卑 / 自负", "type": "checkbox"},
            {"id": "flaw_cowardly", "label": "怯懦 / 鲁莽", "type": "checkbox"},
            {"id": "flaw_control", "label": "冷漠 / 控制欲强", "type": "checkbox"},
            {"id": "flaw_distrust", "label": "不信任他人", "type": "checkbox"},
            {"id": "flaw_intimacy", "label": "害怕亲密关系", "type": "checkbox"},
            {"id": "flaw_trauma", "label": "创伤后遗症", "type": "checkbox"},
            {"id": "flaw_morality", "label": "道德洁癖 / 目的至上", "type": "checkbox"},
            {"id": "flaw_responsibility", "label": "缺乏责任感 / 过度负责", "type": "checkbox"},
            {"id": "flaw_escape", "label": "逃避现实 / 执念过深", "type": "checkbox"},
            {"id": "flaw_memory", "label": "记忆缺失", "type": "checkbox"},
            {"id": "flaw_custom", "label": "自定义", "type": "checkbox_text"},
            {
                "id": "growth_arc_table",
                "label": "成长弧细节",
                "type": "multiline",
                "placeholder": "缺陷的来源（童年/创伤/经历）：\n缺陷在故事中如何影响主角决策：\n成长方向（主角需要学会/改变什么）：\n成长的关键转折事件：\n最终主角是否克服缺陷：",
            },
        ],
    },
    {
        "id": "ability",
        "title": "3.5 能力与金手指",
        "items": [
            {"id": "ability_position", "label": "能力定位", "type": "text"},
            {"id": "ability_cultivation", "label": "修炼体系", "type": "checkbox"},
            {"id": "ability_magic", "label": "魔法体系", "type": "checkbox"},
            {"id": "ability_superpower", "label": "异能体系", "type": "checkbox"},
            {"id": "ability_tech", "label": "科技装备", "type": "checkbox"},
            {"id": "ability_memory", "label": "知识/记忆优势", "type": "checkbox"},
            {"id": "ability_none", "label": "无特殊能力，靠智慧与经验", "type": "checkbox"},
            {"id": "ability_custom", "label": "自定义", "type": "checkbox_text"},
            {
                "id": "cheat_table",
                "label": "金手指细节",
                "type": "multiline",
                "placeholder": "金手指类型（系统/面板/神器/血脉/随身空间/前世记忆/其他）：\n金手指来源：\n金手指优势：\n金手指代价/限制：\n能力成长方式：\n能力上限：\n失败风险：\n主角最终能力形态：",
            },
        ],
    },
    {
        "id": "morality",
        "title": "3.6 道德边界",
        "items": [
            {
                "id": "morality_table",
                "label": "道德边界",
                "type": "multiline",
                "placeholder": "道德底线（绝对不能做的事）：\n可以被突破的底线（在什么情况下会破例）：\n对待敌人的态度：\n对待陌生人的态度：\n对待朋友/伙伴的态度：\n对待背叛者的态度：\n是否愿意为大局牺牲少数人：",
            },
        ],
    },
    {
        "id": "relationships",
        "title": "3.7 关系与情感",
        "items": [
            {"id": "romance_strength", "label": "感情线强度", "type": "text"},
            {"id": "romance_target", "label": "感情对象", "type": "text"},
            {"id": "romance_view", "label": "爱情观", "type": "text"},
            {"id": "romance_meet", "label": "相识契机", "type": "text"},
            {"id": "romance_direction", "label": "关系走向", "type": "text"},
            {"id": "romance_obstacle", "label": "感情线最大阻碍", "type": "text"},
            {"id": "romance_ending", "label": "感情结局", "type": "text"},
            {
                "id": "relationship_table",
                "label": "关系网络",
                "type": "multiline",
                "placeholder": "主角与家人的关系：\n最重要的朋友/伙伴：\n最信任的人：\n会背叛主角的人：\n主角心中不可触碰的人（软肋）：",
            },
        ],
    },
]


SUPPORTING_CHARACTER_FORM_SCHEMA: list[dict[str, Any]] = [
    {
        "id": "basic",
        "title": "4.1 配角基础信息",
        "items": [
            {"id": "alias", "label": "别名/称号", "type": "text"},
            {"id": "age", "label": "年龄", "type": "text"},
            {"id": "gender", "label": "性别", "type": "text"},
            {"id": "appearance_keywords", "label": "外貌关键词", "type": "text"},
            {"id": "signature_feature", "label": "标志性特征", "type": "text"},
            {"id": "identity_occupation", "label": "身份/职业", "type": "text"},
            {"id": "relationship_to_protagonist", "label": "与主角关系（搭档/导师/恋人/宿敌/家人/其他）", "type": "text"},
        ],
    },
    {
        "id": "function",
        "title": "4.2 配角的角色功能定位",
        "items": [
            {"id": "function_partner", "label": "搭档/战友", "type": "checkbox"},
            {"id": "function_mentor", "label": "导师/引路人", "type": "checkbox"},
            {"id": "function_love", "label": "恋人/感情对象", "type": "checkbox"},
            {"id": "function_friend", "label": "挚友/知己", "type": "checkbox"},
            {"id": "function_rival", "label": "宿敌/竞争者", "type": "checkbox"},
            {"id": "function_comedy", "label": "搞笑担当", "type": "checkbox"},
            {"id": "function_brain", "label": "智囊", "type": "checkbox"},
            {"id": "function_fighter", "label": "战力担当", "type": "checkbox"},
            {"id": "function_support", "label": "治疗/后勤", "type": "checkbox"},
            {"id": "function_common_view", "label": "普通人视角", "type": "checkbox"},
            {"id": "function_moral_anchor", "label": "道德锚点", "type": "checkbox"},
            {"id": "function_betrayer", "label": "背叛者", "type": "checkbox"},
            {"id": "function_sacrifice", "label": "牺牲角色", "type": "checkbox"},
            {"id": "function_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "personality",
        "title": "4.3 性格与特质",
        "items": [
            {"id": "personality_main", "label": "主要性格（2-3 个词）", "type": "text"},
            {"id": "catchphrase", "label": "口头禅/习惯动作", "type": "text"},
            {"id": "personality_cheerful", "label": "开朗", "type": "checkbox"},
            {"id": "personality_silent", "label": "沉默", "type": "checkbox"},
            {"id": "personality_tongue", "label": "毒舌", "type": "checkbox"},
            {"id": "personality_gentle", "label": "温柔", "type": "checkbox"},
            {"id": "personality_scheming", "label": "腹黑", "type": "checkbox"},
            {"id": "personality_hotblood", "label": "热血", "type": "checkbox"},
            {"id": "personality_calm", "label": "冷静", "type": "checkbox"},
            {"id": "personality_tsundere", "label": "傲娇", "type": "checkbox"},
            {"id": "personality_airhead", "label": "天然呆", "type": "checkbox"},
            {"id": "personality_obsessive", "label": "偏执", "type": "checkbox"},
            {"id": "personality_trickster", "label": "乐子人", "type": "checkbox"},
            {"id": "personality_introvert", "label": "社恐", "type": "checkbox"},
            {"id": "personality_reliable", "label": "可靠", "type": "checkbox"},
            {"id": "personality_naive", "label": "天真", "type": "checkbox"},
            {"id": "personality_custom", "label": "自定义", "type": "checkbox_text"},
        ],
    },
    {
        "id": "motivation",
        "title": "4.4 动机与欲望",
        "items": [
            {
                "id": "motivation_table",
                "label": "动机与欲望",
                "type": "multiline",
                "placeholder": "个人目标：\n与主角目标一致/冲突的地方：\n为什么跟随/对抗主角：\n深层次的欲望与恐惧：",
            },
        ],
    },
    {
        "id": "ability",
        "title": "4.5 能力定位",
        "items": [
            {"id": "ability_type", "label": "能力类型", "type": "text"},
            {"id": "power_level", "label": "实力等级（相对于主角）", "type": "text"},
            {"id": "specialty", "label": "特长/专精领域", "type": "text"},
            {"id": "weakness", "label": "短板/弱点", "type": "text"},
        ],
    },
    {
        "id": "relationship_arc",
        "title": "4.6 与主角的关系线",
        "items": [
            {
                "id": "relationship_arc_table",
                "label": "关系线",
                "type": "multiline",
                "placeholder": "初次相遇场景：\n关系起点（敌意/陌生/友善/利用）：\n关系转折事件：\n关系高潮时刻：\n当前关系状态：\n最终关系走向：",
            },
        ],
    },
    {
        "id": "personal_arc",
        "title": "4.7 配角个人弧光",
        "items": [
            {
                "id": "personal_arc_table",
                "label": "个人弧光",
                "type": "multiline",
                "placeholder": "出场时的状态：\n个人成长/堕落的方向：\n对其影响最大的事件：\n最终结局：",
            },
        ],
    },
]


def is_protagonist_role(role: str) -> bool:
    normalized = str(role or "").strip()
    return any(token in normalized for token in ("主角", "男主", "女主", "主人公", "主视角"))


def character_profile_schema_key(role: str = "", schema_key: str = "") -> str:
    key = str(schema_key or "").strip().lower()
    if key in {"protagonist", "main", "主角"}:
        return "protagonist"
    if key in {"supporting", "support", "配角"}:
        return "supporting"
    return "protagonist" if is_protagonist_role(role) else "supporting"


def character_profile_schema_for_role(role: str = "", schema_key: str = "") -> list[dict[str, Any]]:
    return PROTAGONIST_FORM_SCHEMA if character_profile_schema_key(role, schema_key) == "protagonist" else SUPPORTING_CHARACTER_FORM_SCHEMA


def character_profile_form_defaults(name: str = "", role: str = "", schema_key: str = "") -> dict[str, Any]:
    resolved_key = character_profile_schema_key(role, schema_key)
    schema = character_profile_schema_for_role(role, resolved_key)
    data = _structured_form_defaults(CHARACTER_PROFILE_FORM_VERSION, schema)
    data["schema"] = resolved_key
    fields = data["fields"]
    if "identity_occupation" in fields and is_protagonist_role(role):
        fields["identity_occupation"]["value"] = str(role or "").strip()
    if "relationship_to_protagonist" in fields and not is_protagonist_role(role):
        fields["relationship_to_protagonist"]["value"] = str(role or "").strip()
    return data


def character_profile_form_to_markdown(data: dict[str, Any] | None, name: str = "", role: str = "") -> str:
    normalized = normalize_character_profile_form(data, name, role)
    schema = character_profile_schema_for_role(role, str(normalized.get("schema", "")))
    heading = "# 主角设定模板" if normalized.get("schema") == "protagonist" else "# 配角设定模板"
    markdown = _structured_form_to_markdown(normalized, schema, heading)
    lines = markdown.splitlines()
    output: list[str] = []
    inserted_identity = False
    for line in lines:
        output.append(line)
        if not inserted_identity and line.startswith("## "):
            output.extend(["", f"- 姓名：{str(name or '').strip() or '____'}", f"- 角色定位：{str(role or '').strip() or '____'}"])
            inserted_identity = True
    return "\n".join(output).strip()


def character_profile_markdown_to_form(markdown: str, name: str = "", role: str = "") -> dict[str, Any]:
    text = str(markdown or "").strip()
    data = character_profile_form_defaults(name, role, _schema_key_from_character_markdown(text, role))
    if not text:
        return data
    if not _looks_like_character_markdown(text):
        return merge_character_profile_supplement(data, name, role, text, supplement_title="AI/用户补充")
    schema = character_profile_schema_for_role(role, str(data.get("schema", "")))
    return normalize_character_profile_form(
        _structured_markdown_to_form(text, schema, data, CHARACTER_PROFILE_FORM_VERSION),
        name,
        role,
        str(data.get("schema", "")),
    )


def normalize_character_profile_form(
    data: dict[str, Any] | None,
    name: str = "",
    role: str = "",
    schema_key: str = "",
) -> dict[str, Any]:
    incoming_key = schema_key
    if isinstance(data, dict):
        incoming_key = str(data.get("schema", "") or incoming_key)
    resolved_key = character_profile_schema_key(role, incoming_key)
    schema = character_profile_schema_for_role(role, resolved_key)
    normalized = _normalize_structured_form(data, schema, CHARACTER_PROFILE_FORM_VERSION)
    normalized["schema"] = resolved_key
    return normalized


def merge_character_profile_supplement(
    data: dict[str, Any] | None,
    name: str,
    role: str,
    content: str,
    *,
    supplement_title: str = "导入补充",
) -> dict[str, Any]:
    normalized = normalize_character_profile_form(data, name, role)
    content = str(content or "").strip()
    if not content:
        return normalized
    supplements = normalized.setdefault("supplements", [])
    if not isinstance(supplements, list):
        normalized["supplements"] = supplements = []
    supplements.append({"title": str(supplement_title or "补充"), "content": content})
    return normalize_character_profile_form(normalized, name, role)


def merge_character_profile_form(
    base_data: dict[str, Any] | None,
    incoming_data: dict[str, Any] | None,
    name: str = "",
    role: str = "",
) -> dict[str, Any]:
    schema_key = str(incoming_data.get("schema", "") if isinstance(incoming_data, dict) else "")
    schema = character_profile_schema_for_role(role, schema_key)
    return normalize_character_profile_form(
        _merge_structured_form(base_data, incoming_data, schema, CHARACTER_PROFILE_FORM_VERSION),
        name,
        role,
        schema_key,
    )


def merge_character_analysis_payload(
    base_data: dict[str, Any] | None,
    *,
    name: str = "",
    role: str = "",
    profile_form: Any = None,
    profile_text: Any = None,
) -> dict[str, Any]:
    data = normalize_character_profile_form(base_data, name, role)
    if isinstance(profile_form, dict):
        data = merge_character_profile_form(data, profile_form, name, role)
    elif isinstance(profile_form, str) and profile_form.strip():
        data = merge_character_profile_supplement(data, name, role, profile_form, supplement_title="AI分析补充")
    text = str(profile_text or "").strip()
    if text:
        if _looks_like_character_markdown(text):
            data = merge_character_profile_form(data, character_profile_markdown_to_form(text, name, role), name, role)
        else:
            data = merge_character_profile_supplement(data, name, role, text, supplement_title="AI分析补充")
    return normalize_character_profile_form(data, name, role)


def _schema_key_from_character_markdown(text: str, role: str = "") -> str:
    if "# 主角设定模板" in text or "## 3.1 基础身份" in text:
        return "protagonist"
    if "# 配角设定模板" in text or "## 4.1 配角基础信息" in text:
        return "supporting"
    return character_profile_schema_key(role)


def _looks_like_character_markdown(text: str) -> bool:
    return (
        "## 3.1 基础身份" in text
        or "## 4.1 配角基础信息" in text
    )


def book_outline_template(title: str = "") -> str:
    return book_outline_form_to_markdown(book_outline_form_defaults(title), title)


def book_outline_form_defaults(title: str = "", volume_specs: list[Any] | None = None) -> dict[str, Any]:
    title = str(title or "").strip()
    fields: dict[str, dict[str, Any]] = {}
    for item in _book_outline_schema_items():
        field_type = str(item.get("type", "text"))
        field_id = str(item["id"])
        if field_type == "checkbox":
            fields[field_id] = {"checked": False}
        elif field_type == "checkbox_text":
            fields[field_id] = {"checked": False, "value": ""}
        else:
            fields[field_id] = {"value": title if item.get("prefill") == "title" else ""}
    return {
        "version": BOOK_OUTLINE_FORM_VERSION,
        "fields": fields,
        "volume_plans": [_default_volume_plan(spec) for spec in _normalize_volume_specs(volume_specs)],
        "supplements": [],
    }


def book_outline_form_to_markdown(
    data: dict[str, Any] | None,
    title: str = "",
    volume_specs: list[Any] | None = None,
) -> str:
    normalized = normalize_book_outline_form(data, title, volume_specs)
    fields = normalized.get("fields", {})
    volume_plans = normalized.get("volume_plans", [])
    lines: list[str] = ["# 书籍大纲模板", ""]
    for section in BOOK_OUTLINE_FORM_SCHEMA:
        lines.extend([f"## {section['title']}", ""])
        if str(section.get("id", "")) == "volume_plan":
            if isinstance(volume_plans, list) and volume_plans:
                for display_index, plan in enumerate(volume_plans, start=1):
                    if not isinstance(plan, dict):
                        continue
                    volume_title = str(plan.get("volume_title", "") or "").strip()
                    heading = f"### 第{display_index}卷规划"
                    if volume_title:
                        heading = f"{heading}：{volume_title}"
                    lines.extend([heading, ""])
                    plan_fields = plan.get("fields", {})
                    if not isinstance(plan_fields, dict):
                        plan_fields = {}
                    for plan_item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
                        plan_field = plan_fields.get(str(plan_item["id"]), {})
                        if not isinstance(plan_field, dict):
                            plan_field = {}
                        value = str(plan_field.get("value", "") or "").strip() or "____"
                        lines.append(f"- {plan_item['label']}：{value}")
                    lines.append("")
            else:
                lines.extend(["> 当前书籍尚未创建分卷。", ""])
            continue
        for item in section.get("items", []):
            field = fields.get(str(item["id"]), {})
            field_type = str(item.get("type", "text"))
            label = str(item.get("label", ""))
            if field_type == "checkbox":
                marker = "x" if bool(field.get("checked", False)) else " "
                lines.append(f"- [{marker}] {label}")
            elif field_type == "checkbox_text":
                marker = "x" if bool(field.get("checked", False)) else " "
                value = str(field.get("value", "") or "").strip() or "____"
                lines.append(f"- [{marker}] {label}：{value}")
            elif field_type == "multiline":
                value = str(field.get("value", "") or "").strip()
                block = value or str(item.get("placeholder", "")).strip()
                lines.extend(["```text", block, "```"])
            else:
                value = str(field.get("value", "") or "").strip() or "____"
                lines.append(f"- {label}：{value}")
        lines.append("")

    supplements = normalized.get("supplements", [])
    if isinstance(supplements, list):
        for supplement in supplements:
            if not isinstance(supplement, dict):
                continue
            content = str(supplement.get("content", "") or "").strip()
            if not content:
                continue
            supplement_title = str(supplement.get("title", "") or "").strip() or "补充"
            lines.extend(["---", "", f"## {supplement_title}", "", content, ""])
    return "\n".join(lines).strip()


def book_outline_markdown_to_form(
    markdown: str,
    title: str = "",
    volume_specs: list[Any] | None = None,
) -> dict[str, Any]:
    text = str(markdown or "").strip()
    data = book_outline_form_defaults(title, volume_specs)
    if not text:
        return data
    if not _looks_like_book_outline_markdown(text):
        return merge_book_outline_supplement(data, title, text, supplement_title="旧版内容")

    fields = data["fields"]
    main_text, supplements = _split_book_outline_supplements(text)
    for item in _book_outline_schema_items():
        field_id = str(item["id"])
        field_type = str(item.get("type", "text"))
        label = re.escape(str(item.get("label", "")))
        if field_type == "checkbox":
            match = re.search(rf"^\s*-\s*\[([ xX])\]\s*{label}\s*$", main_text, re.MULTILINE)
            if match:
                fields[field_id]["checked"] = match.group(1).lower() == "x"
        elif field_type == "checkbox_text":
            match = re.search(rf"^\s*-\s*\[([ xX])\]\s*{label}\s*[:：]\s*(.*)$", main_text, re.MULTILINE)
            if match:
                fields[field_id]["checked"] = match.group(1).lower() == "x"
                value = match.group(2).strip()
                fields[field_id]["value"] = "" if value == "____" else value
        elif field_type == "text":
            match = re.search(rf"^\s*-\s*{label}\s*[:：]\s*(.*)$", main_text, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                fields[field_id]["value"] = "" if value == "____" else value

    code_blocks = re.findall(r"```text\s*\n(.*?)\n```", main_text, flags=re.DOTALL)
    multiline_items = [item for item in _book_outline_schema_items() if str(item.get("type")) == "multiline"]
    for item, block in zip(multiline_items, code_blocks):
        value = block.strip()
        placeholder = str(item.get("placeholder", "")).strip()
        fields[str(item["id"])]["value"] = "" if value == placeholder else value

    parsed_volume_plans = _parse_volume_plans_from_markdown(main_text, volume_specs)
    if parsed_volume_plans:
        data["volume_plans"] = parsed_volume_plans
    data["supplements"] = supplements
    return normalize_book_outline_form(data, title, volume_specs)


def merge_book_outline_supplement(
    data: dict[str, Any] | None,
    title: str,
    content: str,
    *,
    supplement_title: str = "导入补充",
) -> dict[str, Any]:
    normalized = normalize_book_outline_form(data, title)
    content = str(content or "").strip()
    if not content:
        return normalized
    supplements = normalized.setdefault("supplements", [])
    if not isinstance(supplements, list):
        normalized["supplements"] = supplements = []
    supplements.append({"title": str(supplement_title or "补充"), "content": content})
    return normalized


def merge_book_outline_form(
    base_data: dict[str, Any] | None,
    incoming_data: dict[str, Any] | None,
    title: str = "",
    volume_specs: list[Any] | None = None,
) -> dict[str, Any]:
    merged = normalize_book_outline_form(base_data, title, volume_specs)
    incoming = normalize_book_outline_form(incoming_data, title, volume_specs)
    merged_fields = merged.get("fields", {})
    for field_id, incoming_field in incoming.get("fields", {}).items():
        if not isinstance(incoming_field, dict):
            continue
        current = merged_fields.get(field_id, {})
        if "checked" in incoming_field and bool(incoming_field.get("checked", False)):
            current["checked"] = True
        incoming_value = str(incoming_field.get("value", "") or "").strip()
        if incoming_value and not str(current.get("value", "") or "").strip():
            current["value"] = incoming_value
        merged_fields[field_id] = current
    _merge_book_outline_volume_plans(merged, incoming)
    for supplement in incoming.get("supplements", []):
        if isinstance(supplement, dict) and str(supplement.get("content", "") or "").strip():
            merged.setdefault("supplements", []).append(
                {
                    "title": str(supplement.get("title", "") or "AI分析补充"),
                    "content": str(supplement.get("content", "") or "").strip(),
                }
            )
    return normalize_book_outline_form(merged, title, volume_specs)


def normalize_book_outline_form(
    data: dict[str, Any] | None,
    title: str = "",
    volume_specs: list[Any] | None = None,
) -> dict[str, Any]:
    specs = _normalize_volume_specs(volume_specs)
    defaults = book_outline_form_defaults(title, specs)
    if not isinstance(data, dict):
        return defaults
    normalized = deepcopy(defaults)
    fields = data.get("fields", {})
    if isinstance(fields, dict):
        for item in _book_outline_schema_items():
            field_id = str(item["id"])
            source = fields.get(field_id, {})
            if not isinstance(source, dict):
                continue
            target = normalized["fields"][field_id]
            if "checked" in target:
                target["checked"] = bool(source.get("checked", target.get("checked", False)))
            if "value" in target:
                target["value"] = str(source.get("value", target.get("value", "")) or "")
    normalized["volume_plans"] = _normalize_volume_plans(data.get("volume_plans", []), specs)
    supplements = data.get("supplements", [])
    normalized["supplements"] = []
    if isinstance(supplements, list):
        for supplement in supplements:
            if not isinstance(supplement, dict):
                continue
            content = str(supplement.get("content", "") or "").strip()
            if not content:
                continue
            normalized["supplements"].append(
                {
                    "title": str(supplement.get("title", "") or "补充").strip() or "补充",
                    "content": content,
                }
            )
    return normalized


def _volume_value(volume: Any, key: str, default: Any = "") -> Any:
    if isinstance(volume, dict):
        return volume.get(key, default)
    try:
        return volume[key]
    except (KeyError, IndexError, TypeError):
        return getattr(volume, key, default)


def _normalize_volume_specs(volume_specs: list[Any] | None) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if not isinstance(volume_specs, list):
        return specs
    for fallback_index, volume in enumerate(volume_specs, start=1):
        raw_id = _volume_value(volume, "id", fallback_index)
        raw_title = str(_volume_value(volume, "title", "") or "").strip()
        raw_order = _volume_value(volume, "sort_order", fallback_index)
        try:
            sort_order = int(raw_order)
        except (TypeError, ValueError):
            sort_order = fallback_index
        volume_id = str(raw_id or fallback_index)
        specs.append(
            {
                "volume_id": volume_id,
                "volume_title": raw_title or f"第{fallback_index}卷",
                "sort_order": sort_order,
            }
        )
    specs.sort(key=lambda item: (int(item.get("sort_order", 0)), str(item.get("volume_id", ""))))
    return specs


def _blank_volume_plan_fields() -> dict[str, dict[str, str]]:
    return {str(item["id"]): {"value": ""} for item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS}


def _default_volume_plan(spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "volume_id": str(spec.get("volume_id", "")),
        "volume_title": str(spec.get("volume_title", "") or ""),
        "sort_order": int(spec.get("sort_order", 0) or 0),
        "fields": _blank_volume_plan_fields(),
    }


def _normalize_volume_plan(source: Any, spec: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = spec or {}
    if not isinstance(source, dict):
        source = {}
    plan = _default_volume_plan(
        {
            "volume_id": spec.get("volume_id", source.get("volume_id", "")),
            "volume_title": spec.get("volume_title", source.get("volume_title", "")),
            "sort_order": spec.get("sort_order", source.get("sort_order", 0)),
        }
    )
    source_fields = source.get("fields", {})
    if isinstance(source_fields, dict):
        for item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
            field_id = str(item["id"])
            source_field = source_fields.get(field_id, {})
            if isinstance(source_field, dict):
                plan["fields"][field_id]["value"] = str(source_field.get("value", "") or "")
            elif isinstance(source_field, str):
                plan["fields"][field_id]["value"] = source_field
    return plan


def _normalize_volume_plans(raw_plans: Any, specs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_plans = [item for item in raw_plans if isinstance(item, dict)] if isinstance(raw_plans, list) else []
    by_id = {str(plan.get("volume_id", "")): plan for plan in source_plans if str(plan.get("volume_id", "")).strip()}
    by_title = {
        str(plan.get("volume_title", "")).strip(): plan
        for plan in source_plans
        if str(plan.get("volume_title", "") or "").strip()
    }
    if specs:
        plans: list[dict[str, Any]] = []
        for spec in specs:
            source = (
                by_id.get(str(spec.get("volume_id", "")))
                or by_title.get(str(spec.get("volume_title", "")).strip())
                or {}
            )
            plans.append(_normalize_volume_plan(source, spec))
        return plans
    normalized: list[dict[str, Any]] = []
    for index, source in enumerate(source_plans, start=1):
        spec = {
            "volume_id": source.get("volume_id", index),
            "volume_title": source.get("volume_title", f"第{index}卷"),
            "sort_order": source.get("sort_order", index),
        }
        normalized.append(_normalize_volume_plan(source, spec))
    normalized.sort(key=lambda item: (int(item.get("sort_order", 0)), str(item.get("volume_id", ""))))
    return normalized


def _parse_volume_plans_from_markdown(main_text: str, volume_specs: list[Any] | None) -> list[dict[str, Any]]:
    heading_pattern = re.compile(r"^###\s*第(\d+)卷规划(?:[:：]\s*(.*?))?\s*$", re.MULTILINE)
    matches = list(heading_pattern.finditer(main_text))
    if not matches:
        return []
    specs = _normalize_volume_specs(volume_specs)
    parsed: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        block_start = match.end()
        block_end = matches[index + 1].start() if index + 1 < len(matches) else len(main_text)
        block = main_text[block_start:block_end]
        display_index = int(match.group(1))
        heading_title = str(match.group(2) or "").strip()
        spec = specs[display_index - 1] if 0 <= display_index - 1 < len(specs) else {
            "volume_id": str(display_index),
            "volume_title": heading_title or f"第{display_index}卷",
            "sort_order": display_index,
        }
        plan = _default_volume_plan(spec)
        if heading_title and not specs:
            plan["volume_title"] = heading_title
        for plan_item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
            label = re.escape(str(plan_item["label"]))
            item_match = re.search(rf"^\s*-\s*{label}\s*[:：]\s*(.*)$", block, re.MULTILINE)
            if item_match:
                value = item_match.group(1).strip()
                plan["fields"][str(plan_item["id"])]["value"] = "" if value == "____" else value
        parsed.append(plan)
    return parsed


def _merge_book_outline_volume_plans(merged: dict[str, Any], incoming: dict[str, Any]) -> None:
    merged_plans = merged.setdefault("volume_plans", [])
    if not isinstance(merged_plans, list):
        merged["volume_plans"] = merged_plans = []
    incoming_plans = incoming.get("volume_plans", [])
    if not isinstance(incoming_plans, list):
        return
    by_id = {str(plan.get("volume_id", "")): plan for plan in merged_plans if isinstance(plan, dict)}
    by_title = {
        str(plan.get("volume_title", "")).strip(): plan
        for plan in merged_plans
        if isinstance(plan, dict) and str(plan.get("volume_title", "") or "").strip()
    }
    for incoming_plan in incoming_plans:
        if not isinstance(incoming_plan, dict):
            continue
        target = by_id.get(str(incoming_plan.get("volume_id", ""))) or by_title.get(
            str(incoming_plan.get("volume_title", "") or "").strip()
        )
        if target is None:
            merged_plans.append(deepcopy(incoming_plan))
            continue
        target_fields = target.setdefault("fields", {})
        incoming_fields = incoming_plan.get("fields", {})
        if not isinstance(target_fields, dict) or not isinstance(incoming_fields, dict):
            continue
        for plan_item in BOOK_OUTLINE_VOLUME_PLAN_FIELDS:
            field_id = str(plan_item["id"])
            current = target_fields.setdefault(field_id, {"value": ""})
            incoming_field = incoming_fields.get(field_id, {})
            if not isinstance(incoming_field, dict):
                continue
            incoming_value = str(incoming_field.get("value", "") or "").strip()
            if incoming_value and not str(current.get("value", "") or "").strip():
                current["value"] = incoming_value


def _append_supplement_once(data: dict[str, Any], supplement_title: str, content: str) -> None:
    supplements = data.setdefault("supplements", [])
    if not isinstance(supplements, list):
        data["supplements"] = supplements = []
    content = str(content or "").strip()
    if not content:
        return
    for supplement in supplements:
        if not isinstance(supplement, dict):
            continue
        if str(supplement.get("title", "") or "") == supplement_title and str(supplement.get("content", "") or "").strip() == content:
            return
    supplements.append({"title": supplement_title, "content": content})


def _merge_world_analysis_text(data: dict[str, Any], content: str, supplement_title: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if not text:
        return data
    if _looks_like_world_markdown(text):
        return merge_world_form(data, world_markdown_to_form(text))
    return merge_world_supplement(data, text, supplement_title=supplement_title)


def _world_entry_analysis_content(item: dict[str, Any]) -> str:
    for key in ("content_text", "content", "markdown", "text", "description", "summary"):
        value = str(item.get(key, "") or "").strip()
        if value:
            return value
    lines: list[str] = []
    ignored_keys = {"id", "book_id", "name", "title", "category", "created_at", "updated_at"}
    for key, value in item.items():
        if key in ignored_keys or value is None:
            continue
        if isinstance(value, (dict, list, tuple)):
            value_text = str(value).strip()
        else:
            value_text = str(value or "").strip()
        if value_text:
            lines.append(f"{key}：{value_text}")
    return "\n".join(lines).strip()


def _book_outline_schema_items() -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in BOOK_OUTLINE_FORM_SCHEMA:
        section_items = section.get("items", [])
        if isinstance(section_items, list):
            items.extend(item for item in section_items if isinstance(item, dict))
    return items


def _looks_like_book_outline_markdown(text: str) -> bool:
    return "# 书籍大纲模板" in text or "## 1.1 作品基础信息" in text or "## 1.2 篇幅与结构" in text


def _split_book_outline_supplements(text: str) -> tuple[str, list[dict[str, str]]]:
    parts = re.split(r"\n-{3,}\n", text)
    main_text = parts[0]
    supplements: list[dict[str, str]] = []
    for part in parts[1:]:
        cleaned = part.strip()
        if not cleaned:
            continue
        lines = cleaned.splitlines()
        title = "补充"
        if lines and lines[0].startswith("## "):
            title = lines[0].lstrip("#").strip()
            content = "\n".join(lines[1:]).strip()
        else:
            content = cleaned
        if content:
                supplements.append({"title": title, "content": content})
    return main_text, supplements


def world_form_defaults() -> dict[str, Any]:
    return _structured_form_defaults(WORLD_FORM_VERSION, WORLD_FORM_SCHEMA)


def world_form_to_markdown(data: dict[str, Any] | None) -> str:
    return _structured_form_to_markdown(
        normalize_world_form(data),
        WORLD_FORM_SCHEMA,
        "# 世界观设定模板",
    )


def world_markdown_to_form(markdown: str) -> dict[str, Any]:
    text = str(markdown or "").strip()
    data = world_form_defaults()
    if not text:
        return data
    if not _looks_like_world_markdown(text):
        return merge_world_supplement(data, text, supplement_title="AI/用户补充")
    return _structured_markdown_to_form(text, WORLD_FORM_SCHEMA, data, WORLD_FORM_VERSION)


def normalize_world_form(data: dict[str, Any] | None) -> dict[str, Any]:
    return _normalize_structured_form(data, WORLD_FORM_SCHEMA, WORLD_FORM_VERSION)


def merge_world_supplement(
    data: dict[str, Any] | None,
    content: str,
    *,
    supplement_title: str = "AI/用户补充",
) -> dict[str, Any]:
    normalized = normalize_world_form(data)
    _append_supplement_once(normalized, str(supplement_title or "补充"), str(content or ""))
    return normalized


def merge_world_form(base_data: dict[str, Any] | None, incoming_data: dict[str, Any] | None) -> dict[str, Any]:
    return _merge_structured_form(base_data, incoming_data, WORLD_FORM_SCHEMA, WORLD_FORM_VERSION)


def merge_world_analysis_payload(
    base_data: dict[str, Any] | None,
    *,
    world_form: Any = None,
    world_entries: Any = None,
    world_text: str = "",
) -> dict[str, Any]:
    data = normalize_world_form(base_data)
    if isinstance(world_form, dict):
        data = merge_world_form(data, world_form)
    elif isinstance(world_form, str) and world_form.strip():
        data = _merge_world_analysis_text(data, world_form, "AI世界观补充")
    world_text = str(world_text or "").strip()
    if world_text:
        data = _merge_world_analysis_text(data, world_text, "AI世界观补充")
    if isinstance(world_entries, list):
        for index, item in enumerate(world_entries, start=1):
            title = f"AI世界观补充 {index}"
            content = ""
            if isinstance(item, dict):
                name = str(item.get("name", "") or item.get("title", "") or "").strip()
                category = str(item.get("category", "") or "").strip()
                title = f"AI世界观补充：{name or category or index}"
                content = _world_entry_analysis_content(item)
            elif isinstance(item, str):
                content = item
            if content:
                data = _merge_world_analysis_text(data, content, title)
    return normalize_world_form(data)


def world_entry_template(name: str = "", category: str = "") -> str:
    return world_form_to_markdown(world_form_defaults())


def character_profile_template(name: str = "", role: str = "") -> str:
    data = character_profile_form_defaults(name, role)
    return character_profile_form_to_markdown(data, name, role)


def coerce_book_outline_markdown(text: str, title: str = "") -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return book_outline_template(title)
    if _looks_like_book_outline_markdown(cleaned):
        return book_outline_form_to_markdown(book_outline_markdown_to_form(cleaned, title), title)
    data = merge_book_outline_supplement(
        book_outline_form_defaults(title),
        title,
        cleaned,
        supplement_title="AI/用户补充",
    )
    return book_outline_form_to_markdown(data, title)


def coerce_world_markdown(text: str, name: str = "", category: str = "") -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return world_entry_template(name, category)
    if _looks_like_world_markdown(cleaned):
        return world_form_to_markdown(world_markdown_to_form(cleaned))
    return world_form_to_markdown(merge_world_supplement(world_form_defaults(), cleaned))


def coerce_character_markdown(
    text: str,
    name: str = "",
    role: str = "",
    previous_name: str = "",
    previous_role: str = "",
) -> str:
    cleaned = str(text or "").strip()
    if _is_blank_character_template(cleaned, name, role, previous_name, previous_role):
        return character_profile_template(name, role)
    data = character_profile_markdown_to_form(cleaned, name, role)
    return character_profile_form_to_markdown(data, name, role)


def _is_blank_character_template(
    text: str,
    name: str = "",
    role: str = "",
    previous_name: str = "",
    previous_role: str = "",
) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return True
    candidates = {
        character_profile_template(name, role),
        character_profile_template(name, ""),
        character_profile_template(previous_name or name, previous_role),
        character_profile_template(previous_name or name, ""),
    }
    return cleaned in {candidate.strip() for candidate in candidates if str(candidate or "").strip()}


def _coerce_structured_markdown(text: str, template: str, supplement_heading: str) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return template
    if _contains_template_headings(cleaned, template):
        return cleaned
    return f"{template}\n\n---\n\n## {supplement_heading}\n\n{cleaned}".strip()


def _contains_template_headings(text: str, template: str) -> bool:
    headings = [line.strip() for line in template.splitlines() if line.startswith("#")]
    if not headings:
        return False
    return all(heading in text for heading in headings)


def _structured_form_defaults(version: str, schema: list[dict[str, Any]]) -> dict[str, Any]:
    fields: dict[str, dict[str, Any]] = {}
    for item in _schema_items(schema):
        field_id = str(item["id"])
        field_type = str(item.get("type", "text"))
        if field_type == "checkbox":
            fields[field_id] = {"checked": False}
        elif field_type == "checkbox_text":
            fields[field_id] = {"checked": False, "value": ""}
        else:
            fields[field_id] = {"value": ""}
    return {"version": version, "fields": fields, "supplements": []}


def _structured_form_to_markdown(data: dict[str, Any], schema: list[dict[str, Any]], heading: str) -> str:
    fields = data.get("fields", {})
    lines: list[str] = [heading, ""]
    for section in schema:
        lines.extend([f"## {section['title']}", ""])
        for item in section.get("items", []):
            field = fields.get(str(item["id"]), {})
            field_type = str(item.get("type", "text"))
            label = str(item.get("label", ""))
            if field_type == "checkbox":
                marker = "x" if bool(field.get("checked", False)) else " "
                lines.append(f"- [{marker}] {label}")
            elif field_type == "checkbox_text":
                marker = "x" if bool(field.get("checked", False)) else " "
                value = str(field.get("value", "") or "").strip() or "____"
                lines.append(f"- [{marker}] {label}：{value}")
            elif field_type == "multiline":
                value = str(field.get("value", "") or "").strip()
                block = value or str(item.get("placeholder", "")).strip()
                lines.extend(["```text", block, "```"])
            else:
                value = str(field.get("value", "") or "").strip() or "____"
                lines.append(f"- {label}：{value}")
        lines.append("")
    for supplement in data.get("supplements", []):
        if not isinstance(supplement, dict):
            continue
        content = str(supplement.get("content", "") or "").strip()
        if not content:
            continue
        title = str(supplement.get("title", "") or "").strip() or "补充"
        lines.extend(["---", "", f"## {title}", "", content, ""])
    return "\n".join(lines).strip()


def _structured_markdown_to_form(
    text: str,
    schema: list[dict[str, Any]],
    defaults: dict[str, Any],
    version: str,
) -> dict[str, Any]:
    data = deepcopy(defaults)
    fields = data["fields"]
    main_text, supplements = _split_book_outline_supplements(text)
    for item in _schema_items(schema):
        field_id = str(item["id"])
        field_type = str(item.get("type", "text"))
        label = re.escape(str(item.get("label", "")))
        if field_type == "checkbox":
            match = re.search(rf"^\s*-\s*\[([ xX])\]\s*{label}\s*$", main_text, re.MULTILINE)
            if match:
                fields[field_id]["checked"] = match.group(1).lower() == "x"
        elif field_type == "checkbox_text":
            match = re.search(rf"^\s*-\s*\[([ xX])\]\s*{label}\s*[:：]\s*(.*)$", main_text, re.MULTILINE)
            if match:
                fields[field_id]["checked"] = match.group(1).lower() == "x"
                value = match.group(2).strip()
                fields[field_id]["value"] = "" if value == "____" else value
        elif field_type == "text":
            match = re.search(rf"^\s*-\s*{label}\s*[:：]\s*(.*)$", main_text, re.MULTILINE)
            if match:
                value = match.group(1).strip()
                fields[field_id]["value"] = "" if value == "____" else value
    code_blocks = re.findall(r"```text\s*\n(.*?)\n```", main_text, flags=re.DOTALL)
    multiline_items = [item for item in _schema_items(schema) if str(item.get("type")) == "multiline"]
    for item, block in zip(multiline_items, code_blocks):
        value = block.strip()
        placeholder = str(item.get("placeholder", "")).strip()
        fields[str(item["id"])]["value"] = "" if value == placeholder else value
    data["supplements"] = supplements
    return _normalize_structured_form(data, schema, version)


def _apply_structured_field_source(target: dict[str, Any], source: Any) -> None:
    if isinstance(source, dict):
        if "checked" in target:
            target["checked"] = _coerce_structured_checked(source.get("checked", target.get("checked", False)))
        if "value" in target:
            for key in ("value", "content", "content_text", "text", "description", "summary"):
                if key in source:
                    target["value"] = str(source.get(key, "") or "")
                    break
            if "checked" in target and "checked" not in source and str(target.get("value", "") or "").strip():
                target["checked"] = True
        return
    if isinstance(source, bool):
        if "checked" in target:
            target["checked"] = source
        elif "value" in target and source:
            target["value"] = "是"
        return
    if "value" in target:
        value = str(source or "")
        target["value"] = value
        if "checked" in target and value.strip():
            target["checked"] = True
    elif "checked" in target:
        target["checked"] = _coerce_structured_checked(source)


def _coerce_structured_checked(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "y", "x", "checked", "on", "是", "对", "勾选", "已勾选"}:
        return True
    if text in {"0", "false", "no", "n", "none", "off", "否", "不", "未勾选"}:
        return False
    return bool(text)


def _normalize_structured_form(data: dict[str, Any] | None, schema: list[dict[str, Any]], version: str) -> dict[str, Any]:
    defaults = _structured_form_defaults(version, schema)
    if not isinstance(data, dict):
        return defaults
    normalized = deepcopy(defaults)
    fields = data.get("fields", {})
    if isinstance(fields, list):
        fields = {
            str(item.get("id", "") or item.get("field_id", "") or item.get("label", "")).strip(): item
            for item in fields
            if isinstance(item, dict)
        }
    if not isinstance(fields, dict):
        fields = {}
    if not fields:
        fields = data
    if isinstance(fields, dict):
        for item in _schema_items(schema):
            field_id = str(item["id"])
            label = str(item.get("label", "") or "")
            source = fields.get(field_id, None)
            if source is None and label:
                source = fields.get(label, None)
            if source is None:
                continue
            target = normalized["fields"][field_id]
            _apply_structured_field_source(target, source)
    supplements = data.get("supplements", [])
    normalized["supplements"] = []
    if isinstance(supplements, list):
        for supplement in supplements:
            if isinstance(supplement, str):
                title = "补充"
                content = supplement.strip()
            elif isinstance(supplement, dict):
                title = str(supplement.get("title", "") or supplement.get("name", "") or "补充").strip() or "补充"
                content = str(
                    supplement.get("content", "")
                    or supplement.get("content_text", "")
                    or supplement.get("text", "")
                    or supplement.get("description", "")
                    or ""
                ).strip()
            else:
                continue
            if not content:
                continue
            normalized["supplements"].append(
                {
                    "title": title,
                    "content": content,
                }
            )
    return normalized


def _merge_structured_form(
    base_data: dict[str, Any] | None,
    incoming_data: dict[str, Any] | None,
    schema: list[dict[str, Any]],
    version: str,
) -> dict[str, Any]:
    merged = _normalize_structured_form(base_data, schema, version)
    incoming = _normalize_structured_form(incoming_data, schema, version)
    merged_fields = merged.get("fields", {})
    for field_id, incoming_field in incoming.get("fields", {}).items():
        if not isinstance(incoming_field, dict):
            continue
        current = merged_fields.get(field_id, {})
        if "checked" in incoming_field and bool(incoming_field.get("checked", False)):
            current["checked"] = True
        incoming_value = str(incoming_field.get("value", "") or "").strip()
        if incoming_value and not str(current.get("value", "") or "").strip():
            current["value"] = incoming_value
        merged_fields[field_id] = current
    for supplement in incoming.get("supplements", []):
        if isinstance(supplement, dict) and str(supplement.get("content", "") or "").strip():
            merged.setdefault("supplements", []).append(
                {
                    "title": str(supplement.get("title", "") or "AI/用户补充"),
                    "content": str(supplement.get("content", "") or "").strip(),
                }
            )
    return _normalize_structured_form(merged, schema, version)


def _schema_items(schema: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in schema:
        section_items = section.get("items", [])
        if isinstance(section_items, list):
            items.extend(item for item in section_items if isinstance(item, dict))
    return items


def _looks_like_world_markdown(text: str) -> bool:
    return "# 世界观设定模板" in text or "## 2.1 世界基础形态" in text or "## 2.2 时代与文明层级" in text
