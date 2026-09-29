# JackSkill (吴杰克 AI 生产力武器库)

> 面向每一个想用 AI 偷懒、提效、搞钱与解决麻烦事的实战工具箱。  
> 不讲虚的大模型概念，把工作、副业、内容创作与真实生活中的具体问题交给 Agent，获得立即可执行的下一步。

[![Version](https://img.shields.io/badge/version-1.0.0-2563EB.svg?style=flat-square)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-16A34A.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JackAIStudio/jackskill?style=flat-square)](https://github.com/JackAIStudio/jackskill/stargazers)

**支持：豆包、WorkBuddy、Claude Code、Codex、Trae，以及其他支持 Skills 的 Agent。**

JackSkill 由 [吴杰克 Jack](https://github.com/JackAIStudio) 开源打造。它不是象牙塔里的代码玩具，而是吴杰克在真实世界里折腾技术、自媒体实战、副业探索与生活观察的“第二大脑与经验结晶”。

我们不做空谈的理论，只把最接地气的实操心法与避坑指南，沉淀为普通人在豆包、WorkBuddy 里开箱即用的实用武器。

---

## ⚡ 为什么选择 JackSkill？

- **拒绝目录爆炸**：无论发布多少期视频与技能，你的 Agent 目录里**永远只占 1 个位置（`/jack`）**；
- **通吃国内主流 Agent**：开箱支持豆包 Mac App、腾讯 WorkBuddy、Trae Solo 等国内主流客户端，无需复杂配置；
- **视频暗号动态直达**：在短视频评论区领到三位数字暗号后，直接在输入框敲一行 `/jack <编号>`，Agent 自动联网拉取最新规范并当场执行；
- **零感知静默更新**：日常新增编号免升级直接用；核心架构升级只需在聊天框回复 `1`，AI 自动在后台静默升级。

---

## 🚀 快速开始

### 1. 一键安装（推荐）

在终端执行：

```bash
git clone https://github.com/JackAIStudio/jackskill.git "$HOME/Documents/Playground/jackskill"
bash "$HOME/Documents/Playground/jackskill/install-skill.sh"
```

### 2. 在 Agent 中使用

安装完成后，打开豆包、WorkBuddy 或任何 Agent：

- **大白话提问（智能匹配）**：直接输入：
  ```text
  /jack 我想做个事情，但卡在……帮我看看怎么搞
  ```
- **视频暗号直达**：看到短视频里分享的编号时，直接输入：
  ```text
  /jack <编号>
  ```
- **查询当前所有可用编号**：输入：
  ```text
  /jack list
  ```

---

## 📋 当前已发布王牌编号清单（首发）

输入 `/jack list` 即可秒级拉取最新全量列表：

| 编号 | 核心技能 | 对应视频原片 | 实战价值与一键交付 |
|---|---|---|---|
| **`/jack 101`** | **JackVoice 超低声语音输入法** | [📺 B站原片](https://www.bilibili.com/video/BV19qju6dEA7/) | 超低声轻语也能秒转文字并自动粘贴，彻底解放双手的懒人免打字神器 |
| **`/jack 365`** | **全平台免费不限速下载神器** | [📺 B站原片](https://www.bilibili.com/video/BV1xVho6UE2N/) | 免开网盘会员，开源磁力下载器 qBittorrent 调优与最新优质 Tracker 节点生成 |
| **`/jack 666`** | **JackDSH 桌面 AI 工作台全指南** | [📺 B站原片](https://www.bilibili.com/video/BV1v5aT6ZETi/) | 最新 0.1.7 RC2 内核便携包、免 Key 订阅大模型与手机扫码遥控实战 |
| **`/jack 888`** | **达芬奇 AI 智能口播剪辑 (JackAICut)** | [📺 B站原片](https://www.bilibili.com/video/BV1DBh862EPh/) | 口播字级气口切分与失误重说智能剔除，一秒生成达芬奇时间线与官网直达 |

---

## 📚 吴杰克全量视频口播逐字稿开源集 (2023—至今)

在本项目 [`transcripts/`](transcripts/) 目录下，我们正式开源了吴杰克过去 3 年半公开发布的 **全部 215 篇高清视频精修口播逐字稿（累计逾 17 万字）**！

- **`transcripts/README.md`**：包含全部 215 篇视频的完整索引大表、时长与 B 站高清原片直达链接；
- **`transcripts/all-transcripts.jsonl`**：专供 AI 智能体与 RAG 向量检索一键导入的结构化单文件；
- **`transcripts/md/`**：215 篇独立 Markdown 原稿，无论是做自媒体脚本拆解、学习口播结构，还是喂给大模型做知识库，**完全免费开源自取**！

---

## 👨‍💻 关于作者：吴杰克 Jack

- **GitHub**：[@JackAIStudio](https://github.com/JackAIStudio)
- **定位**：用 AI 探索真实世界的实战派 / 独立开发者 / 生命力折腾党
- **旗下自研工具矩阵**：
  - **JackDSH**：开箱即用的桌面 AI 工作台
  - **JackVoice**：基于 Tauri + Rust 的桌面全局极速听写神器
  - **JackAICut**：达芬奇智能口播粗剪助手

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。
