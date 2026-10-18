import { useEffect, useState } from "react";
import { FolderOpen, FolderOutput } from "lucide-react";

interface FolderPickerProps {
  inputFolder: string;
  outputFolder: string;
  sameFolder: boolean;
  onBrowseInput: () => void;
  onBrowseOutput: () => void;
  onToggleSameFolder: (checked: boolean) => void;
  onCommitInput?: (path: string) => void;
  onCommitOutput?: (path: string) => void;
  disabled?: boolean;
}

export function FolderPicker({ inputFolder, outputFolder, sameFolder, onBrowseInput,
  onBrowseOutput, onToggleSameFolder, onCommitInput, onCommitOutput, disabled = false }: FolderPickerProps) {
  const [input, setInput] = useState(inputFolder);
  const [output, setOutput] = useState(outputFolder);
  useEffect(() => setInput(inputFolder), [inputFolder]);
  useEffect(() => setOutput(outputFolder), [outputFolder]);
  return <div className="folder-picker">
    <div className="section-heading"><FolderOpen size={16} /><h2>Source folder</h2></div>
    <p className="muted">Your artwork stays on this computer.</p>
    <label className="sr-only" htmlFor="input-folder">Input folder path</label>
    <input id="input-folder" type="text" value={input} placeholder="Paste a folder path…"
      disabled={disabled} readOnly={!onCommitInput} title={inputFolder}
      onChange={(e) => setInput(e.target.value)}
      onBlur={() => { if (input.trim() !== inputFolder) onCommitInput?.(input.trim()); }}
      onKeyDown={(e) => { if (e.key === "Enter") onCommitInput?.(input.trim()); }} />
    <button type="button" className="button" disabled={disabled} onClick={onBrowseInput}>
      <FolderOpen size={15} />Choose Input Folder
    </button>
    <div className="section-heading destination-heading"><FolderOutput size={16} /><h2>Destination</h2></div>
    <label className="check-row"><input type="checkbox" checked={sameFolder} disabled={disabled}
      onChange={(e) => onToggleSameFolder(e.target.checked)} />Same as input</label>
    {sameFolder ? <p className="path-hint" title={inputFolder}>Saving in the source folder</p> : <>
      <label className="sr-only" htmlFor="output-folder">Output folder path</label>
      <input id="output-folder" type="text" value={output} placeholder="Defaults to source folder"
        disabled={disabled} readOnly={!onCommitOutput} title={outputFolder}
        onChange={(e) => setOutput(e.target.value)}
        onBlur={() => { if (output.trim() !== outputFolder) onCommitOutput?.(output.trim()); }}
        onKeyDown={(e) => { if (e.key === "Enter") onCommitOutput?.(output.trim()); }} />
    </>}
    <button type="button" className="button" disabled={disabled || sameFolder} onClick={onBrowseOutput}>
      <FolderOutput size={15} />Choose Output Folder
    </button>
  </div>;
}
