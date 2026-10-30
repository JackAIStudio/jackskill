# data/ 下的两份真源

`data/` 里是两个文件，各自是一份独立真源，**口径不同，不要混着读**：

| 文件 | 是什么 | 粒度 | 能相加吗 |
| :--- | :--- | :--- | :--- |
| `videos.jsonl` | 每一期视频的播放、点赞、收藏、分享、评论 | 一行一期 | 能。`summary` 就是四平台之和 |
| `followers.jsonl` | 四个账号的粉丝数 | 一行一天（快照） | **不能。**账号级存量，也不跨平台相加 |

加粉丝数的时候最容易犯的错，是把它当成第六个指标塞进 `videos.jsonl`。不行：作品指标是「一行一期、可以累加」的量，粉丝是「一天一个、只有当下」的量。混在一起，页面上迟早会有人把粉丝加进「合计」。所以它单独一个文件、单独一道校验（`scripts/check-followers.mjs`）、页面上也单独一块。

---

# data/videos.jsonl

跨平台自媒体数据，**作品部分唯一真源**。全网四大平台（B 站、抖音、小红书、微信视频号）每一期的真实播放、点赞、收藏、分享、评论都在这里。

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

还有一个**可选**字段 `limited`，只在平台不给数时出现，见下面「口径」一节：

```json
"limited": { "reason": "减少作品推荐", "lastRead": "2026-10-19" }
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

## 指标怎么更新

`data/videos.jsonl` 里的数字不会自己变，得有人定期从四个平台读回来写进去。用 `scripts/refresh-stats.py`：

```bash
# B 站：公开接口，免登录，一次刷全部
python3 scripts/refresh-stats.py --platform bilibili

# 另外三个平台：先在已登录的浏览器里 observe 列表页，把输出存成文件
python3 scripts/refresh-stats.py --platform douyin --in /tmp/dy-page.txt
python3 scripts/refresh-stats.py --platform xiaohongshu --in /tmp/xhs-1.txt
python3 scripts/refresh-stats.py --platform wechat_channels --in /tmp/wx-page.txt

# 先看会改什么，不落盘
python3 scripts/refresh-stats.py --platform douyin --in /tmp/dy-page.txt --dry-run
```

刷完跑 `node scripts/check-data.mjs && node scripts/build-site.mjs`，`summary` 由脚本重算，不用手算。

**B 站不需要开浏览器。** `api.bilibili.com/x/web-interface/view?bvid=` 免登录返回 `view/like/favorite/share/reply`，和创作者后台一致，而且字段有名字，不存在看错列的问题。

**小红书和微信视频号的后台列表页，数字没有表头，只能靠位置判断。** 列序写在脚本的 `PLATFORM_SPEC` 里：

| 平台 | 列序 |
| :--- | :--- |
| 小红书 | 观看 评论 点赞 收藏 分享 |
| 微信视频号 | 播放 点赞 评论 分享 收藏 |

小红书那条最反直觉（收藏在分享前面），是拿五期旧数据反推验证出来的——只有这一种排法能同时对上。按直觉写成「观看/点赞/评论/收藏/分享」，每一条都会错位。**改列序之前先拿旧数据反推验证一遍。**

**抖音不走列表页，走 `work_list` 接口的 `statistics` 对象**（`play_count` / `digg_count` / `comment_count` / `share_count` / `collect_count`）。字段有名字，全是精确整数，不用猜列序也没有四舍五入。同一个 JSON 里别处还有 `view_count`，那是话题标签的计数，不是播放量——按它抓会把每条都读成 0 或乱数。**按 `aweme_id` 配对，不要按日期或标题**：同一天发两条是常事，标题也会被改写。脚本的 `parse_dy_json()` 认不出 `statistics` 时才退回列表页解析。

**小红书和视频号拿不到作品 id，只能按标题全局一对一配对，不能只看同一天。** 平台侧的发布日期和仓库日期经常差一天（09-10 对 09-09、08-30 对 08-29），标题还会被改写（「我做了一个达芬奇插件」→「我开发了个达芬奇插件」）。只按当天匹配时，这类记录会永远落到「未匹配」，数字一直停在旧快照上——小红书 302 条里曾经有 37 条是这样。现在走 `pair_items_to_rows()`：日期差 40 天以内才参与打分，按标题相似度加日期接近度排序、贪心一对一分配，要甩开第二名一定余量才认；配不上的照实报未匹配，不硬塞。

**口径：0 就是 0，拿不到数单独标。** 平台返回数字 `0` 且作品正常可见，就是没人看，照实记；平台不给数了（横杠 `-`、`self_see`、已删除、已下架），**保留最后读数**并加一个可选的 `limited` 字段：

```json
"douyin": {
  "views": 164, "likes": 0, "collects": 1, "shares": 0, "comments": 0,
  "limited": { "reason": "减少作品推荐", "lastRead": "2026-10-19" }
}
```

`limited` 只在真的拿不到数时出现，两个字段：`reason`（平台给的状态）和 `lastRead`（最后一次读到数字的日期，不是发现限流的日期——前者能证明，后者只能猜）。平台哪天重新给数了，这个键会被摘掉。

`reason` 写平台原话。**`仅自己可见` 是最容易看错的一种**：`play_count` 写着 0，看着像真没人看，其实是作品只对作者可见、平台不给统计。实测 80 条里 `self_see=true` 的 8 条 `play_count` 全是 0，`self_see=false` 的 72 条全部大于 0，没有例外。

不清零的理由：被限流之前那些播放真实发生过，清零等于删掉事实。不干留着的理由：看着像还在涨。带 `limited` 的期次不能和正常期次比转化率——分子冻住了，分母还在动。

脚本还挡掉几件事：抖音「1.3万」这类近似值不会覆盖区间内已有的精确值；播放量掉超 20% 会报出来而不写入，因为那多半是读错了行。

**核对有没有漏记录，看接口返回的 `total`。** 它等于后台的作品总数（含没数据的）。拉完所有页后，如果 `total` 和 `data/videos.jsonl` 里该平台的记录数对不上，差额就是没抓到的。翻页靠 `max_cursor`（传上一页返回的值），`has_more: false` 表示到底。

**播放量拿不到、但点赞评论拿得到的记录，是公开页能读的。** 抖音创作者后台对很早的作品可能不给播放量，而 `douyin.com/video/<id>` 公开页仍然显示点赞、评论、收藏、分享。这种情况把能读到的四项填上，播放量保持 0——比整条记 0 更接近事实。

## 两件值得记住的事

**日期是最容易出错的地方。** 一次批量整理逐字稿时，29 篇的文件名和头部被统一写成了同一天，真实发布日却散在两个月里。结果页面上一整批作品挤在同一天、播放量全是 0——因为文件名日期一旦写错，那一期就再也对不上真实数据了。校验能查出「两处日期不一致」，但查不出「两处日期一起写错」，那个只能靠人对。

**不要用「看起来对」来合并记录。** 曾经用相似度阈值判断两条记录是不是同一条视频，结果那批英文标题的内容互相能撞到 0.90 以上（`I am Chinese, like to teach you Chinese` 对 `Chinese Teaching : Learn To Say Hello`），会误合。现在改成只报给人看，不自动合并。

---

# data/followers.jsonl

四个平台的粉丝数，**粉丝部分唯一真源**。一行一条快照，四平台各一个数。

- 标准 JSON Lines，**按 `date` 倒序**（最新在前），与 `videos.jsonl` 同一习惯。
- **一天一条**。涨粉看的是两条快照的差；同一天重刷会替换当天那条，不会多出一条。
- 四个平台一次记齐；某个平台暂时读不到，就先不写那个键，页面显示「—」，不要写 0。

## 字段

```json
{"date":"2026-10-30","platforms":{"bilibili":{"followers":479},"douyin":{"followers":299},"xiaohongshu":{"followers":6441},"wechat_channels":{"followers":446}}}
```

| 字段 | 类型 | 说明 |
| :--- | :--- | :--- |
| `date` | string | `YYYY-MM-DD`，读数的日期。 |
| `platforms` | object | 键只能是 `bilibili`、`douyin`、`xiaohongshu`、`wechat_channels`。 |
| `platforms.<平台>.followers` | int | 该平台的粉丝总数，非负整数。 |

**只允许 `followers` 一个字段。** 多写（比如 `index`、`delta`、`gained`）会直接报错：那些要么能算出来，要么是平台自己的口径，存进来只会各自解释一套。

改完跑：

```bash
node scripts/check-followers.mjs
```

## 为什么单开一个文件

粉丝和作品指标是三处不一样：

1. **粒度不同**：作品一行一期，粉丝一行一天。
2. **能不能加不同**：`summary` 是四平台之和，粉丝**不能**加——四个平台是四个账号，同一个人可能四个都关注。
3. **更新节奏不同**：作品指标刷一次覆盖一批，粉丝一天一条快照，攒起来才有曲线。

塞进 `videos.jsonl` 的话，第一件事就会有人在页面上把粉丝加进「合计」。

## 怎么刷新

```bash
# B 站：公开接口，免登录
python3 scripts/refresh-followers.py --platform bilibili

