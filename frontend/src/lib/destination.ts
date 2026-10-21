import type { PreviewState } from "../types";

type DestinationState = Pick<PreviewState, "inputFolder" | "outputFolder" | "sameFolder">;

/** The one folder every single/batch export writes to. */
export function resolveDestination(state: DestinationState): string {
  return (state.sameFolder ? state.inputFolder : state.outputFolder).trim();
}
