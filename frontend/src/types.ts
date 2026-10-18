export type Location = {
  page_index: number;
  bbox: [number, number, number, number];
};
export type Block = {
  id: string;
  type: string;
  original: string;
  translation: string;
  level: number;
  asset: string;
  section_id: string;
  source_locations: Location[];
  source_page: number;
  translatable: boolean;
  status: string;
  revision: number;
};
export type Paper = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  pages: { width: number; height: number; rotation: number }[];
  total: number;
  translated: number;
  block_count: number;
  blocks: Block[];
  pdf_url: string;
  job: { state: string; kind: string; message: string };
};
export type Settings = {
  base_url: string;
  model: string;
  api_key?: string;
  api_key_set: boolean;
  json_mode: boolean;
  batch_chars: number;
  glossary: string;
  parser: "python" | "cloud";
  mineru_python: string;
  mineru_tier: "basic" | "standard" | "advanced" | "flash";
  mineru_token?: string;
  mineru_token_set: boolean;
  library_path: string;
};
export type LibraryEntry = {
  path: string;
  name: string;
  pdf_name: string;
  imported_id?: string;
};
export type Mode = "zh" | "paragraph" | "section" | "en";
export const MODES: { id: Mode; label: string; short: string }[] = [
  { id: "paragraph", label: "逐段中英对照", short: "逐段对照" },
  { id: "zh", label: "仅显示中文", short: "纯中文" },
  { id: "section", label: "逐节中英对照", short: "逐节对照" },
  { id: "en", label: "仅显示英文", short: "英文原文" },
];
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers:
      options?.body instanceof FormData
        ? options.headers
        : { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : `请求失败（${response.status}），请检查输入或稍后重试。`,
    );
  }
  return response.json();
}
export const active = (paper?: Paper | null) =>
  ["running", "stopping"].includes(paper?.job?.state || "");
export const assetUrl = (id: string, asset: string) =>
  `/api/documents/${id}/assets/${asset.split("/").map(encodeURIComponent).join("/")}`;
