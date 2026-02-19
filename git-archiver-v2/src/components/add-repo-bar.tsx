import { useState } from "react";
import { Plus } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useRepoStore } from "@/stores/repo-store";
import { isValidGithubUrl } from "@/lib/utils";
import { toast } from "@/hooks/use-toast";

export function AddRepoBar() {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const addRepo = useRepoStore((s) => s.addRepo);

  const handleSubmit = async () => {
    const trimmed = url.trim();
    if (!trimmed) return;

    if (!isValidGithubUrl(trimmed)) {
      toast({
        variant: "destructive",
        title: "Invalid URL",
        description:
          "Please enter a valid GitHub repository URL (e.g., https://github.com/owner/repo)",
      });
      return;
    }

    setLoading(true);
    try {
      await addRepo(trimmed);
      toast({
        title: "Repository added",
        description: `Successfully added ${trimmed}`,
      });
      setUrl("");
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to add repository",
        description: String(err),
      });
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="flex items-center gap-2">
      <Input
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="https://github.com/owner/repo"
        disabled={loading}
        className="flex-1"
      />
      <Button onClick={handleSubmit} disabled={loading || !url.trim()} size="sm">
        <Plus className="mr-1 h-4 w-4" />
        Add
      </Button>
    </div>
  );
}
