# JackSkill (吴杰克 Jack 生产力武器库)

> 面向自媒体创作者、独立开发者与极客的开源 AI Skills 武器库。  
> 把最繁琐的文案诊断、脚本拆解、多平台适配与日常提效交给 Agent，获得立即可执行的交付成果。

[![Version](https://img.shields.io/badge/version-1.0.0-2563EB.svg?style=flat-square)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-16A34A.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JackAIStudio/jackskill?style=flat-square)](https://github.com/JackAIStudio/jackskill/stargazers)

**支持：豆包、WorkBuddy、Claude Code、Codex、Trae，以及其他支持 Skills 的 Agent。**

JackSkill 由 [吴杰克 Jack](https://github.com/JackAIStudio) 开源打造。基于自媒体工业化实战与 210+ 篇精修口播经验，旨在把独立开发者、剪辑师与内容创作者的实战工作流，转化为全网 Agent 通用的开箱即用规则库。

---

## ⚡ 为什么选择 JackSkill？

- **拒绝目录爆炸**：无论发布多少期视频，你的 Agent 目录里**永远只占 1 个位置（`/jack`）**；
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

- **日常提效**：直接输入：
  ```text
  /jack 这是我写的小红书开头，帮我看看为什么没人看：……
  ```
- **暗号调用**：看到视频里分享的编号时，直接输入：
  ```text
  /jack <编号>
  ```
- **查询所有可用编号**：输入：
  ```text
  /jack list
  ```

---

## 📋 当前已发布编号清单

实战编号正在持续根据当期短视频高频发布与更新中。输入 `/jack list` 即可秒级拉取最新全量列表。

---

## 👨‍💻 作者与个人 IP

- **作者**：[吴杰克 Jack](https://github.com/JackAIStudio)
- **定位**：独立开发者 / 自媒体实战玩家 / 极客工具创造者
- **旗下生态**：
  - **JackDSH**：开箱即用的桌面 AI 工作台
  - **JackVoice**：基于 Tauri + Rust 的桌面全局极速听写神器
  - **JackAICut**：达芬奇智能口播粗剪助手

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。
