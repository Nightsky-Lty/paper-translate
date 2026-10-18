# 服务器部署

本指南说明如何将纸间部署到自己的 Linux 服务器，并通过 SSH 隧道访问。基础镜像提供论文阅读、翻译和结果导入；需要服务器自动解析 PDF 时，可额外构建 MinerU CPU 镜像。

```text
浏览器 → SSH 加密隧道 → 127.0.0.1:8765 → 应用容器 → 持久化数据卷
```

服务器版使用单一工作空间，通过 SSH 完成身份验证，网页无需登录。应用端口仅发布到服务器 loopback，并限制 Host 和跨站 Origin；当前仅提供私有访问方案。

## 1. 准备环境

需要可通过 SSH 连接的 Linux 服务器、Docker Engine 和 Docker Compose，以及用于翻译的 OpenAI 兼容服务。无需配置域名或反向代理。

在服务器获取源码：

```bash
git clone https://github.com/Nightsky-Lty/paper-translate.git
cd paper-translate
cp .env.example .env
chmod 600 .env
```

基础镜像无需额外的 `.env` 配置；启用 MinerU 扩展镜像时按下方说明设置 `COMPOSE_FILE`。以下示例使用 `sudo docker`，当前用户已有 Docker 权限时可省略 `sudo`。

## 2. 构建应用镜像

```bash
sudo docker compose -f compose.yaml build
```

基础镜像默认限制为 1 GB 内存、1.5 核 CPU，不包含 MinerU Python 库或模型。它可以导入已有结果 ZIP，也可以在网页设置中配置 MinerU 云端解析。

若需要服务器本地解析，继续下面的可选步骤；否则跳到“启动应用”。

### 可选：安装 MinerU CPU Basic

扩展镜像在 `/opt/mineru` 安装独立的 MinerU 4.0.12 环境，不安装 Torch / CUDA / VLM 模型。应用数据保存在 `paper_data` 卷，MinerU 模型与缓存保存在独立的 `mineru_models` 卷。

```bash
sudo docker compose -f compose.yaml -f compose.mineru.yaml build
```

在 `.env` 中加入以下配置，使后续 Compose 命令使用扩展镜像：

```dotenv
COMPOSE_FILE=compose.yaml:compose.mineru.yaml
```

下载并验证模型：

```bash
sudo docker compose run --rm --no-deps --entrypoint /opt/mineru/bin/mineru-kit app \
  models download --tier basic --small-backend onnx --source modelscope
sudo docker compose run --rm --no-deps --entrypoint /opt/mineru/bin/mineru-kit app \
  models verify --tier basic --small-backend onnx
```

下载阶段使用 ModelScope；解析运行时设置为 `MINERU_MODEL_SOURCE=local`，使用已经下载的模型，不自动上传 PDF 到 MinerU 云端。Basic 模式不启用 LLM 辅助后处理。

扩展配置默认使用单篇串行解析、单页处理窗口、2 核 CPU、2500 MB 容器内存上限和 3500 MB 内存加交换空间上限。这些限制涵盖应用与解析子进程总和，应按服务器资源调整。复杂论文或较大扫描页仍可能达到内存上限。Standard / Advanced 需要额外的模型与运行资源，切换前需另行准备。

若默认 PyPI 下载较慢，两个构建命令均可添加 `--build-arg PYTHON_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple`。应用依赖由 `uv.lock` 固定并校验哈希；MinerU 依赖的实际版本记录在镜像内 `/opt/mineru/installed-requirements.txt`。

## 3. 启动应用

```bash
sudo docker compose up -d
sudo docker compose ps
curl --fail http://127.0.0.1:8765/healthz
```

无需创建网页登录账号或密码。

应用端口仅映射到服务器的 `127.0.0.1:8765`。保持单个应用容器和一个 Uvicorn worker，不使用 `--scale app=2`；当前后台任务由单进程管理。

## 4. 建立 SSH 隧道

