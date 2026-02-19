import { ThemeProvider } from "next-themes";

function App() {
  return (
    <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
      <div className="min-h-screen bg-background text-foreground">
        <h1 className="text-2xl font-bold p-4">Git Archiver</h1>
        <p className="px-4 text-muted-foreground">Ready to build.</p>
      </div>
    </ThemeProvider>
  );
}
export default App;
