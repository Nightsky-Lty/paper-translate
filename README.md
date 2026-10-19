# 纸间 · Paper Translate

纸间是一个可在本机或服务器运行的双语论文阅读与翻译工具。它使用 MinerU 解析 PDF，使用 OpenAI 兼容的 LLM 接口翻译文字，并保留段落与原 PDF 的位置关系，方便边读译文边核对原文。

```text
PDF → MinerU 解析 → 段落、图片与坐标 → LLM 翻译 → 对照阅读 / Markdown 导出
```

## 功能

- **四种阅读模式**：逐段中英对照、逐节中英对照、纯中文、英文原文；切换模式无需再次调用 LLM。
- **原 PDF 对照**：点击段落定位并高亮 PDF，点击 PDF 内容框定位对应段落，支持可选的滚动联动。
- **专注阅读**：PDF 与译文左右等宽铺满阅读区，默认收起导航与工具栏；点击“显示工具栏”或按 Esc 恢复操作，目录按需展开。
- **两种自动解析方式**：MinerU 4 Python API 和 MinerU 官方云端 API；也可直接导入已有解析结果。
- **可配置翻译服务**：支持 OpenAI 兼容的接口地址、模型、API Key 和术语表。
- **编辑与续传**：逐批保存译文，支持暂停、继续、单段重译和人工编辑；进行中的翻译不会覆盖较新的人工修改。
- **便携导出**：导出 Markdown、JSON，或包含图片的完整 ZIP 包。
- **服务器部署**：提供 Docker 配置和 SSH 隧道访问，打开网页即可使用，无需网页登录。

## 快速开始

### 环境要求

本地启动脚本使用 Bash，需要：

