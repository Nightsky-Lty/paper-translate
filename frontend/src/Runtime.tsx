import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { api } from "./types";

const Runtime = createContext<"local" | "server" | null>(null);

export function RuntimeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<"local" | "server" | null>(null);
  useEffect(() => {
    let disposed = false;
    api<{ mode: "local" | "server" }>("/health")
      .then((value) => {
        if (!disposed) setMode(value.mode);
      })
      .catch(() => {});
    return () => {
      disposed = true;
    };
  }, []);
  return <Runtime.Provider value={mode}>{children}</Runtime.Provider>;
}

export function useRuntime() {
  const mode = useContext(Runtime);
  return {
    isServer: mode === "server",
    storageLabel:
      mode === "server" ? "服务器" : mode === "local" ? "本机" : "应用数据目录",
    workspaceLabel:
      mode === "server"
        ? "远端工作空间"
        : mode === "local"
          ? "本地工作空间"
          : "工作空间",
    workspaceEnglish: mode === "server" ? "PRIVATE WORKSPACE" : "WORKSPACE",
  };
}
