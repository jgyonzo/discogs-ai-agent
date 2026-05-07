// US1 wires only the chart artifact. SqlViewer / DataPreviewTable / RunMetadata
// are added by US4 (T046) as siblings inside this component.

import { ArtifactFrame } from "./ArtifactFrame";
import type { AppState } from "../api/types";

export type ResultPanelProps = {
  current: AppState["current"];
};

export function ResultPanel({ current }: ResultPanelProps) {
  return (
    <div className="flex flex-col gap-3">
      <ArtifactFrame artifact={current.artifact} />
    </div>
  );
}
