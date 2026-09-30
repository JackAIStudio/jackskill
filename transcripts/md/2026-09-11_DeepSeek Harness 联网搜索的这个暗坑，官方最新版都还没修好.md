# DeepSeek Harness 联网搜索的这个暗坑，官方最新版都还没修好

- **视频原片**：[B站观看](https://www.bilibili.com/video/BV1pkYm6REjf/)
- **发布日期**：2026-09-11
- **视频时长**：01:20 (80 秒)

---

## 逐字稿

我在Deepseek Harness中明明选择的是Grok
为什么我自己的Deepseek的余额在掉
后来我就问Agent我说这是怎么回事
结果AI跟我说
我们的所有的联网搜索操作都是要被Deepseek接管的
我本来还以为出现这个问题是因为我使用的是Gemini和Grok的OpenOARS登录
后来我问了一下结果就算是
用他们自己的API key
也一样
因为这个东西是被写死在源码里的
我的想法是这样既然我都使用Grok模型了
那我肯定是希望Agent它在调用Tool的时候也走的是Grok模型这样子额度才统一啊
那要不然的话我们接入GPT接入gemini结果联网搜索走的还是Deepseek一是很奇怪二是我觉得我们这个余额就直接在不知不觉中就没了
为了解决这个问题我就让Agent帮我实现grok和gemini的搜索
当我们选择的是非Deepseek的模型的时候
要走对应渠道的联网搜索
如你们所见这个插件现在已经开源了
Groq走的是X也就是推特的搜索
Jermaine呢走的就是Google那一套
大家如果在使用DSH的时候也遇到了这样的问题那你们可以让你们的agent安装这个插件就可以了
这里是Jack希望这期视频对你有帮助我们下个视频见拜拜
