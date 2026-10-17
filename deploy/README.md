# 个人服务器部署

部署结构：`浏览器 → Caddy HTTPS → 127.0.0.1:8765 → 单个应用容器 → 持久化数据卷`。

适用于个人使用，所有浏览器使用同一份论文库和翻译配置。认证使用浏览器原生的 HTTP Basic 登录提示；所有页面、API、PDF、图片和导出都要求访问密码，只有不包含配置或数据的 `/healthz` 是公开探活接口。密码以带随机盐的 scrypt 哈希保存，不放入源码或前端。

## 准备

- Linux 服务器，Docker Engine 与 Docker Compose。
- 公网 HTTPS 部署需域名和 TCP 80 / 443；没有域名时可通过 SSH 隧道使用。
- 已有 Caddy 时复用它；不要启动第二个服务争用 80 / 443。
- 当前默认资源限制为 1 GB 内存、1.5 核 CPU。镜像不包含 MinerU CLI / GPU 模型，默认导入已有 ZIP，也可在网页配置 MinerU 云端 Token。

## tencentcloud：无域名访问

项目目录为 `/home/ubuntu/paper-translate`。本机双击 `连接远端纸间.command`，或运行 `python3 scripts/connect_remote.py`，建立到 `tencentcloud` 的 SSH 隧道并打开 `http://localhost:8765`。保持终端窗口打开；关闭隧道后服务器上的任务仍会继续。访问账号为 `reader`，初始密码按下方命令在自己的终端取回。

服务器只向 loopback 发布 8765，不修改现有 Caddy 站点。当前 `.env` 使用 `PAPER_TRANSLATE_PUBLIC_URL=http://localhost:8765`，并通过 `COMPOSE_FILE=compose.yaml:compose.mineru.yaml` 启用下述 MinerU 镜像。

## 服务器 MinerU（CPU Basic）

`Dockerfile.mineru` 基于应用镜像，在 `/opt/mineru` 安装独立的 MinerU 4.0.12 环境，不安装 Torch / CUDA / VLM 模型。模型与缓存保存在独立 `mineru_models` 卷，论文与设置仍在 `paper_data` 卷。

```bash
# 显式选择基础配置，再构建 MinerU 扩展镜像。
sudo docker compose -f compose.yaml build
sudo docker compose -f compose.yaml -f compose.mineru.yaml build

# 在 .env 加入 COMPOSE_FILE=compose.yaml:compose.mineru.yaml 后：
sudo docker compose run --rm --no-deps --entrypoint /opt/mineru/bin/mineru-kit app \
  models download --tier basic --small-backend onnx --source modelscope
sudo docker compose run --rm --no-deps --entrypoint /opt/mineru/bin/mineru-kit app \
  models verify --tier basic --small-backend onnx
sudo docker compose up -d
```

若默认 PyPI 下载很慢，两个构建命令均可添加 `--build-arg PYTHON_INDEX_URL=https://mirrors.cloud.tencent.com/pypi/simple`。应用依赖仍由 `uv.lock` 固定并校验哈希；MinerU 依赖的实际版本记录在镜像内 `/opt/mineru/installed-requirements.txt`。

网页设置选择“服务器 CLI”，命令填写 `/opt/mineru/bin/python /app/scripts/parse_mineru4.py`，Backend 选择 `MinerU 4 · Basic（CPU）`。适配器调用 MinerU 4 的完整文档解析 API，保存图片和中间 JSON，再生成带坐标的 V1 content list；应用仍以原 PDF 作为对照来源。无需单独打开 MinerU WebUI，上传 PDF 后即可在服务器解析。

运行时使用已经下载的本地模型（`MINERU_MODEL_SOURCE=local`）；解析不会自动上传论文到 MinerU 云端。下载阶段显式使用 ModelScope。Basic 模式不启用 LLM 辅助后处理。

约 4 GB 内存的 tencentcloud 使用单篇串行解析、单页处理窗口、2 核 CPU、2500 MB 容器内存上限和 3500 MB 内存加交换空间上限。限制适用于应用和 MinerU 子进程总和；较大的扫描页或复杂论文仍可能达到上限并解析失败。Standard / Advanced 需要更多资源，不能只在这台机器上切换选项就期待稳定运行。翻译仍通过另行配置的 OpenAI 兼容接口完成。

2026-10-17 部署验收：两页合成英文 PDF（含表格）从上传到完成约 14 秒，12 个内容块全部带坐标，容器峰值约 1.13 GiB；同内容的两页扫描版约 18 秒，16 个内容块全部带坐标，峰值约 1.43 GiB。四种格式的 ZIP 导出、PDF 读取、未登录拒绝访问、跨站来源拒绝访问及重启后的文档保留均通过。该结果用于检查流程，不代表复杂论文或大扫描件的性能。验收文档已删除，未调用付费翻译接口。

更新 MinerU 镜像时，先 `sudo docker compose -f compose.yaml build` 更新基础应用，再 `sudo docker compose build` 构建扩展镜像，然后 `sudo docker compose up -d`。不要删除模型卷；模型升级应重新下载并验证，保留旧镜像以便回退。

## 构建并启动

