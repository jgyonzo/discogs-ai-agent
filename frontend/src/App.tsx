import { Header } from "./components/Header";
import { ChatPanel } from "./components/ChatPanel";
import { QueryInput } from "./components/QueryInput";
import { ResultPanel } from "./components/ResultPanel";
import { LoadingState } from "./components/LoadingState";
import { ErrorBanner } from "./components/ErrorBanner";
import { useAgentQuery } from "./hooks/useAgentQuery";

export function App() {
  const { state, submit } = useAgentQuery();

  return (
    <div className="flex flex-col h-screen">
      <Header />
      <main className="flex-1 grid grid-cols-1 md:grid-cols-[1fr_1fr] overflow-hidden">
        <section
          aria-label="Conversation"
          className="flex flex-col border-r border-slate-200 bg-slate-50"
        >
          <div className="flex-1 overflow-hidden p-3">
            <ChatPanel messages={state.messages} />
          </div>
          <div className="border-t border-slate-200 bg-white p-3 flex flex-col gap-2">
            {state.error && <ErrorBanner error={state.error} />}
            {state.pending && <LoadingState />}
            <QueryInput
              disabled={state.pending}
              onSubmit={(message) => {
                void submit(message);
              }}
            />
          </div>
        </section>
        <section aria-label="Result" className="overflow-y-auto p-4">
          <ResultPanel current={state.current} />
        </section>
      </main>
    </div>
  );
}
