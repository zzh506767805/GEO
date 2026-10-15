# emil-design-eng · 有赞龙虾官网

## Skill 来源

- 仓库：https://github.com/emilkowalski/skills （Emil Kowalski 本人仓库，MIT）
- 文件：`skills/emil-design-eng/SKILL.md`
- Commit：`2d228630ba1446365f614a108cb8252f1feda202`
- SKILL.md 没有引用别的文档。同时读了仓库 README，里面补了一条设计原则：用半透明阴影代替实色描边。

## Skill 要求的关键步骤和原则

1. 写任何动效之前先按顺序问四个问题：要不要动（看用户多频繁见到它）→ 为什么动 → 用什么缓动 → 时长多少。
2. 缓动用自定义强曲线（ease-out `cubic-bezier(.23,1,.32,1)`、ease-in-out `cubic-bezier(.77,0,.175,1)`），UI 动效不用 ease-in。UI 动效控制在 300ms 以内，营销和讲解性动效可以长一些。
3. 能按的东西按下时 `scale(0.97)`。不从 `scale(0)` 出现。hover 效果要包在 `@media (hover:hover) and (pointer:fine)` 里。
4. 只对 transform 和 opacity 做动画。会被反复触发的 UI 用 transition，不用 keyframes，这样中途可以打断。
5. 由键盘触发的操作不做动画。
6. 几个元素一起出现时错开 30–80ms。交叉淡入淡出看着别扭时，加一点 blur 把过渡糊过去。
7. Tabs 的做法：把 tab 列表复制一份，用 clip-path 只露出当前那一格。
8. prefers-reduced-motion 的意思是动效"更少、更轻"，不是一点都不动：保留 opacity，去掉位移。
9. 好的默认值比给很多选项重要。用户注意不到的细节累积起来，决定页面给人的感觉。

## 据此做的设计决定

- **配色**：中性灰阶，白底配近黑的文字 #1f2328。品牌蓝 #155bd4 只用在 kicker、选中状态和数据条这几处，深色模式下换成 #4d8dff。卡片和按钮全部用半透明阴影环（`0 0 0 1px rgba(0,0,0,.06)` 再叠柔和投影），不用实色边框。
- **字体**：Inter 加系统中文字体（PingFang / Noto Sans SC）。标题 600 字重、字距收紧，正文 15px，行高 1.65。中文标题按逗号把分句包成 inline-block，避免词在中间断开。
- **版式**：克制的 Vercel / Linear 式单栏。Hero 左边文案、右边对话示意，下面依次是差异点、四块能力（Tabs）、AI 工作台连接器、多渠道、数字员工流程、FAQ、CTA。
- **动效**（逐条走过决策框架）：
  - Hero 入场：首次访问只出现一次，所以可以加一点惊喜。600ms ease-out，translateY(8px) 加 opacity，各元素错开 60ms。
  - 滚动显现：IntersectionObserver 只触发一次，只动 transform 和 opacity。
  - 对话示意：点"随口一问"后，用户气泡用 240ms 过渡（带 2px blur）出现，接着是"正在查询"的点，然后出现示意数据条。数据条做 scaleX 增长，`transform-origin: left`，700ms，属于讲解性动效。每次点击都会作废上一轮的计时器，连续快点不会错乱。
  - Tabs：用复制列表加 clip-path，260ms ease-in-out，面板之间带 blur 淡入淡出。
  - 键盘例外：方向键、Home/End 切换 tab，或用 Enter/Space 触发按钮（通过 `event.detail === 0` 判断）时，一律不播放动画，直接切过去。
  - 按钮和 chip 按下时 scale(0.97)，160ms。hover 只在精确指针设备上生效。导航栏滚动后才显示底部细线。
  - FAQ 不做高度动画，只让答案 220ms 淡入，+ 号转成 −。
  - reduced-motion：去掉所有位移、缩放、blur 和数据条增长，只保留 opacity 淡入，"正在查询"的点也停下来。
- **内容约束**：对话示意只写"门店 A/B/C"这类占位，数据条不标数字，并注明"示意，非真实数据"。没有表单，不写价格，不用最高级。

## 长处与局限

- **长处**：动效判断很具体，什么时候动、动多快、用什么曲线、怎么打断都有明确规则。对键盘、触屏 hover、reduced-motion 这些可访问性细节覆盖得好。做出来的交互手感扎实，也很克制。
- **局限**：几乎只讲动效和组件细节，对品牌视觉、配色、字体、版式、信息架构基本不给方向，这部分只能按它的气质（Vercel / Linear 那种中性风格）自己推断。没有工作流程，也没有可交付物的清单。不涉及中文排版。对"商家官网"这类偏内容的营销页，帮助主要体现在交互打磨上。