以下命令在服务器项目目录执行。`tencentcloud` 已有 Docker，但当前 SSH 用户使用 Docker 需要 `sudo`。

```bash
cp .env.example .env
chmod 600 .env
# 编辑 .env 中的 PAPER_TRANSLATE_PUBLIC_URL 和 PAPER_TRANSLATE_ACCESS_USER。
sudo docker compose build

# 首次创建访问密码：在服务器终端交互输入，不在命令行或聊天里填写。
sudo docker compose run --rm --no-deps --entrypoint /app/.venv/bin/python app \
  scripts/create_access_password.py /app/data/access-password.hash

sudo docker compose up -d
sudo docker compose ps
curl --fail http://127.0.0.1:8765/healthz
```

密码未创建时，应用会拒绝启动。不要使用 `docker compose up --scale app=2`，也不要增加 Uvicorn worker 数量：当前后台任务由单进程管理。

仅需私下验收时，可先设置 `PAPER_TRANSLATE_PUBLIC_URL=http://localhost:8765`，然后在自己的电脑执行：

```bash
ssh -N -L 8765:127.0.0.1:8765 tencentcloud
```

打开 `http://localhost:8765`，输入访问账号密码。这个 HTTP 地址仅限受 SSH 隧道保护的验收；公网域名配置必须使用 HTTPS。准备发布后，将 `.env` 改为最终的 `https://域名`，运行 `sudo docker compose up -d` 更新应用，再配置 Caddy。

## HTTPS 与现有 Caddy

参考 `deploy/Caddyfile.example`，把示例域名替换为实际域名，并作为独立站点加入已有 Caddy 配置。现有站点内容应保留。新配置必须先验证，再 reload：

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo systemctl reload caddy
```

示例给上传请求保留 650 MB 限制，以容纳 PDF 和结果 ZIP 的组合。域名 DNS、80 / 443 放行和证书签发正常后，浏览器访问 `https://域名`。应用端口始终仅映射到服务器 loopback，不直接开放 8765。

如果使用了 CDN / 其他反向代理，还需要同时确认它的请求大小限制和超时设置能承载论文上传。

## 登录和翻译配置

- **访问账号密码**：保护整个网页，由 `.env` 用户名及数据卷中的 `access-password.hash` 管理。
- **LLM API Key / MinerU Token**：登录后在网页设置中填写，只保存在服务器数据卷，不会回传前端或打入镜像。
- 网页的“MinerU 结果目录”是服务器文件目录，不能读取浏览器所在电脑上的 `~/MinerU`。推荐在电脑打包解析结果为 ZIP 后，通过网页上传。
- 重新打开浏览器可能仍会使用浏览器缓存的 Basic 登录凭据。共享电脑请使用独立或隐私浏览会话。

若首次部署使用了 `--random-password-file /app/data/initial-access-password.txt`，随机密码只在服务器数据卷的该文件中保存，权限为 `0600`。可以在自己的终端取回（此命令会在你的终端显示密码，不要粘贴进聊天）：

```bash
ssh tencentcloud 'cd /home/ubuntu/paper-translate && sudo docker compose exec -T app cat /app/data/initial-access-password.txt'
```

修改密码时使用交互创建命令覆盖哈希，再执行 `sudo docker compose restart app`。重启后旧凭据失效；重启前请暂停翻译并等待当前请求结束。

## 更新与备份

源码更新不会覆盖论文、图片或设置。更新方式：

```bash
sudo docker compose up -d --build
```

应用重启后，未完成任务暂停，需在界面继续翻译。更新镜像前可用 `sudo docker image tag paper-translate:local paper-translate:previous` 保存上一版本；数据目录应另行备份。

备份前暂停任务并停止应用，确保数据库和文件一致：

```bash
mkdir -p backups
chmod 700 backups
sudo docker compose stop app
sudo docker compose run --rm --no-deps --entrypoint tar app -C /app/data -czf - . > backups/paper-data.tar.gz
chmod 600 backups/paper-data.tar.gz
sudo docker compose up -d app
```

备份包含论文、译文、API Key 和访问密码哈希，应只保存在你信任的位置。不要使用 `docker compose down -v`，该参数会删除数据卷。

本机数据迁移到服务器时，应先停止本机应用、备份完整 `data/`，再恢复到服务器卷中；文档路径会自动重定位。旧设置中的本机 MinerU 路径应改为服务器路径或云端模式。恢复备份时请保留服务器已设置的访问密码文件，避免意外替换登录凭据。

## 验收

1. 未登录访问首页、`/api/settings`、原 PDF 或图片，应返回 401。
2. 登录后可以导入 ZIP、阅读 PDF、点击段落定位，以及导出完整包。
3. 前端显示“远端工作空间 / 数据保存在服务器”。
4. 重建容器后，已导入的论文和译文仍然存在。
5. 填入 LLM 服务后进行一次短句连接测试，再翻译少量段落。

官方参考：[Caddy 反向代理](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)、[uv Docker 集成](https://docs.astral.sh/uv/guides/integration/docker/)、[FastAPI HTTP Basic](https://fastapi.tiangolo.com/advanced/security/http-basic-auth/)。
