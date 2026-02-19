import { ThemeProvider } from "next-themes";
import { AppHeader } from "@/components/app-header";
import { Toaster } from "@/components/ui/toaster";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="flex flex-col h-screen bg-background text-foreground">
        <AppHeader />
        <main className="flex-1 overflow-hidden p-4">
          <p className="text-muted-foreground">Ready to build.</p>
        </main>
      </div>
      <Toaster />
    </ThemeProvider>
  );
}
export default App;