- Python 3.11 或更高版本。
- [uv](https://docs.astral.sh/uv/)。
- Node.js 20 或更高版本及 npm。

MinerU 和翻译服务需按所选方式单独准备。仅导入已有解析结果时，无需安装 MinerU Python 环境；使用外部服务时，需要自行提供相应凭据。

### 下载并启动

```bash
git clone https://github.com/Nightsky-Lty/paper-translate.git
cd paper-translate
bash scripts/start.sh
```

脚本会创建 Python 环境、安装依赖并构建前端，随后自动打开 **http://127.0.0.1:8765**。首次启动需要联网。保持终端窗口打开，按 Ctrl+C 停止应用。

如需禁止自动打开浏览器：

```bash
PAPER_TRANSLATE_NO_BROWSER=1 bash scripts/start.sh
```

希望在远端运行时，请阅读 [服务器部署指南](deploy/README.md)，其中包含基础 Docker 部署和可选的 MinerU CPU 环境。

## 使用流程

### 1. 选择 PDF 解析方式

在应用设置中选择解析方式，再导入论文：

| 方式 | 需要准备 | 导入方法 |
| --- | --- | --- |
| MinerU Python API | 安装 MinerU 4 的 Python 环境和所需模型 | 上传 PDF，在应用运行的机器上自动解析 |
| MinerU 云端 API | MinerU API Token | 上传 PDF，提交云端解析并获取结果 |

默认使用 Python API，在解析设置中填写已安装 MinerU 4 的 Python 解释器路径；使用云端解析时选择云端 API 并填写 Token。Python 模式使用本地模型，不需要 MinerU 官方云端 Token。

已有结果仍可独立导入，无需调用解析 API。“MinerU 论文库”默认扫描 `~/MinerU`，可在设置中修改。结果需要包含 `*_content_list.json`（V1）或 `*content_list_v2.json`（V2）、原 PDF，以及引用的 `images/`。ZIP 支持嵌套目录；原 PDF 可放在包内，也可单独配对上传。应用不会控制桌面端开始解析。

Python 解释器路径示例（按安装位置替换）：

```text
/path/to/mineru-env/bin/python
```

选择与模型和硬件匹配的 Basic / Standard / Advanced / Flash。应用在独立进程中调用 MinerU 4 Python API，保存图片和中间 JSON，再生成项目使用的 V1 content list。解析任务按单篇串行执行，排队时也可暂停。Docker CPU Basic 环境的安装步骤见部署指南。

### 2. 配置翻译服务

打开“应用设置 → 翻译服务”，填写：

- **API Base URL**：包含服务商要求的版本路径，如 `/v1`，不包含 `/chat/completions`。
- **模型名**：填写所选服务支持的模型标识。
- **API Key**：填写服务凭据；也可连接支持同一协议的本地服务。
- **术语表**：可选，用于约定专业词汇的译法。

默认接口地址与模型名是配置示例，不附带 API Key。点击“保存并测试连接”会发送一句测试请求，测试与后续翻译按服务商规则计费。

### 3. 翻译与阅读

导入论文后点击“开始翻译”。结果逐批保存，可暂停并继续未完成部分；应用重启后任务会暂停，不会自动重新发送翻译请求。

在阅读器中切换显示模式，点击段落或 PDF 内容框相互定位。段落提供“定位、编辑、重译”操作。未翻译内容标记为“待翻译”，纯中文模式下会暂时显示原文作为回退。

首次打开论文时默认进入专注阅读，左侧显示 PDF，右侧显示中文。点击顶部“显示工具栏”或按 Esc，可以切换阅读格式、打开目录、启动翻译或导出；点击“专注阅读”再次收起工具栏。应用会记住阅读格式和专注模式的选择。

### 4. 导出

通过导出菜单选择阅读格式及文件类型：

- **Markdown**：适合在 Markdown 编辑器中阅读；图片需搭配资源目录使用。
- **JSON**：保存段落、译文与位置等结构化数据。
- **Markdown 完整包**：包含 `paper.md`、`paper.json` 和 `assets/` 图片，便于归档或迁移。

## 使用限制

- 定位精度取决于 MinerU 提供的内容块坐标，当前提供段落级对照，不提供逐词对齐，也不自动合并推测的跨页段落。
- 参考文献、代码和独立公式默认保留原文。图注可以翻译，图像内部文字不做 OCR 翻译或重绘。
- 有结构化 HTML 的表格会翻译文字并保留标签；只有图片的表格展示原图。
- 翻译前会保护公式、代码片段、URL、数字引用和 HTML 标签，并校验返回的段落 ID 与占位符。这些校验保证结构完整，不能保证译文语义正确。
- 服务器版使用同一份论文库和翻译配置，暂不提供多用户账号和数据隔离。
- MinerU 不同版本的输出格式可能变化，当前适配 V1 / V2 content list；其他 JSON 不能直接假定兼容。

## 数据与隐私

本机运行时，论文、图片、译文、数据库和设置默认保存在项目的 `data/` 中；服务器 Docker 部署使用持久化数据卷。数据目录和凭据文件已加入 Git 忽略规则。

LLM 请求包含待翻译文字、段落 ID、论文标题、章节上下文和术语表，不发送 PDF 文件、图片和坐标。选择 MinerU 云端 API 时，原 PDF 会上传到 MinerU；Python API 模式使用所配置的本地运行环境。

API Key / MinerU Token 保存在权限为 `0600` 的设置文件中，未做应用层加密，不回传前端，也不放入导出包。可使用 `PAPER_TRANSLATE_API_KEY` 环境变量提供未在设置中保存的翻译凭据。

| 环境变量 | 用途 |
| --- | --- |
| `PAPER_TRANSLATE_DATA` | 修改应用数据目录 |
| `PAPER_TRANSLATE_LIBRARY` | 修改默认的 MinerU 结果目录 |
| `PAPER_TRANSLATE_API_KEY` | 为翻译服务提供 API Key |
| `PAPER_TRANSLATE_MINERU_PYTHON` | 配置默认的 MinerU Python 解释器 |
| `PAPER_TRANSLATE_NO_BROWSER` | 禁止启动脚本自动打开浏览器 |

本机启动和 Docker 端口发布默认仅绑定 `127.0.0.1`，并限制 Host 和跨站 Origin。服务器通过 SSH 隧道访问，身份验证由 SSH 完成，网页不要求账号密码。项目当前仅面向本机和 SSH 私有访问，不提供公网部署方案，配置方法见部署指南。

## 开发与构建

后端开发（在项目根目录）：

```bash
uv sync --frozen
.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8765 --reload
```

前端开发（另开终端，在项目根目录）：

```bash
cd frontend
npm ci
npm run dev
```

打开 **http://127.0.0.1:5173**，Vite 会将 `/api` 请求转发到后端。

构建前端（在项目根目录）：

```bash
npm --prefix frontend run build
```

## 项目结构

```text
server/          FastAPI 后端、MinerU 适配、翻译任务和数据存储
frontend/src/    React 阅读器、PDF 定位、设置与论文库界面
scripts/         本机启动、MinerU 4 适配和 SSH 连接
deploy/          服务器部署指南
```
