import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ChevronDown,
  Download,
  FileJson,
  FileText,
  FolderArchive,
  Languages,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Pause,
  PencilLine,
  RefreshCw,
  Save,
  Settings2,
  X,
  Link2,
  List,
  Check,
  AlertCircle,
  Maximize2,
  Minimize2,
  Combine,
  Split,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import DOMPurify from "dompurify";
import PdfViewer from "./PdfViewer";
import { useDialog } from "./useDialog";
import { useRuntime } from "./Runtime";
import {
  active,
  api,
  assetUrl,
  MODES,
  type Block,
  type Location,
  type Mode,
  type Paper,
} from "./types";

function Content({ text }: { text: string }) {
  if (/<table[\s\S]*?<\/table>/i.test(text)) {
    const chunks = text.split(/(<table[\s\S]*?<\/table>)/gi);
    return (
      <>
        {chunks.map((chunk, i) =>
          /^<table/i.test(chunk) ? (
            <div
              className="table-scroll"
              key={i}
              dangerouslySetInnerHTML={{
                __html: DOMPurify.sanitize(chunk, {
                  ALLOWED_TAGS: [
                    "table",
                    "thead",
                    "tbody",
                    "tfoot",
                    "tr",
                    "td",
                    "th",
                    "br",
                    "b",
                    "i",
                    "strong",
                    "em",
                    "sub",
                    "sup",
                  ],
                  ALLOWED_ATTR: ["colspan", "rowspan"],
                }),
              }}
            />
          ) : (
            <Content key={i} text={chunk} />
          ),
        )}
      </>
    );
  }
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[rehypeKatex]}
      components={{
        a: (props) => <a {...props} target="_blank" rel="noreferrer" />,
      }}
    >
      {text}
    </ReactMarkdown>
  );
}

