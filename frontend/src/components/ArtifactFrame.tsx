import { toAbsoluteArtifactUrl } from "../api/client";
import type { ChartArtifact } from "../api/types";

export type ArtifactFrameProps = {
  artifact: ChartArtifact | null;
};

const EMPTY_COPY =
  "No chart yet. Ask a question or run one of the suggested questions.";

export function ArtifactFrame({ artifact }: ArtifactFrameProps) {
  if (!artifact || artifact.type !== "plotly_html") {
    return (
      <div className="flex items-center justify-center h-[400px] rounded-md border border-dashed border-slate-300 bg-white text-sm text-slate-500 px-6 text-center">
        {EMPTY_COPY}
      </div>
    );
  }
  return (
    <iframe
      src={toAbsoluteArtifactUrl(artifact.url)}
      sandbox="allow-scripts"
      title="Generated chart"
      className="w-full h-[600px] rounded-md border border-slate-200 bg-white"
    />
  );
}
