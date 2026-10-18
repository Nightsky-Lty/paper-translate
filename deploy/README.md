# 服务器部署

本指南说明如何将纸间部署到自己的 Linux 服务器，并通过 HTTPS 或 SSH 隧道访问。基础镜像提供论文阅读、翻译和结果导入；需要服务器自动解析 PDF 时，可额外构建 MinerU CPU 镜像。

```text
浏览器 → HTTPS 反向代理或 SSH 隧道 → 127.0.0.1:8765 → 应用容器 → 持久化数据卷
```

服务器版使用单一工作空间，所有访问者共享论文库和翻译配置。所有页面、API、PDF、图片和导出均要求访问账号密码；只有不含配置或数据的 `/healthz` 可用于无认证探活。

## 1. 准备环境

需要 Linux、Docker Engine 和 Docker Compose，以及用于翻译的 OpenAI 兼容服务。公网域名访问还需要域名解析、可访问的 TCP 80 / 443 和 HTTPS 反向代理；没有域名时可使用 SSH 隧道。

在服务器获取源码：

```bash
git clone https://github.com/Nightsky-Lty/paper-translate.git
cd paper-translate
cp .env.example .env
chmod 600 .env
```

编辑 `.env`：

- HTTPS 访问：将 `PAPER_TRANSLATE_PUBLIC_URL` 设置为实际地址，如 `https://papers.example.com`。
- SSH 隧道访问：设置为 `http://localhost:8765`。
- `PAPER_TRANSLATE_ACCESS_USER` 为网页登录账号，可自行修改。

访问地址应为站点根地址，不含子路径。以下示例使用 `sudo docker`；若当前用户已有 Docker 权限，可省略 `sudo`。

## 2. 构建应用镜像

```bash
sudo docker compose -f compose.yaml build
```

基础镜像默认限制为 1 GB 内存、1.5 核 CPU，不包含 MinerU Python 库或模型。它可以导入已有结果 ZIP，也可以在网页设置中配置 MinerU 云端解析。

若需要服务器本地解析，继续下面的可选步骤；否则跳到“创建访问密码并启动”。

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

## 3. 创建访问密码并启动

首次启动前，在服务器终端交互输入访问密码：

```bash
sudo docker compose run --rm --no-deps --entrypoint /app/.venv/bin/python app \
  scripts/create_access_password.py /app/data/access-password.hash

sudo docker compose up -d
sudo docker compose ps
curl --fail http://127.0.0.1:8765/healthz
```

密码以带随机盐的 scrypt 哈希保存在数据卷中，未创建哈希时应用会拒绝启动。不要把密码写进源码或命令行参数。

应用端口仅映射到服务器的 `127.0.0.1:8765`。保持单个应用容器和一个 Uvicorn worker，不使用 `--scale app=2`；当前后台任务由单进程管理。

## 4. 配置访问方式

### SSH 隧道

先在本机完成 SSH 配置，并通过 `ssh your-server` 确认服务器身份。将 `your-server` 替换为自己的 SSH 别名或 `用户名@服务器地址`。

在本机执行：

```bash
ssh -N -L 127.0.0.1:8765:127.0.0.1:8765 your-server
```

打开 **http://localhost:8765**，使用 `.env` 中的账号和刚创建的密码登录。该 HTTP 地址仅用于受 SSH 隧道保护的连接，不直接对公网开放。

也可在本机克隆的项目根目录运行以下辅助脚本，自动建立隧道并打开浏览器：

```bash
python3 scripts/connect_remote.py --host your-server
```

保持连接终端打开，按 Ctrl+C 关闭隧道。断开连接不会停止服务器上已经提交的任务。本机 8765 端口需要空闲。

### HTTPS 域名

将 `.env` 中的 `PAPER_TRANSLATE_PUBLIC_URL` 设置为实际 HTTPS 域名，并运行 `sudo docker compose up -d` 应用配置。

参考 [Caddyfile.example](Caddyfile.example) 配置反向代理。如果服务器已有 Caddy，在现有配置中加入独立站点，保留其他站点；不要启动第二个服务争用 80 / 443。修改后先验证，再 reload：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

示例为上传保留了 650 MB 请求体限制。DNS、端口放行和证书签发完成后，访问配置的 HTTPS 地址。使用 CDN 或其他代理时，也需确认请求大小限制和超时设置可承载论文上传。

## 5. 配置解析与翻译

登录后进入应用设置：

- **翻译服务**：填写 OpenAI 兼容的 Base URL、模型和 API Key，再进行短句连接测试。
- **已有结果**：通过网页上传结果 ZIP；网页中的 MinerU 结果目录指服务器文件目录，不能读取浏览器所在电脑的文件夹。
- **MinerU 云端**：选择云端解析并填写 Token，PDF 会上传到 MinerU。
- **MinerU CPU 镜像**：选择“MinerU Python API”，Python 解释器使用 `/opt/mineru/bin/python`，解析档位选择 `MinerU 4 · Basic（CPU）`。扩展镜像已配置该解释器的默认值。

访问密码保护整个网页，LLM API Key / MinerU Token 则用于外部服务，两者互相独立。服务凭据保存在服务器数据卷的设置文件中，不回传前端或打入镜像。

## 密码管理

修改密码时，重新运行上面的交互式创建命令覆盖哈希，再执行：

```bash
sudo docker compose restart app
```

重启前请暂停任务并等待当前请求结束。重启后旧密码失效；浏览器可能缓存 Basic 登录凭据，可使用独立浏览器会话重新登录。

自动化部署可使用密码脚本的 `--random-password-file /app/data/initial-access-password.txt` 参数生成随机密码，文件权限为 `0600`，脚本不会将密码打印到日志。仅在使用此方式创建密码时，才会存在该文件，可在服务器项目目录通过以下命令查看：

```bash
sudo docker compose exec -T app cat /app/data/initial-access-password.txt
```

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

备份包含论文、译文、服务凭据和密码哈希，应保存在可信位置。备份前暂停任务并停止应用，确保数据库与文件一致：

```bash
mkdir -p backups
chmod 700 backups
sudo docker compose stop app
sudo docker compose run --rm --no-deps --entrypoint tar app -C /app/data -czf - . > backups/paper-data.tar.gz
chmod 600 backups/paper-data.tar.gz
sudo docker compose up -d app
```

不要使用 `docker compose down -v`，该参数会删除数据卷。使用本地 MinerU 时，模型卷可另行备份，或在恢复后重新下载模型。

从本机迁移到服务器时，先停止本机应用并备份完整 `data/`，再恢复到服务器数据卷。文档路径会自动重定位；设置中的 Python 解释器和结果目录需要按服务器环境调整。恢复时保留服务器已有的访问密码文件，避免替换登录凭据。

早期版本保存的 MinerU 4 命令配置会自动读取为 Python 解释器路径及解析档位；重新保存设置后，旧字段会被移除。其他旧解析模式默认迁移为 Python API，需准备 MinerU 4 环境。

## 部署检查

1. 未登录访问首页、设置、原 PDF 或图片，返回 401。
2. 登录后可以导入论文、阅读 PDF、定位段落，以及导出完整包。
3. 网页显示远端工作空间，数据保存在服务器。
4. 重建容器后，论文和译文仍然存在。
5. 使用本地 MinerU 时，先解析少量页面，确认模型、坐标和资源占用符合预期。
6. 填写翻译服务后进行连接测试，再翻译少量段落；外部调用按服务商规则计费。

参考：[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)、[uv Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/)、[FastAPI HTTP Basic](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/)。