export default function Reader({
  paper,
  onUpdate,
  onBack,
  onSettings,
  notify,
}: {
  paper: Paper;
  onUpdate: (p: Paper) => void;
  onBack: () => void;
  onSettings: () => void;
  notify: (s: string, error?: boolean) => void;
}) {
  const [mode, setMode] = useState<Mode>(() => {
    const saved = localStorage.getItem("paper-mode");
    return MODES.some((m) => m.id === saved) ? (saved as Mode) : "zh";
  });
  const [focused, setFocused] = useState(
    () => localStorage.getItem("paper-focus") !== "false",
  );
  const { storageLabel } = useRuntime();
  const [showPdf, setShowPdf] = useState(true);
  const [selected, setSelected] = useState("");
  const [focusLocation, setFocusLocation] = useState<Location | null>(null);
  const [page, setPage] = useState(0);
  const [edit, setEdit] = useState<Block | null>(null);
  const [structure, setStructure] = useState<{
    kind: "merge" | "split";
    block: Block;
    next?: Block;
  } | null>(null);
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  useDialog(!!edit || !!structure, () => {
    if (!saving) {
      setEdit(null);
      setStructure(null);
    }
  });
  const [exporting, setExporting] = useState(false);
  const [menu, setMenu] = useState("");
  const [toc, setToc] = useState(false);
  const [sync, setSync] = useState(false);
  const content = useRef<HTMLDivElement>(null);
  const source = useRef<"pdf" | "reader">("reader");
  const exportMenu = useRef<HTMLDivElement>(null);
  const enterFocus = useRef<HTMLButtonElement>(null);
  const exitFocus = useRef<HTMLButtonElement>(null);
  const headingBlocks = paper.blocks.filter((b) => b.type === "heading");
  const running = active(paper);
  const percent = paper.total
    ? Math.round((paper.translated / paper.total) * 100)
    : 0;
  const groups = useMemo(() => {
    const groups: Block[][] = [];
    for (const block of paper.blocks) {
      if (
        !groups.length ||
        groups[groups.length - 1][0].section_id !== block.section_id
      )
        groups.push([]);
      groups[groups.length - 1].push(block);
    }
    return groups;
  }, [paper.blocks]);
  const nextBlocks = useMemo(
    () =>
      new Map(
        paper.blocks.slice(0, -1).map((b, i) => [b.id, paper.blocks[i + 1]]),
      ),
    [paper.blocks],
  );

  const changeFocus = (next: boolean) => {
    setMenu("");
    setToc(false);
    setFocused(next);
    requestAnimationFrame(() => {
      (next ? exitFocus : enterFocus).current?.focus();
    });
  };
  useEffect(() => {
    localStorage.setItem("paper-focus", String(focused));
  }, [focused]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => {
      if (
        event.key !== "Escape" ||
        event.defaultPrevented ||
        document.querySelector('[role="dialog"]')
      )
        return;
      if (menu) setMenu("");
      else if (toc) setToc(false);
      else if (focused) changeFocus(false);
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [focused, menu, toc]);

  useEffect(() => {
    localStorage.setItem("paper-mode", mode);
    if (selected) {
      content.current
        ?.querySelector(`[data-block-id="${selected}"]`)
        ?.scrollIntoView({ block: "center" });
    }
  }, [mode]);
  useEffect(() => {
    if (!running) return;
    let disposed = false;
    const timer = setInterval(() => {
      api<Paper>(`/documents/${paper.id}`)
        .then((p) => {
          if (!disposed) onUpdate(p);
        })
        .catch(() => {});
    }, 1500);
    return () => {
      disposed = true;
      clearInterval(timer);
    };
  }, [paper.id, running, onUpdate]);
  useEffect(() => {
    if (!menu) return;
    const listener = (event: MouseEvent) => {
      if (!exportMenu.current?.contains(event.target as Node)) setMenu("");
    };
    document.addEventListener("mousedown", listener);
    return () => document.removeEventListener("mousedown", listener);
  }, [menu]);

  const select = (
    block: Block,
    fromPdf = false,
    clickedLocation?: Location,
  ) => {
    source.current = fromPdf ? "pdf" : "reader";
    setSelected(block.id);
    const loc =
      clickedLocation ||
      block.source_locations.find((v) => v.page_index === page) ||
      block.source_locations[0];
    setFocusLocation(loc || null);
    if (loc && !fromPdf) setPage(loc.page_index);
    if (fromPdf || !showPdf) {
      content.current
        ?.querySelector(`[data-block-id="${block.id}"]`)
        ?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setToc(false);
  };

  const syncScroll = () => {
    if (!sync || source.current === "pdf" || !content.current) return;
    const top = content.current.getBoundingClientRect().top + 100;
    const nodes = [
      ...content.current.querySelectorAll<HTMLElement>("[data-block-id]"),
    ];
    const visible = nodes.find((el) => el.getBoundingClientRect().bottom > top);
    const block = paper.blocks.find((b) => b.id === visible?.dataset.blockId);
    if (block && block.id !== selected) {
      setSelected(block.id);
      if (block.source_locations[0])
        setPage(block.source_locations[0].page_index);
    }
  };

  const action = async (path: string, body: object = {}) => {
    try {
      onUpdate(
        await api<Paper>(`/documents/${paper.id}/${path}`, {
          method: "POST",
          body: JSON.stringify(body),
        }),
      );
    } catch (e) {
      notify((e as Error).message, true);
    }
  };
  const save = async () => {
    if (!edit) return;
    setSaving(true);
    try {
      onUpdate(
        await api<Paper>(`/documents/${paper.id}/blocks/${edit.id}`, {
          method: "PATCH",
          body: JSON.stringify({ translation: draft, revision: edit.revision }),
        }),
      );
      setEdit(null);
      notify("译文已保存");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  };
  const saveStructure = async () => {
    if (!structure) return;
    const { kind, block, next } = structure;
    setSaving(true);
    try {
      const updated = await api<Paper>(
        `/documents/${paper.id}/blocks/${block.id}/${kind === "merge" ? "merge-next" : "split"}`,
        {
          method: "POST",
          body: JSON.stringify({
            revision: block.revision,
            ...(next
              ? { next_block_id: next.id, next_revision: next.revision }
              : {}),
          }),
        },
      );
      onUpdate(updated);
      setSelected(block.id);
      setStructure(null);
      notify(
        kind === "merge"
          ? "已合并为完整段落，可重新翻译该段"
          : "已恢复原始分段和合并前的译文",
      );
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setSaving(false);
    }
  };
  const download = async (format: string) => {
    setExporting(true);
    setMenu("");
    try {
      const r = await fetch(
        `/api/documents/${paper.id}/export?mode=${mode}&format=${format}`,
      );
      if (!r.ok) {
        const body = await r.json();
        throw new Error(body.detail || "导出失败");
      }
      const url = URL.createObjectURL(await r.blob());
      const a = document.createElement("a");
      a.href = url;
      a.download =
        paper.title.slice(0, 80).replace(/[\\/:*?"<>|]/g, "_") + "." + format;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 3000);
      notify("已导出到下载文件夹");
    } catch (e) {
      notify((e as Error).message, true);
    } finally {
      setExporting(false);
    }
  };

  const blockView = (block: Block, language: "en" | "zh", keySuffix = "") => {
    const next = nextBlocks.get(block.id);
    const canMerge =
      block.type === "paragraph" &&
      block.translatable &&
      !block.asset &&
      next?.type === "paragraph" &&
      next.translatable &&
      !next.asset &&
      block.section_id === next.section_id;
    const merged = (block.source_parts?.length || 0) > 1;
    const text =
      language === "en" || !block.translatable
        ? block.original
        : block.translation;
    const isHeading = block.type === "heading";
    return (
      <article
        key={block.id + keySuffix}
        data-block-id={block.id}
        className={`paper-block ${isHeading ? "heading-block" : ""} ${selected === block.id ? "is-selected" : ""} ${language === "en" ? "english" : "chinese"}`}
        onClick={() => select(block)}
      >
        {block.asset &&
          !(
            mode === "paragraph" &&
            language === "zh" &&
            block.translatable
          ) && (
            <img
              className="paper-figure"
              loading="lazy"
              src={assetUrl(paper.id, block.asset)}
              alt={block.original || "论文图表"}
            />
          )}
        {isHeading && (text || mode === "zh") ? (
          <div
            role="heading"
            aria-level={block.level}
            className={`paper-heading level-${block.level}`}
          >
            {text || block.original}
          </div>
        ) : text ? (
          <Content text={text} />
        ) : (
          <div className="untranslated">
            <span>待翻译</span>
            {mode === "zh" && <Content text={block.original} />}
          </div>
        )}
        {merged && language === "zh" && (
          <div
            className="paragraph-locations"
            onClick={(e) => e.stopPropagation()}
          >
            <span>续段已合并</span>
            {block.source_locations.map((loc, i) => (
              <button
                key={i}
                title={`定位原文片段 ${i + 1}（第 ${loc.page_index + 1} 页）`}
                onClick={() => {
                  source.current = "reader";
                  setSelected(block.id);
                  setFocusLocation(loc);
                  setShowPdf(true);
                  setPage(loc.page_index);
                }}
              >
                原文 {i + 1} · 第 {loc.page_index + 1} 页
              </button>
            ))}
          </div>
        )}
        {block.translatable && language === "zh" && (
          <div className="block-actions" onClick={(e) => e.stopPropagation()}>
            {block.status === "edited" && (
              <span className="edited-badge">
                <Check size={11} /> 已编辑
              </span>
            )}
            <button
              title="定位原 PDF"
              className="icon-button"
              disabled={!block.source_locations.length}
              onClick={() => {
                setShowPdf(true);
                select(block);
              }}
            >
              <Link2 size={13} />
            </button>
            <button
              title="编辑译文"
              className="icon-button"
              onClick={() => {
                setEdit(block);
                setDraft(block.translation);
              }}
            >
              <PencilLine size={13} />
            </button>
            <button
              title="重新翻译此段"
              className="icon-button"
              disabled={running}
              onClick={() => action("translate", { block_ids: [block.id] })}
            >
              <RefreshCw size={13} />
            </button>
            {canMerge && (
              <button
                title="与下一段合并"
                aria-label="与下一段合并"
                className="icon-button"
                disabled={running}
                onClick={() => setStructure({ kind: "merge", block, next })}
              >
                <Combine size={13} />
              </button>
            )}
            {merged && (
              <button
                title="恢复原始分段"
                aria-label="恢复原始分段"
                className="icon-button"
                disabled={running}
                onClick={() => setStructure({ kind: "split", block })}
              >
                <Split size={13} />
              </button>
            )}
          </div>
        )}
      </article>
    );
  };

  return (
    <div className={`reader ${focused ? "reader-focused" : ""}`}>
      {focused && (
        <button
          ref={exitFocus}
          className="focus-restore"
          onClick={() => changeFocus(false)}
          title="显示工具栏与目录入口（Esc）"
          aria-keyshortcuts="Escape"
        >
          {running ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <Minimize2 size={14} />
          )}
          显示工具栏
          <kbd>Esc</kbd>
        </button>
      )}
      <header className="reader-topbar">
        <div className="reader-breadcrumb">
          <button
            className="icon-button"
            onClick={onBack}
            aria-label="返回论文库"
          >
            <ArrowLeft size={18} />
          </button>
          <span className="breadcrumb-label">论文库</span>
          <span className="breadcrumb-slash">/</span>
          <strong title={paper.title}>{paper.title}</strong>
        </div>
        <div className="reader-header-actions">
          <button
            ref={enterFocus}
            className="button subtle"
            aria-label="专注阅读"
            title="收起工具栏，专注阅读论文"
            onClick={() => changeFocus(true)}
          >
            <Maximize2 size={15} />
            <span>专注阅读</span>
          </button>
          <button
            className="icon-button"
            aria-label="应用设置"
            onClick={onSettings}
          >
            <Settings2 size={17} />
          </button>
        </div>
      </header>
      <div className="reader-toolbar">
        <div className="toolbar-left">
          <button
            className={`icon-button toc-trigger ${toc ? "on" : ""}`}
            title="论文目录"
            aria-label="论文目录"
            aria-expanded={toc}
            aria-controls="reader-outline"
            onClick={() => setToc(!toc)}
          >
            <List size={18} />
          </button>
          <button
            className={`button subtle ${showPdf ? "on" : ""}`}
            aria-label="显示原 PDF"
            aria-pressed={showPdf}
            onClick={() => setShowPdf(!showPdf)}
          >
            {showPdf ? (
              <PanelLeftClose size={15} />
            ) : (
              <PanelLeftOpen size={15} />
            )}
            <span>原 PDF</span>
          </button>
          <div className="select-wrap">
            <Languages size={15} />
            <select
              aria-label="阅读格式"
              value={mode}
              onChange={(e) => setMode(e.target.value as Mode)}
            >
              {MODES.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
            <ChevronDown size={13} />
          </div>
        </div>
        <div className="toolbar-right">
          <span className="translation-count">
            {paper.translated} / {paper.total} 段
          </span>
          {running ? (
            <button
              className="button secondary"
              disabled={paper.job.state === "stopping"}
              onClick={() => action("pause")}
            >
              <Pause size={14} />
              {paper.job.state === "stopping" ? "暂停中" : "暂停"}
            </button>
          ) : (
            <button
              className="button primary"
              disabled={!paper.blocks.length}
              onClick={() => action("translate")}
            >
              <Languages size={15} />
              {paper.translated === paper.total && paper.total
                ? "检查未译段落"
                : paper.translated
                  ? "继续翻译"
                  : "开始翻译"}
            </button>
          )}
          <div className="export-wrap" ref={exportMenu}>
            <button
              className="button secondary"
              disabled={!paper.blocks.length || exporting}
              onClick={() => setMenu(menu ? "" : "export")}
            >
              {exporting ? (
                <LoaderCircle className="spin" size={15} />
              ) : (
                <Download size={15} />
              )}
              <span>导出</span>
              <ChevronDown size={12} />
            </button>
            {menu && (
              <div className="dropdown export-menu">
                <div className="dropdown-caption">按当前阅读格式导出</div>
                <button onClick={() => download("zip")}>
                  <FolderArchive size={16} />
                  <div>
                    Markdown 完整包<small>包含图片和双语 JSON · 推荐</small>
                  </div>
                </button>
                <button onClick={() => download("md")}>
                  <FileText size={16} />
                  <div>
                    Markdown 文件<small>图片引用需配合完整包使用</small>
                  </div>
                </button>
                <button onClick={() => download("json")}>
                  <FileJson size={16} />
                  <div>
                    结构化 JSON<small>保留原译文与位置映射</small>
                  </div>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
      {(running ||
        paper.job.state === "error" ||
        paper.job.state === "paused") && (
        <div
          className={`job-banner ${paper.job.state === "error" ? "error" : ""}`}
        >
          {running ? (
            <LoaderCircle size={14} className="spin" />
          ) : (
            <AlertCircle size={14} />
          )}
          <span>{paper.job.message}</span>
          {paper.job.state === "error" && !paper.blocks.length && (
            <button onClick={() => action("parse")}>重试解析</button>
          )}
        </div>
      )}
      <div className="reader-workspace">
        {toc && (
          <button
            className="outline-backdrop"
            aria-label="关闭论文目录"
            onClick={() => setToc(false)}
          />
        )}
        <aside
          id="reader-outline"
          aria-label="论文目录"
          className={`outline ${toc ? "mobile-open" : ""}`}
        >
          <div className="outline-title">
            论文目录
            <button
              className="icon-button"
              aria-label="关闭目录"
              onClick={() => setToc(false)}
            >
              <X size={14} />
            </button>
          </div>
          <nav>
            {headingBlocks.map((b, i) => (
              <button
                key={b.id}
                className={
                  selected === b.id ||
                  paper.blocks.find((v) => v.id === selected)?.section_id ===
                    b.id
                    ? "selected"
                    : ""
                }
                onClick={() => {
                  source.current = "pdf";
                  setSelected(b.id);
                  if (b.source_locations[0])
                    setPage(b.source_locations[0].page_index);
                  content.current
                    ?.querySelector(`[data-block-id="${b.id}"]`)
                    ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  setToc(false);
                }}
              >
                <span>{String(i + 1).padStart(2, "0")}</span>
                <span>{b.translation || b.original}</span>
              </button>
            ))}
          </nav>
          <div className="outline-bottom">
            <div>
              <span>翻译进度</span>
              <strong>{percent}%</strong>
            </div>
            <div className="progress-track">
              <i style={{ width: percent + "%" }} />
            </div>
            <small>修改与翻译自动保存在{storageLabel}</small>
          </div>
        </aside>
        {showPdf && (
          <PdfViewer
            paper={paper}
            selected={selected}
            focusLocation={focusLocation}
            onSelect={(b, loc) => select(b, true, loc)}
            page={page}
            setPage={setPage}
          />
        )}
        <section
          className={`translation-panel ${!showPdf ? "full-width" : ""}`}
        >
          <div className="pane-header">
            <span>
              <Languages size={15} />
              {MODES.find((m) => m.id === mode)?.short || "译文"}
            </span>
            <button
              className={`sync-toggle ${sync ? "enabled" : ""}`}
              title="滚动译文时让 PDF 按段落跟随"
              onClick={() => setSync(!sync)}
            >
              <Link2 size={12} />
              {sync ? "滚动联动已开启" : "滚动联动"}
            </button>
          </div>
          <div
            className="translation-scroll"
            ref={content}
            onScroll={syncScroll}
            onWheel={() => {
              source.current = "reader";
            }}
            onTouchMove={() => {
              source.current = "reader";
            }}
          >
            {!paper.blocks.length ? (
              <div className="reader-empty">
                <LoaderCircle className={running ? "spin" : ""} size={30} />
                <h3>{running ? "正在还原论文结构" : "等待解析结果"}</h3>
                <p>解析完成后，标题、段落、公式和图表会在这里出现。</p>
              </div>
            ) : (
              <div className="paper-content">
                <div className="reading-eyebrow">
                  <span>ACADEMIC READING</span>
                  <span>{paper.pages.length} PAGES</span>
                </div>
                {mode === "section"
                  ? groups.map((group, i) => (
                      <section
                        key={group[0].section_id}
                        className="section-group"
                      >
                        <div className="language-divider">ENGLISH · 原文</div>
                        {group.map((b) => blockView(b, "en", "en"))}
                        <div className="language-divider chinese-divider">
                          中文 · 译文
                        </div>
                        {group.map((b) => blockView(b, "zh", "zh"))}
                        {i < groups.length - 1 && <hr />}
                      </section>
                    ))
                  : paper.blocks.map((block) => (
                      <div
                        key={block.id}
                        className={`block-pair ${mode === "paragraph" ? "bilingual" : ""}`}
                      >
                        {mode === "paragraph" && block.translatable && (
                          <div className="original-block">
                            {blockView(block, "en", "en")}
                          </div>
                        )}
                        {blockView(block, mode === "en" ? "en" : "zh", "main")}
                      </div>
                    ))}
                <div className="paper-end">
                  <span /> 文末 <span />
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
      {structure && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget && !saving) setStructure(null);
          }}
        >
          <div
            className="modal paragraph-modal"
            role="dialog"
            aria-modal="true"
            aria-label={
              structure.kind === "merge" ? "合并正文段落" : "恢复原始分段"
            }
          >
            <div className="modal-heading">
              <div>
                <span className="eyebrow">PARAGRAPH ALIGNMENT</span>
                <h2>
                  {structure.kind === "merge"
                    ? "把续段连起来。"
                    : "恢复原始分段。"}
                </h2>
              </div>
              <button
                className="icon-button"
                aria-label="关闭段落调整"
                disabled={saving}
                onClick={() => setStructure(null)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="paragraph-preview">
              <p className="info-note">
                {structure.kind === "merge"
                  ? "合并后会将两段作为完整段落重新翻译。PDF 的位置关联和合并前的译文会保留；确认后不会自动调用翻译服务。"
                  : "拆分后恢复合并前的段落和各自的译文。当前整段译文不会被强行分配到各片段，会保存在结构化 JSON 的段落历史中。"}
              </p>
              {(structure.kind === "merge"
                ? [structure.block, structure.next!]
                : structure.block.source_parts || []
              ).map((b, i) => (
                <div className="paragraph-fragment" key={b.id}>
                  <small>
                    片段 {i + 1}
                    {b.source_locations[0]
                      ? ` · 第 ${b.source_locations[0].page_index + 1} 页`
                      : ""}
                  </small>
                  <Content text={b.original} />
                </div>
              ))}
            </div>
            <div className="modal-footer">
              <span>原文、公式与引用保持关联</span>
              <button
                className="button primary"
                disabled={saving || running}
                onClick={saveStructure}
              >
                {saving && <LoaderCircle size={15} className="spin" />}
                {structure.kind === "merge" ? "确认合并" : "确认拆分"}
              </button>
            </div>
          </div>
        </div>
      )}
      {edit && (
        <div
          className="modal-backdrop"
          onMouseDown={(e) => {
            if (e.target === e.currentTarget) setEdit(null);
          }}
        >
          <div
            className="modal edit-modal"
            role="dialog"
            aria-modal="true"
            aria-label="编辑段落译文"
          >
            <div className="modal-heading">
              <div>
                <span className="eyebrow">TRANSLATION EDITOR</span>
                <h2>让表达更准确一点。</h2>
              </div>
              <button
                className="icon-button"
                onClick={() => setEdit(null)}
                aria-label="关闭"
              >
                <X size={20} />
              </button>
            </div>
            <label className="field-label">英文原文</label>
            <div className="edit-original">
              <Content text={edit.original} />
            </div>
            <label className="field-label" htmlFor="translation-edit">
              中文译文
            </label>
            <textarea
              id="translation-edit"
              className="edit-textarea"
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="输入或修改这段译文…"
            />
            <div className="modal-footer">
              <span>只修改译文，保留原文位置关联</span>
              <button
                className="button primary"
                disabled={saving}
                onClick={save}
              >
                {saving ? (
                  <LoaderCircle size={15} className="spin" />
                ) : (
                  <Save size={15} />
                )}
                保存译文
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
