import { ThemeProvider } from "next-themes";
import { AppHeader } from "@/components/app-header";
import { DataTable } from "@/components/repo-table/data-table";
import { Toaster } from "@/components/ui/toaster";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="flex flex-col h-screen bg-background text-foreground">
        <AppHeader />
        <main className="flex-1 overflow-auto p-4">
          <DataTable />
        </main>
      </div>
      <Toaster />
    </ThemeProvider>
  );
}
export default App;
