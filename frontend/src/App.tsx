import { Hero } from "./components/Hero";
import { GreetingPanel } from "./components/GreetingPanel";
import { AgentPanel } from "./components/AgentPanel";
import { IVRPromptPanel } from "./components/IVRPromptPanel";
// CorrectionPanel removed — corrections are now managed as defaults in backend

function App() {
  return (
    <main className="max-w-6xl mx-auto py-10 px-5 lg:px-0 space-y-8">
      <Hero />
      <GreetingPanel />
      <IVRPromptPanel />
      <AgentPanel />
      <footer className="text-center text-xs text-onyx/50 py-6">
        Crafted for Jadau · Inspired by heritage ateliers · {new Date().getFullYear()}
      </footer>
    </main>
  );
}

export default App;
