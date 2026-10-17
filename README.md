# 纸间 · Paper Translate

一个本地运行的双语论文阅读工具：MinerU 负责解析 PDF，LLM 仅负责翻译，程序保存原文、译文和 PDF 坐标之间的对应关系。

## 启动

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/) 和 Node.js 20+。

```bash
cd /Users/polaris/CS/paper-translate
bash scripts/start.sh
```

启动后自动在浏览器打开 **http://127.0.0.1:8765**。macOS 也可双击 `启动纸间.command`，终端窗口中按 Ctrl+C 停止。首次启动需要联网安装依赖。前端依赖和字体均打包在本地，之后阅读已导入论文无需访问外部服务。设置 `PAPER_TRANSLATE_NO_BROWSER=1` 可禁用自动打开浏览器。

## 使用

1. 点击 **导入论文 → MinerU 论文库**。默认扫描 `~/MinerU`，可在设置中修改目录。选择一篇已有解析结果，应用会复制原 PDF、JSON 和图片，不改动 MinerU 原文件。
2. 在 **应用设置 → 翻译服务** 中填写 OpenAI 兼容的 API Base URL、模型名和 API Key。Base URL 包含服务商所需的版本路径（如 `/v1`），不包含 `/chat/completions`。默认地址与模型名仅作为 DeepSeek 配置示例，不附带 Key。也可连接支持该协议的本地服务。
3. 可先 **保存并测试连接**，会发送一句英文测试请求。测试与翻译均按服务商规则产生调用费用。
4. 打开论文，点击 **开始翻译**。结果按批立即保存。可暂停、继续；应用重启后不会自动重新发送请求。
5. 在 **逐段对照 / 纯中文 / 逐节对照 / 英文原文** 中切换。显示格式的切换不会调用 LLM。
6. 点击译文段落可定位并高亮原 PDF；点击 PDF 内容框可定位译文。可选开启按段落的滚动联动。PDF 下方可翻页、缩放。
7. 段落下方提供 **定位、编辑、重译**。人工修改带版本保护，不会被正在执行的旧批次覆盖。
8. 点击 **导出 → Markdown 完整包**，得到 `paper.md`、`paper.json` 和 `assets/` 图片。单独的 Markdown 需要搭配图片目录。

未翻译内容明确标记为“待翻译”；纯中文模式会暂时显示原文作为阅读回退。参考文献、代码和独立公式默认保留原文。图像保持不变，图注参与翻译；有结构化 HTML 的表格翻译文字并保留标签，只有表格图片时展示原图。图像内部的英文不做 OCR 翻译。

## 现有 MinerU 与新 PDF

已在本机检测到 `/Applications/MinerU.app` 桌面版 0.13.1 和 `~/MinerU` 解析结果。桌面应用不等于命令行解析器，因此默认使用 **已有 MinerU 结果** 模式。

- **已有结果目录**：需要 `*_content_list.json`（V1）或 `*content_list_v2.json`（V2）、原 PDF，以及引用到的 `images/`。优先使用 V1，以读取明确的 `page_idx`。V1/V2 的 bbox 从 0–1000 转换为应用统一的 0–1 坐标。
- **PDF + 结果 ZIP**：在导入窗口选择 ZIP；原 PDF 可放在 ZIP 里，或与 ZIP 一起上传。支持 ZIP 中的一层或多层目录。
- **本地 CLI**：在设置中启用并填写 `mineru` 可执行文件路径。适配支持 `-p / -o / -b` 的 MinerU 2.x CLI。程序用参数数组启动进程，不执行 shell。模型文件和 CLI 需要自行安装；本项目不会改变桌面版安装。
- **MinerU 云端 API**：在设置中启用并填写 Token。导入新 PDF 时，文件会上传到 MinerU 官方 API，程序获取结果后在本地保存。已提交云端的任务可能在本地暂停后继续运行。

不同版本 MinerU 的输出契约可能变化；当前适配器支持已验证的 V1 / V2 内容列表，不假定所有 JSON 都具有相同结构。需要新格式时修改 `server/mineru.py`，无需改动阅读器或翻译协议。

## 数据与翻译协议

```text
PDF → MinerU → 统一段落模型 → 按章节和段落分批翻译 → GUI / Markdown
```

每个块保存稳定 ID、类型、原文、译文、章节 ID、`source_locations[]`、翻译状态和编辑版本。`source_locations` 是数组，可承载跨页或跨栏的多个来源矩形；当前导入器忠实保留 MinerU 内容块边界，不自动猜测跨页段落合并。定位精度以解析器提供的段落框为准，不提供逐词对齐。

LLM 请求只包含段落 ID 与文字，以及论文标题、章节上下文和术语表；坐标、PDF 文件和图片不发送给 LLM。公式、代码片段、URL、数字引用和 HTML 标签先替换为受保护占位符。返回结果必须满足完整且唯一的段落 ID、非空译文、正确的占位符数量后才会保存；失败重试最多 3 次，不覆盖已保存结果。这些校验保证结构完整，不能保证翻译语义正确。

实际论文、图片、SQLite 数据库和设置保存在 `data/`，已被 `.gitignore` 排除。API Key / MinerU Token 保存在权限为 `0600` 的本机设置文件中（不是加密保险库），不会回传给前端或放入导出包。也可以使用环境变量 `PAPER_TRANSLATE_API_KEY` 为未保存 Key 的环境提供凭据。`PAPER_TRANSLATE_DATA` 可指定其他数据目录。

服务默认仅监听 `127.0.0.1`，并限制 API 的 Host 和跨站 Origin。它面向个人本机使用，不是经过身份验证的多用户公网服务。

## 开发与测试

后端开发：

```bash
uv sync --frozen
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8765 --reload
```

前端开发（另一个终端）：

```bash
cd frontend
npm ci
npm run dev
```

打开 http://127.0.0.1:5173，Vite 将 `/api` 转发到后端。

验证：

```bash
.venv/bin/python -m unittest discover -s tests -v
cd frontend
npm run build
```

测试使用临时 PDF / JSON 和模拟的 LLM 返回，不调用付费服务。覆盖 V1/V2 几何映射、ZIP 安全、三种导出方式、秘密字段过滤、段落 ID / 占位符校验、断点续传，以及翻译过程中人工修改的版本保护。

## 目录

```text
server/
  app.py          HTTP API、导入、设置、文件访问
  mineru.py       MinerU 适配、本地 CLI / 云端解析
  translation.py  翻译请求、受保护内容、响应校验
  jobs.py         后台任务、暂停续传、版本保护
  store.py        SQLite 文档存储与本机设置
  exporter.py     Markdown、JSON 与图片打包
frontend/src/
  App.tsx         论文库、导入和设置
  Reader.tsx      对照阅读、编辑和导出
  PdfViewer.tsx   PDF.js 渲染与坐标高亮
tests/            可离线运行的核心测试
```
