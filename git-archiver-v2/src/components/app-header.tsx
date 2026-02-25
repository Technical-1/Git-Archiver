import { useState } from "react";
import { Archive, Settings, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { SettingsDialog } from "@/components/dialogs/settings-dialog";
import { toast } from "@/hooks/use-toast";
import * as commands from "@/lib/commands";

export function AppHeader() {
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [updating, setUpdating] = useState(false);

  const handleUpdateAll = async () => {
    setUpdating(true);
    try {
      await commands.updateAll(false);
      toast({
        title: "Update All",
        description: "All repositories queued for update",
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Update All failed",
        description: String(err),
      });
    } finally {
      setUpdating(false);
    }
  };

  return (
    <>
      <header className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Archive className="h-6 w-6" />
          <h1 className="text-xl font-bold">Git Archiver</h1>
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            disabled={updating}
            onClick={handleUpdateAll}
            aria-label="Update all repositories"
          >
            <RefreshCw className={`h-4 w-4 mr-1 ${updating ? "animate-spin" : ""}`} />
            Update All
          </Button>
          <ThemeToggle />
          <Button
            variant="ghost"
            size="icon"
            aria-label="Settings"
            onClick={() => setSettingsOpen(true)}
          >
            <Settings className="h-5 w-5" />
          </Button>
        </div>
      </header>
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </>
  );
}