# 另外三个：在已登录的浏览器里 observe 页面，把输出存成文件
python3 scripts/refresh-followers.py --platform douyin --in /tmp/dy-data.txt
python3 scripts/refresh-followers.py --platform xiaohongshu --in /tmp/xhs-home.txt
python3 scripts/refresh-followers.py --platform wechat_channels --in /tmp/wx-home.txt
```

各处读什么：

| 平台 | 打开哪里 | 认的标签 | 备注 |
| :--- | :--- | :--- | :--- |
| B 站 | 不用开浏览器 | `relation/stat` 接口的 `follower` | 精确整数，免登录 |
| 抖音 | 创作者中心 → 数据中心（**点侧栏进去**） | `总粉丝量` | 见下面那个坑 |
| 小红书 | `creator.xiaohongshu.com/new/home` | `粉丝数` | 精确整数 |
| 视频号 | `channels.weixin.qq.com/platform` | `关注者` | 精确整数 |

**抖音有三个坑，都实测过：**

1. **首页那个「粉丝指数 301」不是粉丝数**，是账号权重分。真正的总数在数据中心页，同一个号是 299。
2. **直接敲 `/creator-micro/data/home` 或 `/data/overview` 会显示「数据暂未产出」**，必须从首页点侧栏「数据中心」进去才渲染得出来。
3. 数据中心页有一排「粉丝净增 / 吸粉量 / 脱粉量 / 回访粉丝量」，都是为了别认错才只认「总粉丝量」这个标签。

**读不到就不写。** 认不出标签时脚本直接报错退出，不拿别的数字顶上——页面上一旦出现一个错的粉丝数，没人看得出来。

**平台只给约数时照实记。** 小红书面板上写「1.9万」就是 19000 左右的档位，别自己编尾数。`followers.jsonl` 里存的是整数，页面上按原样按万显示。

## 校验会拦什么

**错误**（阻止 `build-site.mjs`）：日期格式不对、平台名不认识、`followers` 不是非负整数、同一天两条快照、日期不是倒序、写了 `followers` 以外的字段。

**提醒**（不拦构建）：某条快照缺某个平台、最近两条快照相隔超过 14 天（粉丝数已经偏旧）。
