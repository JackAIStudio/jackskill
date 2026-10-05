# JackSkill（吴杰克 Jack 把自己开源了）
这里收录了他的开源工具、商业产品、全部视频的口播逐字稿，以及 2023 年至今全量跨平台自媒体视频互动数据（持续更新）。

支持环境：豆包、WorkBuddy、Codex、Claude Code，以及支持 Skills 的各类智能体。

---

## 快速安装与使用

### 1. 一行安装到本机

在终端执行：

```bash
npx -y skills add JackAIStudio/jackskill -g --all
```

### 2. 在 Agent 中调用

安装完成后，打开豆包、WorkBuddy 或任意支持的 Agent：

- **自然提问**：输入 `/jack <你想问的任何问题>` 智能匹配解法

- **编号直达**：输入 `/jack <编号>` 立即执行对应技能（如 `/jack 101`）
- **查看清单**：输入 `/jack list` 获取最新技能列表

- **一键更新**：直接对 Agent 说 **“更新 jackskill”**，全自动同步最新技能与逐字稿

---

## 常见场景速查

在 Agent 中遇到以下场景时，可以直接找 `/jack`：

- **日常交流、困惑与经历**
  - → `/jack 我想知道吴杰克是谁？过往视频讲过哪些内容？`
  - → `/jack 想做自媒体录视频，但面对镜头感到害怕，该怎么调整？`
  - → `/jack 自媒体口播文案怎么写才自然？`
- **自媒体选题、数据分析与算法避坑**
  - → `/jack 你播放量最高的视频是哪几期？讲了什么？`
  - → `/jack 有哪些视频被平台限流了？怎么复盘原因？`
  - → `/jack 技术分享内容在 B 站和小红书的表现有什么差异？`
- **“深夜或在安静办公室，怎么小声说话打字还不打扰别人？”**
  - → `/jack 101`，使用 JackVoice 极低声轻语转文字。
- **“我是达芬奇用户，我想提高剪辑效率。”**
  - → `/jack 888`，使用 JackAICut 辅助剪辑。
- **“做自媒体发视频太繁琐，怎么一键把视频发布至小红书、抖音、B站、视频号？”**
  - → `/jack 201`，使用 Jack Media Publisher 准备小红书、抖音、B站、视频号草稿。
- **“想在电脑本地跑 Agent 辅助工作，有没有好用的桌面客户端？”**
  - → `/jack 666`，配置 JackDSH 桌面工作台。
---

## 当前支持的编号工具

| 编号 | 工具 | 场景与说明 |
| :--- | :--- | :--- |
| **`/jack 101`** | **JackVoice 语音输入** | 超低声语音输入转文字。在图书馆或安静办公室轻声说话即可转文字，自带语音备忘录。[源码与客户端](https://github.com/JackAIStudio/JackVoice) |
| **`/jack 201`** | **Jack Media Publisher 多平台视频发布** | 将视频分发至小红书、抖音、B站、微信视频号，对齐标题与话题、匹配多比例封面，生成草稿供你验收后发布。[开源地址](https://github.com/JackAIStudio/jack-media-publisher) |
| **`/jack 666`** | **JackDSH 桌面 AI 工作台指南** | 可定制、开箱即用的桌面 AI 工作台，内置手机远程控制。[项目主页](https://github.com/JackAIStudio) |
| **`/jack 888`** | **JackAICut 达芬奇智能口播剪辑助手** | 结合文字、画面和声音等多维度，辅助剪辑达芬奇时间线。[官网直达](https://jackaicut.com) |

---

## 视频口播逐字稿 (2023 至今，持续更新)

在本项目 [`transcripts/`](transcripts/) 目录下，收录了吴杰克发布的全部视频口播逐字稿，跟随最新视频同步更新。

---

## 自媒体视频互动数据 (data/videos.jsonl)

为了开源真实的创作 Context，本项目不仅开源口播文案，还将 2023 年至今发布的 400+ 期视频在四大平台（B 站、小红书、抖音、微信视频号）的真实数据完整开源在 [`data/videos.jsonl`](data/videos.jsonl)。

### 数据特点与价值

1. **真实数据，拒绝粉饰**：不只记录爆款，扑街、低播放和被平台限流的视频数据同样保留，供创作者客观参考什么样的内容真正有流量、什么样的选题容易受限。
2. **数据与逐字稿双向索引**：每条数据记录的 `transcript` 字段直连对应的 Markdown 逐字稿文件。读者和 Agent 在看到播放、收藏等指标的同时，能直接翻看当期视频说了什么、开头怎么抓人。
3. **跨平台调性对比**：同一期视频在四个平台的分发数据同步列出，直观展示长视频与短视频平台的算法差异与受众偏好。

### 字段格式契约

数据以 JSON Lines（每行一个独立 JSON）格式存储，极简结构示例：

```json
{
  "id": "2026-10-04_开源一个语音输入+备忘录二合一工具",
  "date": "2026-10-04",
  "topic": "开源一个语音输入+备忘录二合一工具",
  "duration": 139,
  "transcript": "transcripts/md/2026-10-04_开源一个语音输入+备忘录二合一工具.md",
  "summary": {
    "views": 1899,
    "likes": 74,
    "collects": 70,
    "shares": 13,
    "comments": 3
  },
  "platforms": {
    "bilibili": { "views": 192, "likes": 12, "collects": 20, "shares": 0, "comments": 0, "url": "https://..." },
    "xiaohongshu": { "views": 615, "likes": 36, "collects": 30, "shares": 3, "comments": 2 },
    "douyin": { "views": 718, "likes": 25, "collects": 11, "shares": 0, "comments": 1 },
    "wechat_channels": { "views": 374, "likes": 1, "collects": 9, "shares": 10, "comments": 0 }
  }
}
```

### 快速读取示例

任何语言或 Agent 均可直接读取与分析。Python 示例：

```python
import json

with open("data/videos.jsonl", "r", encoding="utf-8") as f:
    videos = [json.loads(line) for line in f]

# 查按总播放量排序的前 5 期视频
top_videos = sorted(videos, key=lambda v: v["summary"]["views"], reverse=True)[:5]
for v in top_videos:
    print(f"[{v['date']}] {v['topic']} - 总播放: {v['summary']['views']}")
```

---

## 关于作者

- **GitHub**：[@JackAIStudio](https://github.com/JackAIStudio)
- **小红书**：[吴杰克Jack](https://www.xiaohongshu.com/user/profile/6102c7cb000000002002cae4)
- **B 站**：[吴杰克Jack](https://space.bilibili.com/1698895777)
- **抖音**：[吴杰克Jack](https://v.douyin.com/RSk1LT4I7po)
- **X（推特）**：[@JackAIStudio999](https://x.com/JackAIStudio999)
- **微信号**：JackAIStudio

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
