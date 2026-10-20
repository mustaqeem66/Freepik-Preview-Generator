import React from "react";
import { AlertCircle, AlertTriangle, Info, X } from "lucide-react";

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

const ICONS = { error: AlertCircle, warning: AlertTriangle, info: Info } as const;
export const ErrorNotice: React.FC<ErrorNoticeProps> = ({ notices, onDismiss }) => {
  if (!notices.length) return null;
  return <div className="notice-stack" role="region" aria-label="Notifications">
    {notices.map((notice) => {
      const Icon = ICONS[notice.type];
      return <div key={notice.id} className={`notice notice-${notice.type}`}
        role={notice.type === "error" ? "alert" : "status"}>
        <Icon size={16} aria-hidden="true"/>
        <div className="notice-body"><strong>{notice.message}</strong>
          {notice.details && <span className="muted">{notice.details}</span>}
        </div>
        <button type="button" className="notice-dismiss" title="Dismiss"
          aria-label={`Dismiss ${notice.message}`} onClick={() => onDismiss(notice.id)}>
          <X size={16}/>
        </button>
      </div>;
    })}
  </div>;
};
