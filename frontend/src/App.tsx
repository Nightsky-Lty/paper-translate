import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  ArrowDownToLine,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  Clock3,
  FileText,
  FolderOpen,
  Globe2,
  HardDrive,
  Languages,
  Library,
  LoaderCircle,
  Plus,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
  Upload,
  X,
  AlertCircle,
  KeyRound,
  Plug,
  SlidersHorizontal,
} from "lucide-react";
const Reader = lazy(() => import("./Reader"));
import { useDialog } from "./useDialog";
import { useRuntime } from "./Runtime";
import {
  active,
  api,
  type LibraryEntry,
  type Paper,
  type Settings,
} from "./types";

function Mark({ small = false }: { small?: boolean }) {
  return (
    <div className={`brand ${small ? "compact" : ""}`}>
      <div className="brand-icon">
        <span />
        <span />
      </div>
      {!small && (
        <div>
          <strong>纸间</strong>
          <span>PAPER TRANSLATE</span>
        </div>
      )}
    </div>
  );
}

function SettingsDialog({
  onClose,
  notify,
}: {
  onClose: () => void;
  notify: (s: string, error?: boolean) => void;
}) {
  const { storageLabel, isServer } = useRuntime();
  const [values, setValues] = useState<Settings | null>(null);
  const [tab, setTab] = useState("llm");
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [key, setKey] = useState("");
  const [token, setToken] = useState("");
  const [clearKey, setClearKey] = useState(false);
  const [clearToken, setClearToken] = useState(false);
  useDialog(true, () => {
    if (!busy && !testing) onClose();
  });
  useEffect(() => {
    api<Settings>("/settings")
      .then(setValues)
      .catch((e) => notify(e.message, true));
  }, [notify]);
  const set = <K extends keyof Settings>(name: K, value: Settings[K]) =>
    setValues((s) => (s ? { ...s, [name]: value } : s));
  const save = async (close = true) => {
    if (!values) return false;
    setBusy(true);
    try {
      const body = {
        ...values,
        ...(key || clearKey ? { api_key: key } : {}),
        ...(token || clearToken ? { mineru_token: token } : {}),
      };
      const saved = await api<Settings>("/settings", {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setValues(saved);
      setKey("");
      setToken("");
      setClearKey(false);
      setClearToken(false);
      if (close) {
        notify("设置已保存");
        onClose();
      }
      return true;
    } catch (e) {
      notify((e as Error).message, true);
      return false;
    } finally {
      setBusy(false);
    }
  };
  const test = async () => {
    setTesting(true);
    try {
      if (await save(false)) {
        const r = await api<{ translation: string }>("/settings/test", {
          method: "POST",
        });
        notify(`连接成功：${r.translation}`);
      }
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setTesting(false);
    }
  };
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal settings-modal"
        role="dialog"
        aria-modal="true"
        aria-label="应用设置"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">MAKE IT YOURS</span>
            <h2>你的阅读工作流。</h2>
          </div>
          <button
            className="icon-button"
            onClick={onClose}
            aria-label="关闭设置"
          >
            <X size={20} />
          </button>
        </div>
        <div className="modal-tabs">
          {[
            { id: "llm", label: "翻译服务", icon: Plug },
            { id: "parser", label: "论文解析", icon: FileText },
            { id: "glossary", label: "术语与翻译", icon: Languages },
          ].map((t) => (
            <button
              key={t.id}
              className={tab === t.id ? "selected" : ""}
              onClick={() => setTab(t.id)}
            >
              <t.icon size={15} />
              {t.label}
            </button>
          ))}
        </div>
        {!values ? (
          <div className="loading-center">
            <LoaderCircle className="spin" />
          </div>
        ) : (
          <div className="settings-body">
            {tab === "llm" && (
              <>
                <div className="info-note">
                  <ShieldCheck size={17} />
                  <span>
                    论文和阅读记录保存在{storageLabel}
                    。开始翻译时，所选段落文字会发送到你配置的 LLM 服务。
                  </span>
                </div>
                <label className="field-label" htmlFor="base-url">
                  API Base URL
                </label>
                <input
                  id="base-url"
                  value={values.base_url}
                  onChange={(e) => set("base_url", e.target.value)}
                  placeholder="https://api.deepseek.com/v1"
                />
                <p className="field-help">
                  支持 OpenAI 兼容接口；填写基础地址，不包含 /chat/completions。
                </p>
                <label className="field-label" htmlFor="model-name">
                  模型名称
                </label>
                <input
                  id="model-name"
                  value={values.model}
                  onChange={(e) => set("model", e.target.value)}
                  placeholder="deepseek-chat"
                />
                <div className="label-row">
                  <label className="field-label" htmlFor="api-key">
                    API Key
                  </label>
                  {values.api_key_set && (
                    <span className="saved-secret">
                      <Check size={12} /> 已保存
                    </span>
                  )}
                </div>
                <div className="input-icon">
                  <KeyRound size={15} />
                  <input
                    id="api-key"
                    type="password"
                    autoComplete="new-password"
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    placeholder={
                      values.api_key_set
                        ? "留空保留已保存的 Key"
                        : "输入 API Key；本地服务可留空"
                    }
                  />
                </div>
                {values.api_key_set && (
                  <label className="checkbox-row">
                    <input
                      type="checkbox"
                      checked={clearKey}
                      onChange={(e) => setClearKey(e.target.checked)}
                    />
                    清除已保存的 Key
                  </label>
                )}
                <div className="setting-switch">
                  <div>
                    <strong>JSON 输出模式</strong>
                    <small>请求返回结构化译文；服务不支持时可关闭</small>
                  </div>
                  <button
                    className={`switch ${values.json_mode ? "checked" : ""}`}
                    role="switch"
                    aria-checked={values.json_mode}
                    aria-label="JSON 输出模式"
                    onClick={() => set("json_mode", !values.json_mode)}
                  >
                    <span />
                  </button>
                </div>
                <button
                  className="button secondary"
                  disabled={testing || busy}
                  onClick={test}
                >
                  {testing ? (
                    <LoaderCircle className="spin" size={15} />
                  ) : (
                    <Plug size={15} />
                  )}
                  保存并测试连接
                </button>
                <p className="field-help">
                  测试会发送一句英文，产生一次小额模型调用。
                </p>
              </>
            )}
            {tab === "parser" && (
              <>
                <label className="field-label">解析方式</label>
                <div className="parser-options">
                  {[
                    {
                      id: "existing",
                      name: "已有 MinerU 结果",
                      desc: "直接导入桌面版解析的论文，无需重新解析",
                      icon: FolderOpen,
                    },
                    {
                      id: "cli",
                      name: isServer ? "服务器命令行" : "本地命令行",
                      desc: isServer
                        ? "调用服务器上的 MinerU CLI 解析新 PDF"
                        : "调用本机 MinerU CLI 解析新 PDF",
                      icon: HardDrive,
                    },
                    {
                      id: "cloud",
                      name: "MinerU 云端 API",
                      desc: "将 PDF 上传至 MinerU 解析，需要 Token",
                      icon: Globe2,
                    },
                  ].map((p) => (
                    <button
                      key={p.id}
                      className={values.parser === p.id ? "selected" : ""}
                      onClick={() => set("parser", p.id)}
                    >
                      <p.icon size={19} />
                      <div>
                        <strong>{p.name}</strong>
                        <span>{p.desc}</span>
                      </div>
                      <span className="radio-dot" />
                    </button>
                  ))}
                </div>
                <label className="field-label" htmlFor="library-path">
                  {isServer
                    ? "服务器上的 MinerU 结果目录"
                    : "MinerU 桌面版论文目录"}
                </label>
                <input
                  id="library-path"
                  value={values.library_path}
                  onChange={(e) => set("library_path", e.target.value)}
                />
                <p className="field-help">
                  导入时复制解析结果，原目录中的文件保持不变。
                </p>
                {values.parser === "cli" && (
                  <>
                    <label className="field-label" htmlFor="mineru-command">
                      MinerU 命令或可执行文件路径
                    </label>
                    <input
                      id="mineru-command"
                      value={values.mineru_command}
                      onChange={(e) => set("mineru_command", e.target.value)}
                      placeholder="/path/to/env/bin/mineru"
                    />
                    <label className="field-label" htmlFor="mineru-backend">
                      Backend
                    </label>
                    <select
                      id="mineru-backend"
                      value={values.mineru_backend}
                      onChange={(e) => set("mineru_backend", e.target.value)}
                    >
                      <option value="pipeline">pipeline</option>
                      <option value="basic">MinerU 4 · Basic（CPU）</option>
                      <option value="standard">MinerU 4 · Standard</option>
                      <option value="advanced">MinerU 4 · Advanced</option>
                      <option value="flash">MinerU 4 · Flash</option>
                      <option value="vlm-auto-engine">vlm-auto-engine</option>
                      <option value="hybrid-auto-engine">
                        hybrid-auto-engine
                      </option>
                      <option value="vlm-http-client">vlm-http-client</option>
                    </select>
                    <p className="field-help">
                      MinerU 2.x 使用原生 CLI；MinerU 4 使用随项目提供的
                      parse_mineru4.py 适配器。约 4 GB 内存的服务器建议使用
                      Basic。
                    </p>
                  </>
                )}
                {values.parser === "cloud" && (
                  <>
                    <div className="label-row">
                      <label className="field-label" htmlFor="mineru-token">
                        MinerU API Token
                      </label>
                      {values.mineru_token_set && (
                        <span className="saved-secret">已保存</span>
                      )}
                    </div>
                    <input
                      id="mineru-token"
                      type="password"
                      autoComplete="new-password"
                      value={token}
                      onChange={(e) => setToken(e.target.value)}
                      placeholder={
                        values.mineru_token_set
                          ? "留空保留现有 Token"
                          : "输入 MinerU API Token"
                      }
                    />
                    {values.mineru_token_set && (
                      <label className="checkbox-row">
                        <input
                          type="checkbox"
                          checked={clearToken}
                          onChange={(e) => setClearToken(e.target.checked)}
                        />
                        清除已保存的 Token
                      </label>
                    )}
                    <p className="field-help">
                      仅在上传新 PDF 并选择云端解析时发送文件。
                    </p>
                  </>
                )}
              </>
            )}
            {tab === "glossary" && (
              <>
                <label className="field-label" htmlFor="glossary">
                  术语表
                </label>
                <textarea
                  id="glossary"
                  className="glossary-textarea"
                  value={values.glossary}
                  onChange={(e) => set("glossary", e.target.value)}
                  placeholder={"attention = 注意力\nagent = 智能体"}
                />
                <p className="field-help">
                  每行一个术语。翻译时提供给模型，帮助全文保持一致。更新后对后续翻译生效。
                </p>
                <label className="field-label" htmlFor="batch-chars">
                  每批原文字符数
                </label>
                <input
                  id="batch-chars"
                  type="number"
                  min={500}
                  max={15000}
                  step={500}
                  value={values.batch_chars}
                  onChange={(e) => set("batch_chars", Number(e.target.value))}
                />
                <p className="field-help">
                  按完整段落、章节边界分批。输出截断时可以调小；单个长段落保持完整。
                </p>
                <div className="info-note">
                  <Languages size={17} />
                  <span>
                    LLM 只负责翻译。段落
                    ID、页码、坐标和图像位置始终由程序管理；公式、代码和参考文献默认保留。
                  </span>
                </div>
              </>
            )}
          </div>
        )}
        <div className="modal-footer">
          <span>
            <HardDrive size={13} /> 设置仅保存在{storageLabel}
          </span>
          <button
            className="button primary"
            disabled={!values || busy || testing}
            onClick={() => save()}
          >
            {busy ? (
              <LoaderCircle className="spin" size={15} />
            ) : (
              <Check size={15} />
            )}
            保存设置
          </button>
        </div>
      </div>
    </div>
  );
}

function ImportDialog({
  onClose,
  onImported,
  onSettings,
  notify,
}: {
  onClose: () => void;
  onImported: (p: Paper) => void;
  onSettings: () => void;
  notify: (s: string, error?: boolean) => void;
}) {
  const { isServer } = useRuntime();
  const [tab, setTab] = useState(isServer ? "files" : "library");
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [pdf, setPdf] = useState<File | null>(null);
  const [archive, setArchive] = useState<File | null>(null);
  const [parser, setParser] = useState("existing");
  const [error, setError] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  useDialog(true, () => {
    if (!busy) onClose();
  });
  useEffect(() => {
    Promise.all([api<LibraryEntry[]>("/library"), api<Settings>("/settings")])
      .then(([e, s]) => {
        setEntries(e);
        setParser(s.parser);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);
  const importEntry = async (entry: LibraryEntry) => {
    setBusy(entry.path);
    setError("");
    try {
      const p = entry.imported_id
        ? await api<Paper>(`/documents/${entry.imported_id}`)
        : await api<Paper>("/import/local", {
            method: "POST",
            body: JSON.stringify({ path: entry.path }),
          });
      onImported(p);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  const takeFiles = (files: FileList | null) => {
    if (!files) return;
    for (const file of [...files]) {
      if (file.name.toLowerCase().endsWith(".pdf")) setPdf(file);
      else if (file.name.toLowerCase().endsWith(".zip")) setArchive(file);
      else notify("请选择 PDF 或 MinerU 结果 ZIP 文件", true);
    }
  };
  const upload = async () => {
    const form = new FormData();
    if (pdf) form.append("pdf", pdf);
    if (archive) form.append("archive", archive);
    setBusy("upload");
    setError("");
    try {
      onImported(
        await api<Paper>("/import/files", { method: "POST", body: form }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  };
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose();
      }}
    >
      <div
        className="modal import-modal"
        role="dialog"
        aria-modal="true"
        aria-label="导入论文"
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">A NEW PERSPECTIVE</span>
            <h2>下一篇，读什么？</h2>
            <p>导入论文，把精力留给理解。</p>
          </div>
          <button
            className="icon-button"
            disabled={!!busy}
            onClick={onClose}
            aria-label="关闭导入"
          >
            <X size={20} />
          </button>
        </div>
        <div className="modal-tabs">
          <button
            disabled={!!busy}
            className={tab === "library" ? "selected" : ""}
            onClick={() => setTab("library")}
          >
            <FolderOpen size={15} />
            MinerU 论文库
          </button>
          <button
            disabled={!!busy}
            className={tab === "files" ? "selected" : ""}
            onClick={() => setTab("files")}
          >
            <Upload size={15} />
            PDF / 结果 ZIP
          </button>
        </div>
        <div className="import-body">
          {error && (
            <div className="inline-error">
              <AlertCircle size={16} />
              {error}
            </div>
          )}
          {tab === "library" ? (
            <>
              {loading ? (
                <div className="loading-center">
                  <LoaderCircle className="spin" />
                </div>
              ) : entries.length ? (
                <>
                  <div className="import-caption">
                    发现 {entries.length} 篇已解析论文
                    <span>原文件不会被修改</span>
                  </div>
                  <div className="library-entries">
                    {entries.map((e) => (
                      <button
                        key={e.path}
                        disabled={!!busy}
                        className="library-entry"
                        onClick={() => importEntry(e)}
                      >
                        <div className="file-icon">
                          <FileText size={22} />
                        </div>
                        <div>
                          <strong>{e.name}</strong>
                          <span>
                            {e.imported_id
                              ? "已在论文库中 · 点击打开"
                              : "PDF + 结构化段落 + 图片"}
                          </span>
                        </div>
                        {busy === e.path ? (
                          <LoaderCircle size={17} className="spin" />
                        ) : e.imported_id ? (
                          <CheckCircle2 size={17} />
                        ) : (
                          <Plus size={18} />
                        )}
                      </button>
                    ))}
                  </div>
                </>
              ) : (
                <div className="import-empty">
                  <FolderOpen size={32} />
                  <h3>还没有找到解析结果</h3>
                  <p>
                    在设置中指定 MinerU 的论文目录，
                    <br />
                    或直接导入完整的结果 ZIP。
                  </p>
                  <button className="button secondary" onClick={onSettings}>
                    配置解析器
                  </button>
                </div>
              )}
            </>
          ) : (
            <>
              <button
                className="dropzone"
                disabled={!!busy}
                onClick={() => fileInput.current?.click()}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  if (!busy) takeFiles(e.dataTransfer.files);
                }}
              >
                <div className="upload-icon">
                  <ArrowDownToLine size={25} />
                </div>
                <strong>拖入文件，或点击选择</strong>
                <span>支持论文 PDF 和 MinerU 解析结果 ZIP</span>
                <small>PDF ≤ 200 MB · ZIP ≤ 400 MB</small>
              </button>
              <input
                ref={fileInput}
                hidden
                type="file"
                accept=".pdf,.zip"
                multiple
                onChange={(e) => {
                  takeFiles(e.target.files);
                  e.target.value = "";
                }}
              />
              <div className="selected-files">
                {[
                  { file: pdf, remove: () => setPdf(null) },
                  { file: archive, remove: () => setArchive(null) },
                ].map(
                  ({ file, remove }, i) =>
                    file && (
                      <div key={i}>
                        <FileText size={17} />
                        <span>
                          {file.name}
                          <small>
                            {(file.size / 1024 / 1024).toFixed(1)} MB
                          </small>
                        </span>
                        <button
                          className="icon-button"
                          disabled={!!busy}
                          onClick={remove}
                          aria-label="移除文件"
                        >
                          <X size={15} />
                        </button>
                      </div>
                    ),
                )}
              </div>
              <div className="info-note">
                <FileText size={17} />
                <span>
                  {archive
                    ? "ZIP 需包含 content_list JSON 和 images。原 PDF 可放在 ZIP 内，也可以单独选择。"
                    : parser === "existing"
                      ? "当前使用已有解析结果。仅导入 PDF 时，需先配置本地 CLI 或云端解析。"
                      : parser === "cloud"
                        ? "当前使用 MinerU 云端解析。导入后，PDF 将上传至 MinerU。"
                        : isServer
                          ? "当前使用服务器上的 MinerU CLI，导入后会在服务器解析。"
                          : "当前使用本地 MinerU CLI，导入后会在本机解析。"}
                </span>
              </div>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button
            className="text-button"
            disabled={!!busy}
            onClick={onSettings}
          >
            <Settings2 size={14} />
            解析器设置
          </button>
          {tab === "files" ? (
            <button
              className="button primary"
              disabled={!!busy || (!pdf && !archive)}
              onClick={upload}
            >
              {busy ? (
                <LoaderCircle size={15} className="spin" />
              ) : (
                <Plus size={15} />
              )}
              导入论文
            </button>
          ) : (
            <span className="small-muted">点击论文即可导入并打开</span>
          )}
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const { storageLabel, workspaceLabel, workspaceEnglish } = useRuntime();
  const [papers, setPapers] = useState<Paper[]>([]);
  const [paper, setPaper] = useState<Paper | null>(null);
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [modal, setModal] = useState("");
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [deletePaper, setDeletePaper] = useState<Paper | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const notify = useCallback((message: string, error = false) => {
    setToast({ message, error });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 6000);
  }, []);
  const refresh = useCallback(
    () =>
      api<Paper[]>("/documents")
        .then(setPapers)
        .catch((e) => notify(e.message, true)),
    [notify],
  );
  useEffect(() => {
    refresh().finally(() => setLoading(false));
  }, [refresh]);
  const hasActiveTasks = papers.some((p) => active(p));
  useEffect(() => {
    if (paper || !hasActiveTasks) return;
    const timer = setInterval(refresh, 2000);
    return () => clearInterval(timer);
  }, [paper?.id, hasActiveTasks, refresh]);
  useEffect(() => {
    const load = () => {
      const id = window.location.hash.match(/^#paper\/([a-f0-9]+)$/)?.[1];
      if (!id) {
        setPaper(null);
        return;
      }
      setOpening(true);
      api<Paper>(`/documents/${id}`)
        .then(setPaper)
        .catch((e) => {
          notify(e.message, true);
          window.location.hash = "";
        })
        .finally(() => setOpening(false));
    };
    load();
    window.addEventListener("hashchange", load);
    return () => window.removeEventListener("hashchange", load);
  }, [notify]);
  const update = useCallback((next: Paper) => {
    setPaper(next);
    setPapers((prev) => prev.map((p) => (p.id === next.id ? next : p)));
  }, []);
  const open = (p: Paper) => {
    window.location.hash = `paper/${p.id}`;
  };
  const imported = (p: Paper) => {
    setModal("");
    refresh();
    open(p);
    notify("论文已准备好，点击「开始翻译」即可生成译文");
  };
  const remove = async () => {
    if (!deletePaper) return;
    try {
      await api(`/documents/${deletePaper.id}`, { method: "DELETE" });
      setDeletePaper(null);
      refresh();
      notify("已从本应用移除，MinerU 原文件保持不变");
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const shown = papers.filter(
    (p) =>
      p.title.toLowerCase().includes(query.toLowerCase()) &&
      (filter === "all" ||
        (filter === "done"
          ? p.total > 0 && p.translated === p.total
          : p.translated < p.total || !p.total)),
  );
  const translated = papers.filter(
    (p) => p.total > 0 && p.translated === p.total,
  ).length;

  return (
    <div className={`app-shell ${paper ? "reader-layout" : ""}`}>
      <aside className="sidebar">
        <button
          className="brand-button"
          onClick={() => {
            window.location.hash = "";
          }}
          aria-label="返回首页"
        >
          <Mark small={!!paper} />
        </button>
        <div className="sidebar-body">
          <div className="nav-eyebrow">工作空间</div>
          <button
            className="nav-item selected"
            onClick={() => {
              window.location.hash = "";
            }}
            title="论文库"
          >
            <Library size={18} />
            <span>论文库</span>
            <small>{papers.length}</small>
          </button>
          <button
            className="nav-item"
            onClick={() => setModal("import")}
            title="导入论文"
          >
            <Plus size={18} />
            <span>导入论文</span>
          </button>
          <button
            className="nav-item"
            onClick={() => setModal("settings")}
            title="应用设置"
          >
            <Settings2 size={18} />
            <span>应用设置</span>
          </button>
        </div>
        <div className="sidebar-bottom">
          <div className="local-badge">
            <span className="status-dot" />
            <span>{workspaceLabel}</span>
          </div>
          <p>理解，不必隔着语言。</p>
          <div className="sidebar-version">
            <span>纸间</span>
            <span>v0.1.0</span>
          </div>
        </div>
      </aside>
      <main className="app-main">
        <Suspense
          fallback={
            <div className="loading-center full">
              <LoaderCircle className="spin" />
              <span>正在加载阅读器…</span>
            </div>
          }
        >
          {opening ? (
            <div className="loading-center full">
              <LoaderCircle className="spin" />
              <span>正在打开论文…</span>
            </div>
          ) : paper ? (
            <Reader
              key={paper.id}
              paper={paper}
              onUpdate={update}
              onBack={() => {
                window.location.hash = "";
                refresh();
              }}
              onSettings={() => setModal("settings")}
              notify={notify}
            />
          ) : (
            <>
              <header className="library-topbar">
                <span>
                  <span className="status-dot" /> {workspaceEnglish}
                </span>
                <div>
                  <HardDrive size={14} /> 数据保存在{storageLabel}
                  <button
                    className="icon-button"
                    onClick={() => setModal("settings")}
                    title="应用设置"
                  >
                    <SlidersHorizontal size={17} />
                  </button>
                </div>
              </header>
              <div className="library-page">
                <section className="library-hero">
                  <div className="hero-copy">
                    <div className="eyebrow">
                      <span /> READ BEYOND LANGUAGE
                    </div>
                    <h1>
                      读懂论文，
                      <br />
                      让思想自由抵达<span>。</span>
                    </h1>
                    <p>
                      从英文原文到中文理解。保留每一处公式、
                      <br className="desktop-br" />
                      每一段推导，让阅读回到内容本身。
                    </p>
                    <button
                      className="button primary hero-button"
                      onClick={() => setModal("import")}
                    >
                      <Plus size={17} />
                      导入论文
                      <ArrowRight size={15} />
                    </button>
                  </div>
                  <div className="hero-illustration" aria-hidden="true">
                    <div className="orbit orbit-one" />
                    <div className="orbit orbit-two" />
                    <span className="floating-plus plus-one">+</span>
                    <span className="floating-plus plus-two">+</span>
                    <div className="illustration-paper back-paper">
                      <div className="mini-paper-label">ORIGINAL</div>
                      <div className="mini-title">
                        Ideas have
                        <br />
                        no borders.
                      </div>
                      <div className="mini-lines">
                        <i />
                        <i />
                        <i />
                        <i />
                      </div>
                      <div className="mini-formula">f(x) = ∑ αᵢ · xᵢ</div>
                      <div className="mini-lines short">
                        <i />
                        <i />
                        <i />
                      </div>
                      <div className="paper-page-number">01</div>
                    </div>
                    <div className="illustration-paper front-paper">
                      <div className="mini-paper-label">
                        中文译文 <span>ZH</span>
                      </div>
                      <div className="mini-title">
                        思想，
                        <br />
                        本无边界。
                      </div>
                      <div className="mini-lines">
                        <i />
                        <i />
                        <i />
                        <i />
                      </div>
                      <div className="mini-highlight">
                        让每一次阅读，都更进一步。
                      </div>
                      <div className="mini-lines short">
                        <i />
                        <i />
                      </div>
                      <div className="paper-page-number">01</div>
                    </div>
                    <div className="translation-stamp">
                      <Languages size={17} />
                      <span>
                        原文 · 译文
                        <br />
                        <strong>始终对应</strong>
                      </span>
                      <CheckCircle2 size={14} />
                    </div>
                  </div>
                </section>
                <section className="library-section">
                  <div className="section-title-row">
                    <div>
                      <h2>
                        我的论文<span>{papers.length}</span>
                      </h2>
                      <p>你的知识，从这里继续。</p>
                    </div>
                    <div className="library-search">
                      <Search size={16} />
                      <input
                        aria-label="搜索论文"
                        placeholder="搜索论文标题…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                      {query && (
                        <button
                          className="icon-button"
                          onClick={() => setQuery("")}
                          aria-label="清除搜索"
                        >
                          <X size={13} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="library-filter-row">
                    <div className="library-filters">
                      {[
                        { id: "all", label: "全部论文", count: papers.length },
                        {
                          id: "pending",
                          label: "待完成",
                          count: papers.length - translated,
                        },
                        { id: "done", label: "已翻译", count: translated },
                      ].map((f) => (
                        <button
                          className={filter === f.id ? "selected" : ""}
                          key={f.id}
                          onClick={() => setFilter(f.id)}
                        >
                          {f.label}
                          <span>{f.count}</span>
                        </button>
                      ))}
                    </div>
                    <span className="sort-label">
                      <Clock3 size={13} />
                      最近更新
                    </span>
                  </div>
                  {loading ? (
                    <div className="loading-center">
                      <LoaderCircle className="spin" />
                    </div>
                  ) : shown.length ? (
                    <div className="paper-grid">
                      {shown.map((p) => (
                        <article key={p.id} className="paper-card">
                          <button
                            className="paper-card-main"
                            onClick={() => open(p)}
                          >
                            <div className="card-top">
                              <div className="card-file-icon">
                                <FileText size={22} />
                              </div>
                              <span
                                className={`paper-state ${p.translated === p.total && p.total ? "done" : active(p) ? "working" : ""}`}
                              >
                                {active(p) ? (
                                  <>
                                    <LoaderCircle className="spin" size={11} />
                                    处理中
                                  </>
                                ) : p.translated === p.total && p.total ? (
                                  <>
                                    <Check size={11} />
                                    已翻译
                                  </>
                                ) : p.translated ? (
                                  "部分已译"
                                ) : (
                                  "待翻译"
                                )}
                              </span>
                            </div>
                            <h3>{p.title}</h3>
                            <div className="paper-meta">
                              <span>PDF</span>
                              <span>·</span>
                              <span>{p.pages.length || "—"} 页</span>
                              <span>·</span>
                              <span>{p.total || "—"} 段</span>
                            </div>
                            <div className="card-progress">
                              <div className="progress-track">
                                <i
                                  style={{
                                    width:
                                      (p.total
                                        ? (p.translated / p.total) * 100
                                        : 0) + "%",
                                  }}
                                />
                              </div>
                              <span>
                                {p.total
                                  ? Math.round((p.translated / p.total) * 100)
                                  : 0}
                                %
                              </span>
                            </div>
                          </button>
                          <div className="paper-card-footer">
                            <span>
                              {new Date(p.updated_at).toLocaleDateString(
                                "zh-CN",
                                { month: "short", day: "numeric" },
                              )}{" "}
                              更新
                            </span>
                            <button
                              className="text-button read-button"
                              onClick={() => open(p)}
                            >
                              继续阅读
                              <ArrowRight size={13} />
                            </button>
                            <button
                              className="icon-button delete-button"
                              disabled={active(p)}
                              title="从本应用移除论文"
                              onClick={() => setDeletePaper(p)}
                            >
                              <Trash2 size={14} />
                            </button>
                          </div>
                        </article>
                      ))}
                      <button
                        className="add-paper-card"
                        onClick={() => setModal("import")}
                      >
                        <div>
                          <Plus size={23} />
                        </div>
                        <strong>添加下一篇论文</strong>
                        <span>新的理解，从这里开始</span>
                      </button>
                    </div>
                  ) : (
                    <div className="empty-library">
                      <div className="empty-library-icon">
                        <BookOpen size={30} />
                      </div>
                      <h3>
                        {query || filter !== "all"
                          ? "没有找到符合条件的论文"
                          : "为下一次理解，翻开第一页。"}
                      </h3>
                      <p>
                        {query || filter !== "all"
                          ? "试试其他关键词或查看全部论文。"
                          : "导入 PDF 或已有的 MinerU 解析结果，建立你的双语论文库。"}
                      </p>
                      <button
                        className="button secondary"
                        onClick={() => {
                          if (query || filter !== "all") {
                            setQuery("");
                            setFilter("all");
                          } else setModal("import");
                        }}
                      >
                        {query || filter !== "all"
                          ? "查看全部论文"
                          : "导入第一篇论文"}
                        <ArrowRight size={14} />
                      </button>
                    </div>
                  )}
                </section>
                <footer className="library-footer">
                  <span>纸间 · 让理解发生</span>
                  <div>
                    <ShieldCheck size={13} />
                    {storageLabel}保存
                    <Languages size={13} />
                    自由对照
                    <LinkIcon />
                    原文可溯
                  </div>
                </footer>
              </div>
            </>
          )}
        </Suspense>
      </main>
      {modal === "settings" && (
        <SettingsDialog onClose={() => setModal("")} notify={notify} />
      )}
      {modal === "import" && (
        <ImportDialog
          onClose={() => setModal("")}
          onImported={imported}
          onSettings={() => setModal("settings")}
          notify={notify}
        />
      )}
      {deletePaper && (
        <div className="modal-backdrop">
          <div
            className="modal confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-label="移除论文"
          >
            <div className="modal-heading">
              <h2>从论文库移除？</h2>
              <button
                className="icon-button"
                onClick={() => setDeletePaper(null)}
                aria-label="关闭"
              >
                <X size={18} />
              </button>
            </div>
            <p>将删除本应用中这篇论文的副本和译文。MinerU 原文件保持不变。</p>
            <strong>{deletePaper.title}</strong>
            <div className="modal-footer">
              <button
                className="button secondary"
                onClick={() => setDeletePaper(null)}
              >
                保留
              </button>
              <button className="button danger" onClick={remove}>
                <Trash2 size={14} />
                确认移除
              </button>
            </div>
          </div>
        </div>
      )}
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          {toast.error ? <AlertCircle size={17} /> : <CheckCircle2 size={17} />}
          <span>{toast.message}</span>
          <button
            className="icon-button"
            onClick={() => setToast(null)}
            aria-label="关闭通知"
          >
            <X size={14} />
          </button>
        </div>
      )}
    </div>
  );
}
function LinkIcon() {
  return <span className="footer-link-icon">↔</span>;
}
