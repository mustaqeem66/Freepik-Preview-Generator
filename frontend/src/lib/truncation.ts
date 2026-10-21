const TRUNCATION_LABELS: Record<string, string> = {
  maximum_files: "file limit reached",
  maximum_directories: "folder limit reached",
  maximum_depth: "folder depth limit reached",
  maximum_time: "time limit reached",
  maximum_archive_members: "archive entry limit reached",
  permission_denied: "some folders could not be read",
};

/** Human labels for backend truncation codes; unknown codes stay readable. */
export function formatTruncationReasons(
  reasons: readonly string[],
  fallback = "safety limit"
): string {
  const labels = reasons.map(
    (reason) => TRUNCATION_LABELS[reason] ?? reason.replaceAll("_", " ")
  );
  return labels.length > 0 ? labels.join("; ") : fallback;
}
