import React from "react";
import { AlertCircle, X } from "lucide-react";

export interface NoticeMessage {
  id: string;
  type: "error" | "warning" | "info";
  message: string;
  details?: string;
}

interface ErrorNoticeProps {
  notices: NoticeMessage[];
  onDismiss: (id: string) => void;
}

export const ErrorNotice: React.FC<ErrorNoticeProps> = ({ notices, onDismiss }) => {
  if (notices.length === 0) return null;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        marginBottom: "12px",
      }}
    >
      {notices.map((n) => {
        const isErr = n.type === "error";
        const isWarn = n.type === "warning";
        const bg = isErr
          ? "rgba(239, 68, 68, 0.15)"
          : isWarn
          ? "rgba(245, 158, 11, 0.15)"
          : "rgba(99, 102, 241, 0.15)";
        const border = isErr ? "#EF4444" : isWarn ? "#F59E0B" : "#6366F1";
        const color = isErr ? "#EF4444" : isWarn ? "#F59E0B" : "#6366F1";

        return (
          <div
            key={n.id}
            role={isErr ? "alert" : "status"}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "10px 14px",
              background: bg,
              border: `1px solid ${border}`,
              borderRadius: "8px",
              fontSize: "12px",
              color: "var(--text-main)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <AlertCircle size={16} color={color} />
              <div>
                <span style={{ fontWeight: 600 }}>{n.message}</span>
                {n.details && (
                  <span style={{ color: "var(--text-sec)", marginLeft: "6px" }}>
                    — {n.details}
                  </span>
                )}
              </div>
            </div>
            <button
              type="button"
              aria-label={`Dismiss ${n.message}`}
              onClick={() => onDismiss(n.id)}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: "4px",
                display: "flex",
                alignItems: "center",
                color: "var(--text-sec)",
              }}
              title="Dismiss"
            >
              <X size={14} />
            </button>
          </div>
        );
      })}
    </div>
  );
};
