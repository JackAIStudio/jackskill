# data/videos.jsonl

跨平台自媒体数据，**本仓库的唯一真源**。全网四大平台（B 站、抖音、小红书、微信视频号）每一期的真实播放、点赞、收藏、分享、评论都在这里。

- 一行一期，标准 JSON Lines：**每行一个完整 JSON 对象，行与行之间没有逗号，末尾一个换行**。
- 文件按 `date` 倒序排列（最新在前）。
- 文件里不要写注释、不要留空行、不要包成数组。

这个文件**由人（或 Agent）直接编辑**，没有生成器。改完跑一次校验：

```bash
node scripts/check-data.mjs
```

## 字段

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | string | **推导出来的**：`date + "_" + topic 里的空白换成下划线`。不要自己起名。 |
| `date` | string | `YYYY-MM-DD`，这一期的发布日期。**必须与逐字稿文件名里的日期一致。** |
| `topic` | string | 这一期的标题。有逐字稿时取自文件名。 |
| `duration` | int | 时长（秒）。不知道就填 `0`。 |
| `transcript` | string \| null | 逐字稿路径，如 `transcripts/md/2026-10-08_标题.md`；没有就填 `null`。 |
| `summary` | object | 四个平台相加的汇总，见下。**必须等于各平台之和。** |
| `platforms` | object | 按平台分的数据，见下。**某个平台没有数据就整个不写这个键。** |

`summary` 固定五个非负整数：

```json
{ "views": 726, "likes": 5, "collects": 4, "shares": 1, "comments": 0 }
```

`platforms` 的键只能是这四个：`bilibili`、`douyin`、`xiaohongshu`、`wechat_channels`。
每个平台对象：

```json
{
  "title": "该平台上的标题（各平台会不一样，可以带 #话题）",
  "url": "该平台的作品链接",
  "views": 3, "likes": 0, "collects": 0, "shares": 0, "comments": 0
}
```

`url` 有一条约定：**B 站和抖音填作品永久直链；小红书和微信视频号填平台主页**（`https://www.xiaohongshu.com` 与 `https://channels.weixin.qq.com`）。后两者的笔记链接受风控和 Session 限制，很快会失效，所以数据里不存。

## 完整示例

```json
{"id":"2026-10-08_我们该如何验证AI说的对不对","date":"2026-10-08","topic":"我们该如何验证AI说的对不对","duration":85,"transcript":"transcripts/md/2026-10-08_我们该如何验证AI说的对不对.md","summary":{"views":726,"likes":5,"collects":4,"shares":1,"comments":0},"platforms":{"bilibili":{"title":"我们该如何验证AI说的对不对","url":"https://www.bilibili.com/video/BV1VwHy6KESo/","views":3,"likes":0,"collects":0,"shares":0,"comments":0},"douyin":{"title":"我们该如何验证AI说的对不对 #AI #开源","url":"https://www.douyin.com/video/7693964829530344731","views":638,"likes":4,"collects":3,"shares":0,"comments":0},"xiaohongshu":{"title":"我们该如何验证AI说的对不对","url":"https://www.xiaohongshu.com","views":26,"likes":1,"collects":1,"shares":0,"comments":0},"wechat_channels":{"title":"我们该如何验证AI说的对不对 #AI","url":"https://channels.weixin.qq.com","views":59,"likes":0,"collects":0,"shares":1,"comments":0}}}
```

这一期的 `summary` 就是四个平台相加：views 3+638+26+59 = 726，likes 0+4+1+0 = 5，以此类推。

## 加一期怎么做

1. 先把逐字稿放进 `transcripts/md/`，文件名 `YYYY-MM-DD_标题.md`，头部写「发布日期」。
2. 在 `videos.jsonl` 里加一行：`id` 和 `date` 都从文件名来，`transcript` 指向该文件。
3. `summary` 按各平台相加算出来填上。
4. 没有数据的平台**不要写那个键**（不要写成一堆 0）。
5. `node scripts/check-data.mjs` 通过即可。

## 校验会拦什么

`check-data.mjs` 分两档。**错误**会阻止 `build-site.mjs` 生成页面（坏数据不许发布），**提醒**只喊一声。

**错误**：

- `summary` 的任一指标与各平台之和对不上——全站所有数字都是这个口径
- `id` 与 `date` + `topic` 推导出来的不一致
- `transcript` 指向的文件不存在，或文件名没有 `YYYY-MM-DD_` 前缀
- `date` 与逐字稿文件名里的日期不一致
- `id` 重复、日期格式不对、指标不是非负整数、平台名不认识

**提醒**：

- 同一条视频疑似记了两次（判据：清洗标题后相同或包含，且相隔不超过 30 天）
- md 头部的「发布日期」与文件名日期不一致
- 某期既没有逐字稿也没有任何平台数据
- 某平台没有链接

## 两件值得记住的事

**日期是最容易出错的地方。** 一次批量整理逐字稿时，29 篇的文件名和头部被统一写成了同一天，真实发布日却散在两个月里。结果页面上一整批作品挤在同一天、播放量全是 0——因为文件名日期一旦写错，那一期就再也对不上真实数据了。校验能查出「两处日期不一致」，但查不出「两处日期一起写错」，那个只能靠人对。

**不要用「看起来对」来合并记录。** 曾经用相似度阈值判断两条记录是不是同一条视频，结果那批英文标题的内容互相能撞到 0.90 以上（`I am Chinese, like to teach you Chinese` 对 `Chinese Teaching : Learn To Say Hello`），会误合。现在改成只报给人看，不自动合并。
