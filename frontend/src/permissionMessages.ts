/** Native file grants cannot be created by typing or pasting a pathname. */
export function describeNativePickerFailure(error: unknown): string {
  const cause = error instanceof Error && error.message.trim()
    ? error.message.trim()
    : "The native file picker is unavailable.";
  return `${cause} Retry with the native folder or Add Files picker. Typing a path does not grant access.`;
}
