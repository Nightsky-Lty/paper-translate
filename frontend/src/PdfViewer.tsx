import { useEffect, useRef, useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Minus,
  Plus,
  ScanLine,
  LoaderCircle,
  ExternalLink,
} from "lucide-react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
  type RenderTask,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import type { Paper, Block } from "./types";

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfViewer({
  paper,
  selected,
  onSelect,
  page,
  setPage,
}: {
  paper: Paper;
  selected: string;
  onSelect: (b: Block) => void;
  page: number;
  setPage: (page: number) => void;
}) {
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [width, setWidth] = useState(600);
  const [zoom, setZoom] = useState(1);
  const [ratio, setRatio] = useState(1.414);
  const container = useRef<HTMLDivElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [pageInput, setPageInput] = useState("1");

  useEffect(() => {
    setPdf(null);
    setError("");
    setLoading(true);
    const task = getDocument({ url: paper.pdf_url, isEvalSupported: false });
    let disposed = false;
    task.promise
      .then((doc) => {
        if (!disposed) setPdf(doc);
      })
      .catch(() => {
        if (!disposed) {
          setError("PDF 加载失败，请重新打开论文。");
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
      void task.destroy();
    };
  }, [paper.id, paper.pdf_url]);

  useEffect(() => {
    const element = container.current;
    if (!element) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(180, entries[0].contentRect.width - 44)),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let disposed = false;
    let task: RenderTask | undefined;
    setLoading(true);
    pdf
      .getPage(page + 1)
      .then(async (source) => {
        if (disposed || !canvas.current) return;
        const initial = source.getViewport({ scale: 1 });
        setRatio(initial.height / initial.width);
        const dpr = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = source.getViewport({
          scale: ((width * zoom) / initial.width) * dpr,
        });
        const element = canvas.current;
        element.width = viewport.width;
        element.height = viewport.height;
        task = source.render({
          canvasContext: element.getContext("2d")!,
          viewport,
        });
        await task.promise;
        if (!disposed) {
          setLoading(false);
          setError("");
        }
      })
      .catch((err) => {
        if (!disposed && err.name !== "RenderingCancelledException") {
          setError("页面渲染失败。可尝试在新窗口打开原 PDF。");
          setLoading(false);
        }
      });
    return () => {
      disposed = true;
      task?.cancel();
    };
  }, [pdf, page, width, zoom]);

  useEffect(() => {
    setPageInput(String(page + 1));
  }, [page]);
  useEffect(() => {
    const block = paper.blocks.find((b) => b.id === selected);
    const location = block?.source_locations.find(
      (loc) => loc.page_index === page,
    );
    if (location && scroll.current) {
      const top = location.bbox[1] * width * zoom * ratio;
      scroll.current.scrollTo({
        top: Math.max(0, top - 110),
        behavior: "smooth",
      });
    }
  }, [selected, page, ratio, width, zoom]);

  const pageCount = pdf?.numPages || paper.pages.length;
  const changePage = (value: number) => {
    if (Number.isFinite(value))
      setPage(Math.max(0, Math.min(pageCount - 1, Math.round(value))));
    scroll.current?.scrollTo({ top: 0 });
  };
  return (
    <section className="pdf-panel" ref={container} aria-label="原 PDF 对照">
      <div className="pane-header">
        <span>
          <ScanLine size={15} /> 原文 PDF
        </span>
        <a
          className="icon-button"
          href={paper.pdf_url}
          target="_blank"
          rel="noreferrer"
          title="在新窗口打开 PDF"
        >
          <ExternalLink size={15} />
        </a>
      </div>
      <div className="pdf-scroll" ref={scroll}>
        {error && <div className="inline-error">{error}</div>}
        <div
          className="pdf-sheet"
          style={{ width: width * zoom, height: width * zoom * ratio }}
        >
          <canvas ref={canvas} style={{ width: "100%", height: "100%" }} />
          <div className="pdf-annotations">
            {paper.blocks.flatMap((block) =>
              block.source_locations
                .filter((loc) => loc.page_index === page)
                .map((loc, i) => (
                  <button
                    key={block.id + i}
                    aria-label={`定位译文：${block.original.slice(0, 40) || "图表"}`}
                    className={`pdf-region ${selected === block.id ? "selected" : ""}`}
                    style={{
                      left: loc.bbox[0] * 100 + "%",
                      top: loc.bbox[1] * 100 + "%",
                      width: (loc.bbox[2] - loc.bbox[0]) * 100 + "%",
                      height: (loc.bbox[3] - loc.bbox[1]) * 100 + "%",
                    }}
                    onClick={() => onSelect(block)}
                    title={block.original.slice(0, 120) || "图表"}
                  />
                )),
            )}
          </div>
          {loading && (
            <div className="pdf-loading">
              <LoaderCircle size={22} className="spin" />
            </div>
          )}
        </div>
        <p className="pdf-hint">点击原文区域，定位对应译文</p>
      </div>
      <div className="pdf-controls">
        <div>
          <button
            className="icon-button"
            disabled={page <= 0}
            onClick={() => changePage(page - 1)}
            aria-label="上一页"
          >
            <ChevronLeft size={16} />
          </button>
          <input
            aria-label="PDF 页码"
            value={pageInput}
            onChange={(e) => setPageInput(e.target.value)}
            onBlur={() => {
              changePage(Number(pageInput) - 1);
              setPageInput(String(page + 1));
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
            }}
          />
          <span>/ {pageCount || "—"}</span>
          <button
            className="icon-button"
            disabled={page >= pageCount - 1}
            onClick={() => changePage(page + 1)}
            aria-label="下一页"
          >
            <ChevronRight size={16} />
          </button>
        </div>
        <div>
          <button
            className="icon-button"
            disabled={zoom <= 0.65}
            onClick={() => setZoom((z) => Math.max(0.6, z - 0.15))}
            aria-label="缩小"
          >
            <Minus size={15} />
          </button>
          <button
            className="zoom-label"
            onClick={() => setZoom(1)}
            title="恢复适合宽度"
          >
            {Math.round(zoom * 100)}%
          </button>
          <button
            className="icon-button"
            disabled={zoom >= 2}
            onClick={() => setZoom((z) => Math.min(2, z + 0.15))}
            aria-label="放大"
          >
            <Plus size={15} />
          </button>
        </div>
      </div>
    </section>
  );
}
