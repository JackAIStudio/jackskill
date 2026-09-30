# JackSkill

吴杰克 Jack 把自己开源了。这里收录了他做的几个工具，以及 2023 年至今全部视频的口播逐字稿，持续更新。按需取用，一起成长。

[![Version](https://img.shields.io/badge/version-1.2.1-2563EB.svg?style=flat-square)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-16A34A.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JackAIStudio/jackskill?style=flat-square)](https://github.com/JackAIStudio/jackskill/stargazers)

这个 skill 体积很轻，内容都在 GitHub 上，本地几乎零占用。支持环境：豆包、WorkBuddy、Codex、Claude Code，以及支持 Skills 的各类智能体。

---

## 快速安装与使用

### 1. 一行安装到本机

在终端执行：

```bash
npx -y skills add JackAIStudio/jackskill -g --all
```

### 2. 在 Agent 中调用

安装完成后，打开豆包、WorkBuddy 或任意支持的 Agent：

- **编号直达**：输入 `/jack <编号>` 立即执行对应技能（如 `/jack 101`）
- **查看清单**：输入 `/jack list` 获取最新技能列表
- **自然提问**：输入 `/jack <你想问的任何问题>` 智能匹配解法
- **一键更新**：直接对 Agent 说 **“更新 jackskill”**，全自动同步最新技能与逐字稿

---

## 当前支持的编号工具

| 编号 | 工具 | 场景与说明 |
| :--- | :--- | :--- |
| **`/jack 101`** | **JackVoice 语音输入** | 超低声语音输入转文字。在图书馆或安静办公室轻声说话即可转文字，自带语音备忘录。[源码与客户端](https://github.com/JackAIStudio/JackVoice) |
| **`/jack 201`** | **Jack Media Publisher 多平台视频发布** | 将视频分发至小红书、抖音、B站、微信视频号，对齐标题与话题、匹配多比例封面，生成草稿供你验收后发布。[开源地址](https://github.com/JackAIStudio/jack-media-publisher) |
| **`/jack 666`** | **JackDSH 桌面 AI 工作台指南** | 可定制、开箱即用的桌面 AI 工作台，内置手机远程控制。[项目主页](https://github.com/JackAIStudio) |
| **`/jack 888`** | **JackAICut 达芬奇智能口播剪辑助手** | 结合文字、画面和声音等多维度，辅助剪辑达芬奇时间线。[官网直达](https://jackaicut.com) |

---

## 常见场景速查

在 Agent 中遇到以下场景时，可以直接找 `/jack`：

- **日常交流、困惑与经历**  
  → `/jack 我想知道吴杰克是谁？过往视频讲过哪些内容？`  
  → `/jack 想做自媒体录视频，但面对镜头感到害怕，该怎么调整？`  
  → `/jack 自媒体口播文案怎么写才自然？`
- **“深夜或在安静办公室，怎么小声说话打字还不打扰别人？”**  
  → `/jack 101`，使用 JackVoice 极低声轻语转文字。
- **“我是达芬奇用户，我想提高剪辑效率。”**  
  → `/jack 888`，使用 JackAICut 辅助剪辑。
- **“做自媒体发视频太繁琐，怎么一键把视频发布至小红书、抖音、B站、视频号？”**  
  → `/jack 201`，使用 Jack Media Publisher 准备小红书、抖音、B站、视频号草稿。
- **“想在电脑本地跑 Agent 辅助工作，有没有好用的桌面客户端？”**  
  → `/jack 666`，配置 JackDSH 桌面工作台。

---

## 视频口播逐字稿 (2023 至今，持续更新)

在本项目 [`transcripts/`](transcripts/) 目录下，收录了吴杰克自 2023 年以来发布的全部视频口播逐字稿，跟随最新视频同步更新。

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
