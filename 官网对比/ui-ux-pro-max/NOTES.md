# ui-ux-pro-max 版 · 设计笔记

## Skill 来源
- 仓库：https://github.com/nextlevelbuilder/ui-ux-pro-max-skill（原作者仓库）
- Commit：`56ea9cf174ed86786187daa9de0e6247cb0747e4`
- 使用：`.claude/skills/ui-ux-pro-max/SKILL.md` + `references/quick-reference.md` + `references/pro-rules.md`，以及 `scripts/search.py`（读过源码：只读本地 CSV 做 BM25 检索，可选写 MASTER.md；未用 --persist）。
- 运行方式：`python3 -I` + 一个把 scripts 目录加入 sys.path 的小包装（`-I` 下脚本目录不在 sys.path，否则 `from core import` 失败）。

## Skill 要求的关键步骤/原则
1. 分析需求（产品类型、受众、风格关键词、技术栈）。
2. 新页面必须先跑 `--design-system` 拿到整套方向（版式模式、风格、配色 token、字体、效果、反模式）；可加 variance/motion/density 三个拨盘。
3. 用 `--domain` 补充单点检索；结果要核对是否贴合产品，0 结果不许编。
4. 按优先级执行规则：可访问性 > 触控交互 > 性能 > 风格一致 > 响应式 > 字体配色 > 动效……
5. 交付前跑 Pre-Delivery Checklist（对比度 4.5:1、焦点可见、无 emoji 图标、cursor-pointer、reduced-motion、375/768/1024/1440 断点、无横向滚动）。

## 实际检索与设计决定
- 命令：`"AI business assistant SaaS merchant retail" --design-system -p "Youzan Lobster" --variance 5 --motion 4 --density 3`
  → 品类 SaaS (General)；版式 **Hero + Features + CTA**（CTA：Hero 吸顶 + 底部）；风格 **Glassmorphism**；反模式“过度动画 + 默认深色”。
- 配色：完全采用脚本给的 token —— 主色 #2563EB、次色 #3B82F6、CTA 橙 #EA580C（配黑字，脚本已为对比度调整过）、背景 #F8FAFC、正文 #1E293B、弱文字 #475569、边框 #E2E8F0。没有改用龙虾客户端的 #155bd4（skill 让配色由产品类型决定）。只做浅色模式（脚本明确“深色支持但本产品避免”）。
- 字体：脚本推荐 Poppins（标题）/ Open Sans（正文），但都不含中文；按 skill 的“补充检索”再查 `"chinese simplified CJK" --domain typography`，得到 Noto Sans SC，作为中文回退字体。
- 版式：吸顶玻璃导航（带唯一主 CTA）→ Hero（标题 + 示意对话框，标注“界面示意”）→ 价值主张（通用 AI vs 龙虾）→ 四块能力卡片 → 随口一问 → AI 工作台连接器（5 板块 / 16 技能）→ 多渠道 → 数字员工 → FAQ（details 折叠）→ 底部 CTA → 页脚。间距用 density 3 的 4/8/24/32/48/64/96 刻度，max-width 1180。
- 玻璃效果：彩色模糊光斑做“鲜艳背景”，卡片 `backdrop-filter: blur(16px)` + 半透明白 + 细边；不支持时回退为近不透明白。
- 图标：一套 Lucide 风格内联 SVG（1.75 描边），装饰图标 aria-hidden；龙虾图标 base64 原尺寸以内使用，不拉伸。
- 动效：motion 4 对应 “Stagger List”（GSAP 3.12.5，cdnjs 固定版本），滚动进入时 y16 + 淡入、每项 60ms 错开；没用片段里的 back.out 回弹（片段自己的 Don't 说信息型 UI 别用），改 power2.out。GSAP 加载失败或 prefers-reduced-motion 时直接显示最终状态，内容不依赖 JS。
- 可访问性：跳转链接、可见焦点环、按钮/链接 ≥44px、标题层级 h1→h2→h3、scroll-padding 防吸顶遮挡焦点。

## 长处
- 不是纯“审美建议”，而是可检索的数据库 + 一键出完整设计系统，配色给成语义 token 并考虑了对比度修正，落地很快。
- 规则清单（可访问性、触控、响应式、reduced-motion）非常全，交付前自检有抓手。

## 局限
- 推荐偏通用 SaaS 模板：玻璃拟态 + 蓝/橙，辨识度一般，容易和大量 AI SaaS 落地页撞脸；不会主动考虑品牌已有色。
- 字体推荐默认面向拉丁文，中文页面需要自己补检索；`--design-system` 不感知语言。
- 检索是关键词 BM25，查询措辞稍变结果就会换风格，需要人判断取舍。
- 截图环境里 Google Fonts 和 cdnjs 被代理挡住，截图用的是系统中文字体、无动效回退状态（页面本身已按此设计成可降级）。
