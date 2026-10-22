import { useEffect, useState } from "react";
import { FolderOpen, FolderOutput } from "lucide-react";

interface FolderPickerProps {
  inputFolder: string;
  outputFolder: string;
  sameFolder: boolean;
  onBrowseInput: () => void;
  onBrowseFiles?: () => void;
  onBrowseOutput: () => void;
  onToggleSameFolder: (checked: boolean) => void;
  disabled?: boolean;
  forceSeparateOutput?: boolean;
}

export function FolderPicker({ inputFolder, outputFolder, sameFolder, onBrowseInput,
  onBrowseFiles, onBrowseOutput, onToggleSameFolder, disabled = false,
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
      disabled={disabled} readOnly title="Use Choose Folder to authorize a source directory"
      />
    <div className="source-choice-actions" role="group" aria-label="Choose artwork source">
      <button type="button" className="button source-folder-button" disabled={disabled} onClick={onBrowseInput}>
        <FolderOpen size={15} aria-hidden="true" />Choose Folder
      </button>
      {onBrowseFiles && <button type="button" className="button source-files-button" disabled={disabled}
        onClick={onBrowseFiles}>Browse Files…</button>}
    </div>
    <div className="section-heading destination-heading"><FolderOutput size={16} /><h2>Destination</h2></div>
    <label className="check-row"><input type="checkbox" checked={sameFolder && !forceSeparateOutput}
      disabled={disabled || forceSeparateOutput}
      onChange={(e) => onToggleSameFolder(e.target.checked)} />Same as input</label>
    {forceSeparateOutput && <p className="path-hint">
      Selected files may come from different folders, so choose a separate output destination.
    </p>}
    {sameFolder && !forceSeparateOutput ? <p className="path-hint" title={inputFolder}>Saving in the source folder</p> : <>
      <input id="output-folder" type="text" value={output} placeholder="Choose an output folder"
        disabled={disabled} readOnly title={outputFolder}
        aria-label="Output folder path" />
    </>}
    <button type="button" className="button" disabled={disabled || (sameFolder && !forceSeparateOutput)} onClick={onBrowseOutput}>
      <FolderOutput size={15} />Choose Output Folder
    </button>
  </div>;
}
