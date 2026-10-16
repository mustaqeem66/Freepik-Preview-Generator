import { Component, ErrorInfo, ReactNode } from "react";


interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  copied: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    copied: false,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error, copied: false };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("Uncaught React error:", error, errorInfo);
  }

  private handleCopy = async (): Promise<void> => {
    if (!this.state.error) return;
    try {
      await navigator.clipboard.writeText(
        `PreviewGen UI Crash:\nMessage: ${this.state.error.message}\nStack: ${this.state.error.stack}`
      );
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2000);
    } catch {
      // Fallback
    }
  };

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
              maxWidth: "520px",
              padding: "28px",
              borderRadius: "16px",
              background: "#1E293B",
              border: "1px solid #334155",
              boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
            }}
          >
            <h2 style={{ fontSize: "20px", fontWeight: 700, color: "#EF4444", marginBottom: "12px" }}>
              PreviewGen could not load its interface
            </h2>
            <p style={{ fontSize: "14px", color: "#94A3B8", marginBottom: "20px", lineHeight: "1.5" }}>
              An unexpected render error occurred. You can restart the application, copy technical details, or inspect the backend diagnostic logs.
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
                maxHeight: "120px",
              }}
            >
              {this.state.error?.message || "Unknown error"}
            </pre>
            <div style={{ display: "flex", gap: "10px", justifyContent: "center" }}>
              <button
                type="button"
                onClick={() => window.location.reload()}
                style={{
                  padding: "10px 18px",
                  borderRadius: "8px",
                  background: "#6366F1",
                  color: "#FFFFFF",
                  border: "none",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: "13px",
                }}
              >
                Restart PreviewGen
              </button>
              <button
                type="button"
                onClick={this.handleCopy}
                style={{
                  padding: "10px 18px",
                  borderRadius: "8px",
                  background: "#334155",
                  color: "#FFFFFF",
                  border: "none",
                  fontWeight: 600,
                  cursor: "pointer",
                  fontSize: "13px",
                }}
              >
                {this.state.copied ? "Copied Details!" : "Copy Details"}
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
