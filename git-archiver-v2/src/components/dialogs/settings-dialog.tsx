import { useState, useEffect } from "react";
import { Eye, EyeOff } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { useSettingsStore } from "@/stores/settings-store";
import { toast } from "@/hooks/use-toast";
import * as commands from "@/lib/commands";
import type { RateLimitInfo } from "@/lib/types";

interface SettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: SettingsDialogProps) {
  const { settings, saveSettings } = useSettingsStore();

  // Local form state
  const [token, setToken] = useState("");
  const [showToken, setShowToken] = useState(false);
  const [maxConcurrent, setMaxConcurrent] = useState(4);
  const [autoUpdateEnabled, setAutoUpdateEnabled] = useState(false);
  const [autoUpdateInterval, setAutoUpdateInterval] = useState(60);
  const [rateLimit, setRateLimit] = useState<RateLimitInfo | null>(null);
  const [testingToken, setTestingToken] = useState(false);
  const [saving, setSaving] = useState(false);

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      setToken("");
      setShowToken(false);
      setMaxConcurrent(settings.max_concurrent_tasks);
      setAutoUpdateEnabled(settings.auto_check_interval_minutes !== null);
      setAutoUpdateInterval(settings.auto_check_interval_minutes ?? 60);
      setRateLimit(null);
    }
  }, [open, settings]);

  const handleTestToken = async () => {
    setTestingToken(true);
    try {
      const info = await commands.checkRateLimit();
      setRateLimit(info);
      toast({
        title: "Token valid",
        description: `Rate limit: ${info.remaining}/${info.limit}`,
      });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Token test failed",
        description: String(err),
      });
      setRateLimit(null);
    } finally {
      setTestingToken(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const updatedSettings = {
        ...settings,
        max_concurrent_tasks: maxConcurrent,
        auto_check_interval_minutes: autoUpdateEnabled
          ? autoUpdateInterval
          : null,
      };
      await saveSettings(updatedSettings, token || undefined);
      toast({
        title: "Settings saved",
        description: "Your settings have been updated",
      });
      onOpenChange(false);
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to save settings",
        description: String(err),
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Settings</DialogTitle>
          <DialogDescription>
            Configure Git Archiver preferences
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* GitHub Token */}
          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="github-token">
              GitHub Token
            </label>
            <div className="flex items-center gap-2">
              <div className="relative flex-1">
                <Input
                  id="github-token"
                  type={showToken ? "text" : "password"}
                  placeholder="ghp_xxxxxxxxxxxx"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="absolute right-0 top-0 h-full px-3"
                  onClick={() => setShowToken(!showToken)}
                  aria-label={showToken ? "Hide token" : "Show token"}
                >
                  {showToken ? (
                    <EyeOff className="h-4 w-4" />
                  ) : (
                    <Eye className="h-4 w-4" />
                  )}
                </Button>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleTestToken}
                disabled={testingToken}
              >
                {testingToken ? "Testing..." : "Test"}
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              Leave blank to keep the existing token unchanged.
            </p>
            {rateLimit && (
              <p className="text-xs text-muted-foreground" data-testid="rate-limit-display">
                Rate limit: {rateLimit.remaining}/{rateLimit.limit} remaining
              </p>
            )}
          </div>

          {/* Max Parallel Operations */}
          <div className="space-y-2">
            <label className="text-sm font-medium">
              Max Parallel Operations: {maxConcurrent}
            </label>
            <Slider
              value={[maxConcurrent]}
              onValueChange={(v) => setMaxConcurrent(v[0])}
              min={1}
              max={16}
              step={1}
              data-testid="concurrency-slider"
            />
            <p className="text-xs text-muted-foreground">
              Number of repos to process simultaneously (1-16)
            </p>
          </div>

          {/* Auto-update */}
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                id="auto-update"
                checked={autoUpdateEnabled}
                onChange={(e) => setAutoUpdateEnabled(e.target.checked)}
                className="h-4 w-4 rounded border-input"
              />
              <label htmlFor="auto-update" className="text-sm font-medium">
                Enable auto-update
              </label>
            </div>
            {autoUpdateEnabled && (
              <div className="flex items-center gap-2 ml-6">
                <label htmlFor="interval" className="text-sm text-muted-foreground">
                  Check every
                </label>
                <Input
                  id="interval"
                  type="number"
                  min={1}
                  max={1440}
                  value={autoUpdateInterval}
                  onChange={(e) =>
                    setAutoUpdateInterval(
                      Math.max(1, Math.min(1440, Number(e.target.value))),
                    )
                  }
                  className="w-20"
                />
                <span className="text-sm text-muted-foreground">minutes</span>
              </div>
            )}
          </div>

          {/* Data Path */}
          <div className="space-y-2">
            <label className="text-sm font-medium">Data Path</label>
            <Input value={settings.data_dir} disabled className="bg-muted" />
            <p className="text-xs text-muted-foreground">
              Read-only. Change via configuration file.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
