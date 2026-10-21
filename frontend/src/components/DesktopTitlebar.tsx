import { useEffect, useState } from "react";
import { Maximize2, Minus, X } from "lucide-react";
import { ApiBridge } from "../api/bridge";

type DesktopPlatform = "windows" | "linux" | "macos" | "unknown";
type WindowAction = "minimize" | "fullscreen" | "close";

export function DesktopTitlebar() {
  const [platform, setPlatform] = useState<DesktopPlatform | null>(null);
  const [inFlight, setInFlight] = useState(false);

  useEffect(() => {
    let mounted = true;
    const detect = async () => {
      try {
        const api = await ApiBridge.getApi(1500);
        if (!api?.get_window_chrome) return;
        const response = await api.get_window_chrome();
        if (mounted && response.ok && response.value?.enabled) {
          setPlatform(response.value.platform);
        }
      } catch {
        // In a browser dev server or native-titlebar fallback, OS chrome owns
        // minimize, fullscreen and close controls.
      }
    };
    void detect();
    window.addEventListener("pywebviewready", detect);
    return () => {
      mounted = false;
      window.removeEventListener("pywebviewready", detect);
    };
  }, []);

  if (!platform) return null;

  const action = async (kind: WindowAction) => {
    if (inFlight) return;
    setInFlight(true);
    try {
      const api = await ApiBridge.getApi(1000);
      const response = await api?.window_action?.(kind);
      if (!response?.ok) console.warn("Window action unavailable:", response?.error ?? kind);
    } catch (error) {
      console.warn("Window action failed:", error);
    } finally {
      setInFlight(false);
    }
  };

  const controls = (includeClose: boolean) => <>
    <button className="titlebar-control" type="button" title="Minimize window"
      aria-label="Minimize window" disabled={inFlight}
      onClick={() => void action("minimize")}><Minus size={14} aria-hidden="true"/></button>
    <button className="titlebar-control" type="button" title="Toggle fullscreen"
      aria-label="Toggle fullscreen" disabled={inFlight}
      onClick={() => void action("fullscreen")}><Maximize2 size={13} aria-hidden="true"/></button>
    {includeClose && <button className="titlebar-control titlebar-close" type="button"
      title="Close application" aria-label="Close application" disabled={inFlight}
      onClick={() => void action("close")}><X size={15} aria-hidden="true"/></button>}
  </>;

  return <div className={`desktop-titlebar desktop-titlebar--${platform}`}
    role="toolbar" aria-label="Desktop window controls" data-testid="desktop-titlebar">
    {platform !== "macos" && <div className="titlebar-leading">{controls(false)}</div>}
    <div className="pywebview-drag-region titlebar-drag" aria-hidden="true">
      <span>PreviewGen</span>
    </div>
    {platform === "macos"
      ? <div className="titlebar-trailing">{controls(true)}</div>
      : <div className="titlebar-trailing">
          <button className="titlebar-control titlebar-close" type="button"
            title="Close application" aria-label="Close application" disabled={inFlight}
            onClick={() => void action("close")}><X size={15} aria-hidden="true"/></button>
        </div>}
  </div>;
}