先在本机完成 SSH 配置，并通过 `ssh your-server` 确认服务器身份。将 `your-server` 替换为自己的 SSH 别名或 `用户名@服务器地址`。

在本机执行：

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 your-server
```

打开 **http://localhost:8765** 即可使用，不会出现网页登录提示。网页流量由 SSH 隧道加密传输，服务器的应用端口仍只绑定 `127.0.0.1`。

也可在本机克隆的项目根目录运行以下辅助脚本，自动建立隧道并打开浏览器：

```bash
python3 scripts/connect_remote.py --host your-server
```

保持连接终端打开，按 Ctrl+C 关闭隧道。断开连接不会停止服务器上已经提交的任务。本机 8765 端口需要空闲。

## 5. 配置解析与翻译

打开网页后进入应用设置：

- **翻译服务**：填写 OpenAI 兼容的 Base URL、模型和 API Key，再进行短句连接测试。
- **已有结果**：通过网页上传结果 ZIP；网页中的 MinerU 结果目录指服务器文件目录，不能读取浏览器所在电脑的文件夹。
- **MinerU 云端**：选择云端解析并填写 Token，PDF 会上传到 MinerU。
- **MinerU CPU 镜像**：选择“MinerU Python API”，Python 解释器使用 `/opt/mineru/bin/python`，解析档位选择 `MinerU 4 · Basic（CPU）`。扩展镜像已配置该解释器的默认值。

LLM API Key / MinerU Token 用于调用外部服务，仍需在应用设置中填写。服务凭据保存在服务器数据卷的设置文件中，不回传前端或打入镜像。

## 更新

更新源码后重建并启动基础镜像：

```bash
git pull --ff-only
sudo docker compose -f compose.yaml build
```

若启用了 MinerU 扩展配置，还需重建扩展镜像：

```bash
sudo docker compose build
```

最后执行 `sudo docker compose up -d`。更新镜像不会覆盖持久化数据；重启后未完成任务会暂停，需在界面手动继续。模型升级后应重新下载并验证，保留旧镜像与数据备份以便回退。

## 备份与迁移

备份包含论文、译文、服务凭据，应保存在可信位置。备份前暂停任务并停止应用，确保数据库与文件一致：

```bash
mkdir -p backups
chmod 700 backups
sudo docker compose stop app
sudo docker compose run --rm --no-deps --entrypoint tar app -C /app/data -czf - . > backups/paper-data.tar.gz
chmod 600 backups/paper-data.tar.gz
sudo docker compose up -d app
```

不要使用 `docker compose down -v`，该参数会删除数据卷。使用本地 MinerU 时，模型卷可另行备份，或在恢复后重新下载模型。

从本机迁移到服务器时，先停止本机应用并备份完整 `data/`，再恢复到服务器数据卷。文档路径会自动重定位；设置中的 Python 解释器和结果目录需要按服务器环境调整。

早期版本保存的 MinerU 4 命令配置会自动读取为 Python 解释器路径及解析档位；重新保存设置后，旧字段会被移除。其他旧解析模式默认迁移为 Python API，需准备 MinerU 4 环境。

## 部署检查

1. 建立 SSH 隧道后，首页与设置可直接打开，不要求网页账号密码。
2. 可以导入论文、阅读 PDF、定位段落，以及导出完整包。
3. 网页显示远端工作空间，数据保存在服务器。
4. 重建容器后，论文和译文仍然存在。
5. 使用本地 MinerU 时，先解析少量页面，确认模型、坐标和资源占用符合预期。
6. 填写翻译服务后进行连接测试，再翻译少量段落；外部调用按服务商规则计费。

升级旧版本时，可从 `.env` 中移除 `PAPER_TRANSLATE_PUBLIC_URL`、`PAPER_TRANSLATE_ACCESS_USER` 和 `PAPER_TRANSLATE_PASSWORD_HASH_FILE`；新版本不再读取这些配置，也不使用旧的网页登录密码文件。

参考：[uv Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/)。
