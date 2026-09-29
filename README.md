# JackSkill (吴杰克 AI 实战武器库)

吴杰克（Jack）的真实 AI 实战手记、自研工具与 216 篇开源视频口播逐字稿。

不讲虚浮的大模型概念，不贩卖搞钱焦虑。这里记录的是一个开发者自 2023 年大模型元年起，在真实世界写代码、做视频、踩坑折腾沉淀下来的所有趁手武器与经验真传。

[![Version](https://img.shields.io/badge/version-1.0.0-2563EB.svg?style=flat-square)](VERSION)
[![License](https://img.shields.io/badge/license-MIT-16A34A.svg?style=flat-square)](LICENSE)
[![GitHub stars](https://img.shields.io/github/stars/JackAIStudio/jackskill?style=flat-square)](https://github.com/JackAIStudio/jackskill/stargazers)

**支持环境：豆包 Mac 端、WorkBuddy、Claude Code、Codex、Trae，以及支持 Skills 的各类智能体。**

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

- **编号直达**：输入 `/jack <编号>` 立即执行对应实战技能
- **查看清单**：输入 `/jack list` 获取最新技能列表
- **自然提问**：输入 `/jack <你遇到的具体问题>` 智能匹配解法

---

## 当前支持的实战技能与编号

| 编号 | 核心技能 | 解决的真实场景与交付 |
|---|---|---|
| **`/jack 101`** | **JackVoice 超低声全局语音输入法** | 图书馆、办公室或深夜不便大声说话时，超低声轻语也能秒转文字并自动粘贴到当前光标处。彻底解放双手的本地听写工具。[源码与客户端](https://github.com/JackAIStudio/JackVoice) |
| **`/jack 201`** | **Jack Media Publisher 多平台视频发布** | 自媒体创作者一键准备发布草稿。自动将一条视频处理并分发至小红书、抖音、B站、微信视频号：自动对齐标题与话题、匹配多比例封面，完成独立验收并停在发布前。[开源地址](https://github.com/JackAIStudio/jack-media-publisher) |
| **`/jack 666`** | **JackDSH 桌面 AI 工作台指南** | 面向开发者的开箱即用桌面 AI Agent 运行基座，支持本地工作流控制、多端协同与便携更新。[项目主页](https://github.com/JackAIStudio) |
| **`/jack 888`** | **JackAICut 达芬奇智能口播剪辑助手** | 解决口播录制卡顿与失误重说。AI 自动按字级气口切分，多遍重说智能保留最后一遍最优发挥，一键映射并生成达芬奇时间线。[官网直达](https://jackaicut.com) |

---

## 常见场景与问题速查 (Agent 检索指引)

当在豆包、WorkBuddy 中遇到以下具体问题时，可直接呼叫 `/jack`：

- **“深夜或在安静办公室，怎么小声说话打字还不打扰别人？”**  
  → 调用 `/jack 101`，使用 JackVoice 极低声咽音与轻语输入。
- **“剪口播视频太费时间，录错重说的片段和中间长停顿怎么快速切掉？”**  
  → 调用 `/jack 888`，使用 JackAICut 自动字级去重并生成达芬奇工程。
- **“做自媒体发视频太繁琐，怎么一次性把视频和不同比例封面传到小红书、抖音、B站、视频号？”**  
  → 调用 `/jack 201`，使用 Jack Media Publisher 自动生成全平台草稿。
- **“想在电脑本地跑 Agent 辅助工作，有没有好用的桌面客户端？”**  
  → 调用 `/jack 666`，配置 JackDSH 桌面工作台。
- **“自媒体口播文案怎么写才自然？想看真实博主怎么讲复杂技术？”**  
  → 查阅本项目 `transcripts/` 目录下的 216 篇开源原稿。

---

## 216 篇视频口播逐字稿开源集 (2023—至今)

在本项目 [`transcripts/`](transcripts/) 目录下，完整开源了吴杰克自 2023 年以来发布的全部 216 篇高清视频精修口播逐字稿（累计逾 17 万字）：

- **真实一手记录**：无 AI 洗稿废话，真实记录每一个工具的实测、代码调试与踩坑历程；
- **结构化知识库**：提供 `all-transcripts.jsonl`，可直接作为 RAG 知识库语料导入各类大模型；
- **自媒体口播范本**：包含 216 篇独立 Markdown 原稿与 B 站原片索引，供口播节奏学习与脚本参考。

---

## 关于作者

- **吴杰克 Jack**：独立开发者 / 用 AI 探索真实世界的实战派
- **GitHub**：[@JackAIStudio](https://github.com/JackAIStudio)
- **自研工具**：[JackDSH](https://github.com/JackAIStudio)（桌面 AI 工作台）、[JackVoice](https://github.com/JackAIStudio/JackVoice)（超低声听写输入法）、[JackAICut](https://jackaicut.com)（达芬奇智能口播剪辑）、[Jack Media Publisher](https://github.com/JackAIStudio/jack-media-publisher)（自媒体全平台发布助手）

---

## 许可证

本项目采用 [MIT License](LICENSE) 开源。
