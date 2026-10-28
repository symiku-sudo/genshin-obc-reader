# 观测观测枢

原神中文文本的本地浏览与搜索网页。使用 Python 标准库和 SQLite，不需要账号或 npm 运行依赖。

首页提供自由浏览、全文搜索和“全部／未读／已读”筛选。可在列表或正文页手动标记词条已读；标记保存在 SQLite。收藏、阅读位置和字号保存在当前浏览器。管理区收纳目录导入、更新、在线查找及阅读记录备份。备份文件包含已读标记、收藏、位置和字号，不含正文；恢复会合并阅读标记与收藏，并保留当前已有的位置和字号。

当前已接入书籍、武器、圣遗物、地图文本、角色、食物、背包 7 个观测枢公开目录。实际覆盖取决于原站公开正文及当前提取规则；目录不代表游戏内全部文本。保存中文故事、设定、书籍、交互对白、物品描述及角色中文语音文案。属性、成长与突破材料表、配装攻略、图片、视频、音频和玩法数值不进入正文。对白结构异常或未知模块会标为待核对，避免猜测拼接。

## 在 Termux 中运行

```sh
cd obc-reader
sh control.sh start
```

在同一台设备的浏览器打开 <http://127.0.0.1:8766/>。该地址只供本机访问。使用 `sh control.sh status` 检查服务，`sh control.sh stop` 停止。Android 结束 Termux 后需重新启动服务；导入任务会保存进度并可继续。

前台运行方式：

```sh
sh start.sh
```

## 测试

```sh
python -m unittest -q
node --check static/app.js
node --check static/library.js
node --check static/backup.js
```

可选 DOM 交互检查（需要 Node.js 和联网安装测试依赖）：

```sh
npm install --prefix .qa --no-save --no-package-lock jsdom@26.1.0
node test_ui.cjs
```

## 缓存和隐私

所有下载的正文、搜索索引、阅读标记和数据库备份保存在 `data/`；该目录被 Git 忽略。不要提交个人的 SQLite 数据库或阅读记录备份。样本响应和目录清单位于 `research/`，用于测试与离线解析；它们包含观测枢文本，当前 GitHub 仓库设为私有。

`python audit_imports.py` 和 `python audit_map_cache.py` 可从本地缓存生成覆盖报告；`python recheck_saved_reviews.py JOB_ID [...]` 只用数据库已保存的原始响应重查待适配项，不联网。

## 独立安卓 App（开发中）

安卓版本复用同一套页面、提取器与搜索接口，Python 通过 Chaquopy 运行在 App
进程内。没有监听端口，不依赖 Termux 或网页服务。内置当前完整中文文本库，
首次启动在 App 私有目录解压；升级不会覆盖已有数据库。已读记录保存在 SQLite，
收藏、位置和字号保存在 App 的 WebView 存储。网页已有的阅读记录可以通过管理区
导出 JSON，再在 App 中选择文件合并恢复。

构建需要 JDK 17、Python 3.13、Gradle 8.11.1、Android SDK 35。GitHub Actions
工作流下载私有 Release 中的文本包，并运行后端测试及模拟器断网验收。
签名密钥保存在 Actions Secrets，本地副本位于忽略目录 `data/android/signing/`；构建日志与 Git 不包含密钥。后续版本必须沿用
同一签名密钥及 applicationId，才能保留数据覆盖安装。

本地准备资产与构建调试包：

```sh
# 从当前网页数据库生成全量文本快照；不会修改原数据库
python tools/prepare_android_assets.py --snapshot
cd android
gradle :app:assembleDebug
```

已有文本包时使用 `python tools/prepare_android_assets.py`。
发布构建使用 `OBC_SIGNING_FILE` 指向 PKCS12 文件，`OBC_SIGNING_PASSWORD`
通过环境变量提供，别名为 `reader`。不配置签名时只能直接安装调试构建。

验收范围和待验证事项见 [Android 验收清单](docs/android-parity.md)。
