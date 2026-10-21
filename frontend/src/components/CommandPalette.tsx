import { useEffect, useId, useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Command, Search, X } from "lucide-react";
import "./commandPalette.css";

export interface StudioCommand {
  id: string;
  title: string;
  group: string;
  keywords?: string;
  disabled?: boolean;
  action: () => void;
}

export function findCommands(actions: StudioCommand[], query: string): StudioCommand[] {
  const q = query.trim().toLocaleLowerCase();
  return q ? actions.filter((item) =>
    `${item.title} ${item.group} ${item.keywords ?? ""}`.toLocaleLowerCase().includes(q)) : actions;
}

export function CommandPalette({ open, actions, onClose }: {
  open: boolean; actions: StudioCommand[]; onClose: () => void;
}) {
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const searchRef = useRef<HTMLInputElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const priorFocusRef = useRef<HTMLElement | null>(null);
  const titleId = useId();
  const listId = useId();
  const matches = findCommands(actions, query);
  const enabled = matches.filter((item) => !item.disabled);
  const selected = enabled.length ? enabled[Math.min(index, enabled.length - 1)] : undefined;

  useEffect(() => {
    if (!open) return;
    priorFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setQuery("");
    setIndex(0);
    searchRef.current?.focus();
    return () => { priorFocusRef.current?.focus(); };
  }, [open]);

  if (!open) return null;

  const run = (item: StudioCommand) => {
    if (item.disabled) return;
    onClose();
    item.action();
  };
  const onKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault(); event.stopPropagation(); onClose();
    } else if (event.key === "Tab") {
      // Only Search and Close are tab stops; rows are traversed by arrow key.
      event.preventDefault();
      if (document.activeElement === closeRef.current) searchRef.current?.focus();
      else closeRef.current?.focus();
    } else if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!enabled.length) return;
      setIndex((i) => (i + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length);
      searchRef.current?.focus();
    } else if (event.key === "Enter" && selected && document.activeElement !== closeRef.current) {
      event.preventDefault(); run(selected);
    }
  };

  return <div className="command-scrim" onMouseDown={(event) => {
    if (event.target === event.currentTarget) onClose();
  }}>
    <div className="command-panel" role="dialog" aria-modal="true" aria-labelledby={titleId}
      onKeyDown={onKeys} data-testid="command-palette">
      <div className="command-head">
        <h2 id={titleId}><Command size={17} aria-hidden="true"/>Quick actions</h2>
        <button type="button" ref={closeRef} aria-label="Close quick actions" className="command-dismiss"
          onClick={onClose}><X size={16}/></button>
      </div>
      <div className="command-query"><Search size={17} aria-hidden="true"/>
        <input ref={searchRef} type="search" role="combobox" aria-label="Search actions"
          aria-controls={listId} aria-expanded="true" aria-autocomplete="list"
          aria-activedescendant={selected ? `${listId}-${selected.id}` : undefined}
          placeholder="Find an action…" value={query}
          onChange={(event) => { setQuery(event.target.value); setIndex(0); }} />
        <kbd>Esc</kbd>
      </div>
      <div className="command-list" id={listId} role="listbox" aria-label="Commands">
        {!matches.length && <div className="command-no-results" role="status">No matching actions.</div>}
        {matches.map((item) => <button type="button" role="option" tabIndex={-1}
          id={`${listId}-${item.id}`} key={item.id} className="command-row"
          aria-selected={selected?.id === item.id} aria-disabled={item.disabled || undefined}
          disabled={item.disabled} onClick={() => run(item)}
          onMouseEnter={() => { const i = enabled.findIndex((entry) => entry.id === item.id); if (i >= 0) setIndex(i); }}>
          <span>{item.title}</span><small>{item.group}</small>
        </button>)}
      </div>
      <div className="command-legend">
        <span><kbd>↑</kbd><kbd>↓</kbd> Navigate</span><span><kbd>↵</kbd> Run</span>
        <span>Unavailable actions are disabled</span>
      </div>
    </div>
  </div>;
}
