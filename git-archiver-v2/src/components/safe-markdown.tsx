import ReactMarkdown from "react-markdown";
import { openUrl } from "@tauri-apps/plugin-opener";

interface SafeMarkdownProps {
  children: string;
}

/**
 * Renders Markdown with link-scheme allowlisting. Only http(s) hrefs become
 * clickable anchors; other schemes (javascript:, data:, file:, etc.) render
 * as plain text. Clicks are routed through the Tauri opener plugin so the
 * URL is opened in the user's external browser, not the WebView.
 *
 * react-markdown v10 strips raw HTML by default (so classic XSS is mitigated),
 * but Markdown `[click](javascript:...)` links produced a keyboard-activatable
 * `<a href="javascript:...">` anchor in the DOM. This wrapper closes that gap.
 */
export function SafeMarkdown({ children }: SafeMarkdownProps) {
  return (
    <ReactMarkdown
      components={{
        a: ({ href, children }) => {
          const safe = typeof href === "string" && /^https?:\/\//i.test(href);
          if (!safe) {
            return <span>{children}</span>;
          }
          return (
            <a
              href={href}
              onClick={(e) => {
                e.preventDefault();
                openUrl(href).catch(() => {
                  /* best-effort; user-visible failure not warranted */
                });
              }}
            >
              {children}
            </a>
          );
        },
      }}
    >
      {children}
    </ReactMarkdown>
  );
}
