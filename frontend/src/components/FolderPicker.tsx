import { useEffect, useState } from "react";
import { FolderOpen, FolderOutput, Info } from "lucide-react";

interface FolderPickerProps {
  inputFolder: string;
  outputFolder: string;
  sameFolder: boolean;
  onBrowseInput: () => void;
  onBrowseOutput: () => void;
  onToggleSameFolder: (checked: boolean) => void;
  onCommitInput?: (path: string) => void;
  disabled?: boolean;
  forceSeparateOutput?: boolean;
}

export function FolderPicker({ inputFolder, outputFolder, sameFolder, onBrowseInput,
  onBrowseOutput, onToggleSameFolder, onCommitInput, disabled = false,
  forceSeparateOutput = false }: FolderPickerProps) {
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
    <p className="picker-hint"><Info size={14} aria-hidden="true" />The system dialog selects folders only; it won't display individual files. Choose a folder to scan supported assets inside it.</p>
    <div className="section-heading destination-heading"><FolderOutput size={16} /><h2>Destination</h2></div>
    <label className="check-row"><input type="checkbox" checked={sameFolder && !forceSeparateOutput}
      disabled={disabled || forceSeparateOutput}
      onChange={(e) => onToggleSameFolder(e.target.checked)} />Same as input</label>
    {forceSeparateOutput && <p className="path-hint">
      Selected files may come from different folders, so choose a separate output destination.
    </p>}
    {sameFolder && !forceSeparateOutput ? <p className="path-hint" title={inputFolder}>Saving in the source folder</p> : <>
      <label className="sr-only" htmlFor="output-folder">Output folder path</label>
      {/* Export only writes into folders selected through the native picker, so
          typing a path here would produce an UNAUTHORIZED_PATH error. */}
      <input id="output-folder" type="text" value={output} placeholder="Choose an output folder"
        disabled={disabled} readOnly title={outputFolder}
        aria-describedby="output-folder-hint" />
      <p id="output-folder-hint" className="picker-hint">Pick the destination with the button below so PreviewGen is allowed to write there.</p>
    </>}
    <button type="button" className="button" disabled={disabled || (sameFolder && !forceSeparateOutput)} onClick={onBrowseOutput}>
      <FolderOutput size={15} />Choose Output Folder
    </button>
  </div>;
}
