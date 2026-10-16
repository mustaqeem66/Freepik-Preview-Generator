import React, { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Uncaught React error:", error, errorInfo);
  }

  public render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div
          style={{
            height: "100vh",
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px",
            background: "#0F172A",
            color: "#F8FAFC",
            fontFamily: "system-ui, -apple-system, sans-serif",
            textAlign: "center",
          }}
        >
          <div
            style={{
              maxWidth: "500px",
              padding: "28px",
              borderRadius: "16px",
              background: "#1E293B",
              border: "1px solid #334155",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <h2 style={{ fontSize: "20px", fontWeight: 700, color: "#EF4444", marginBottom: "12px" }}>
              Application Render Error
            </h2>
            <p style={{ fontSize: "14px", color: "#94A3B8", marginBottom: "20px", lineHeight: "1.5" }}>
              PreviewGen encountered an unexpected error during UI rendering. Check backend logs for full details.
            </p>
            <pre
              style={{
                textAlign: "left",
                background: "#0F172A",
                padding: "12px",
                borderRadius: "8px",
                fontSize: "12px",
                color: "#FCA5A5",
                overflowX: "auto",
                marginBottom: "20px",
              }}
            >
              {this.state.error?.message || "Unknown error"}
            </pre>
            <button
              type="button"
              onClick={() => window.location.reload()}
              style={{
                padding: "10px 20px",
                borderRadius: "8px",
                background: "#6366F1",
                color: "#FFFFFF",
                border: "none",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Reload Application
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
