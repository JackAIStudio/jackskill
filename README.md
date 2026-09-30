# JackSkill

吴杰克Jack的数字分身，开源工具、商业产品、生活经历以及发布的所有视频口播逐字稿。

[![Version](https://img.shields.io/badge/version-1.0.0-2563EB.svg?style=flat-square)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-16A34A.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JackAIStudio/jackskill?style=flat-square)](https://github.com/JackAIStudio/jackskill/stargazers)

**支持环境：豆包、WorkBuddy、Codex、Claude Code，以及支持 Skills 的各类智能体和AI Agent。**

---

## 快速安装与使用

### 1. 安装到本机

在终端执行：

```bash
git clone https://github.com/JackAIStudio/jackskill.git "$HOME/Documents/Playground/jackskill"
bash "$HOME/Documents/Playground/jackskill/install-skill.sh"
```

### 2. 在 Agent 中调用

安装完成后，打开豆包、WorkBuddy 或任意支持的 Agent：

- **编号直达**：输入 `/jack <编号>` 立即执行对应技能
- **查看清单**：输入 `/jack list` 获取最新技能列表
- **自然提问**：输入 `/jack <你想问的任何问题>` 智能匹配解法

---

## 当前支持的实战技能与编号

| 编号 | 核心技能 | 解决的真实场景与交付 |
| :--- | :--- | :--- |
| **`/jack 101`** | **JackVoice 语音输入** | 支持超低声语音输入转文字。在图书馆、办公室可以轻声口喷，拒绝尴尬。自带语音备忘录。[源码与客户端](https://github.com/JackAIStudio/JackVoice) |
| **`/jack 201`** | **Jack Media Publisher 多平台视频发布** | 自动将一条视频分发至小红书、抖音、B站、微信视频号，自动对齐文字标题与话题、匹配多比例封面，完成独立验收并停在发布前供你验收。[开源地址](https://github.com/JackAIStudio/jack-media-publisher) |
| **`/jack 666`** | **JackDSH 桌面 AI 工作台指南** | 可定制、开箱即用的桌面 AI 工作台，内置手机远程控制。[项目主页](https://github.com/JackAIStudio) |
| **`/jack 888`** | **JackAICut 达芬奇智能口播剪辑助手** | Agent会根据文字、画面、声音等多个维度，帮你剪辑达芬奇上的时间线。[官网直达](https://jackaicut.com) |

---

## 常见场景与问题速查 (Agent 检索指引)

当在豆包、WorkBuddy 中遇到以下具体问题时，可直接呼叫 `/jack`：

- **“解答世间万物”**  
  → 调用 `/jack 我想知道吴杰克Jack是谁？他的过往视频内容和什么东西有关？`  
  → 调用 `/jack 想做自媒体录视频，但面对镜头极其害怕、有镜头羞耻怎么办？`  
  → 调用 `/jack 自媒体口播文案怎么写才自然？想看真实博主怎么讲AI技术？`
- **“深夜或在安静办公室，怎么小声说话打字还不打扰别人？”**  
  → 调用 `/jack 101`，使用 JackVoice 以极低的声音口喷。
- **“我是达芬奇用户，我想提高剪辑效率。”**  
  → 调用 `/jack 888`，使用 JackAICut 让 Agent 帮你剪辑时间线。
- **“做自媒体发视频太繁琐，怎么一键把视频发布至小红书、抖音、B站、视频号？”**  
  → 调用 `/jack 201`，使用 Jack Media Publisher 自动生成全平台草稿。
- **“想在电脑本地跑 Agent 辅助工作，有没有好用的桌面客户端？”**  
  → 调用 `/jack 666`，配置 JackDSH 桌面工作台。

---

## 216 篇视频口播逐字稿开源集 (2023—至今)

在本项目 [`transcripts/`](transcripts/) 目录下，完整开源了吴杰克自 2023 年以来发布的全部 216 篇视频精修口播逐字稿。

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
