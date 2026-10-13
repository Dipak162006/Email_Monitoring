import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import DOMPurify from "dompurify";
import { Code, FileText, ExternalLink } from "lucide-react";

export interface EmailBodyViewerProps {
  html?: string | null;
  text?: string | null;
  defaultMode?: "html" | "text";
  className?: string;
  minHeight?: number;
}

/**
 * Remove invisible preheader characters and zero-width spaces commonly found in marketing/notification emails.
 */
function cleanPreheaderChars(text: string): string {
  if (!text) return "";
  // Strip zero-width spaces, joiners, and byte-order marks
  return text.replace(/[\u200B-\u200D\uFEFF\u034F]/g, "").trim();
}

/**
 * Convert plain text with URLs and emails into clean, accessible interactive React elements.
 */
function renderFormattedPlainText(rawText: string) {
  const cleaned = cleanPreheaderChars(rawText);
  if (!cleaned) {
    return <span className="text-slate-400 italic">No message content.</span>;
  }

  const lines = cleaned.split("\n");

  return (
    <div className="font-sans text-sm text-slate-800 leading-relaxed space-y-1.5 selection:bg-indigo-100 selection:text-indigo-900">
      {lines.map((line, idx) => {
        const isQuote = line.trim().startsWith(">");
        const isSigDivider = line.trim() === "--" || line.trim() === "---";

        if (isSigDivider) {
          return (
            <div key={idx} className="pt-3 pb-1 border-b border-slate-200/80 w-16 text-slate-400 text-xs font-mono">
              --
            </div>
          );
        }

        // Match URLs and email addresses
        const tokenRegex = /(https?:\/\/[^\s<>"']+)|([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/gi;
        const parts: React.ReactNode[] = [];
        let lastIndex = 0;
        let match: RegExpExecArray | null;

        while ((match = tokenRegex.exec(line)) !== null) {
          if (match.index > lastIndex) {
            parts.push(line.substring(lastIndex, match.index));
          }

          const matchedToken = match[0];
          if (matchedToken.includes("@") && !matchedToken.startsWith("http")) {
            parts.push(
              <a
                key={`${idx}-${match.index}`}
                href={`mailto:${matchedToken}`}
                className="text-indigo-600 hover:text-indigo-800 hover:underline font-medium"
              >
                {matchedToken}
              </a>
            );
          } else {
            parts.push(
              <a
                key={`${idx}-${match.index}`}
                href={matchedToken}
                target="_blank"
                rel="noopener noreferrer"
                className="text-indigo-600 hover:text-indigo-800 hover:underline font-medium inline-flex items-center gap-0.5"
              >
                <span>{matchedToken}</span>
                <ExternalLink className="h-2.5 w-2.5 inline shrink-0 opacity-70" />
              </a>
            );
          }
          lastIndex = match.index + matchedToken.length;
        }

        if (lastIndex < line.length) {
          parts.push(line.substring(lastIndex));
        }

        if (isQuote) {
          return (
            <div
              key={idx}
              className="pl-3 border-l-2 border-slate-300 text-slate-500 italic my-0.5"
            >
              {parts.length > 0 ? parts : "\u00A0"}
            </div>
          );
        }

        return (
          <div key={idx} className="min-h-[1.25rem] break-words">
            {parts.length > 0 ? parts : "\u00A0"}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Sandboxed, auto-resizing HTML Email Viewer adhering to industry SaaS standards (Gmail/Superhuman/Front).
 * Isolates email stylesheets, prevents CSS pollution, respects tables and inline layouts, and resizes dynamically.
 */
export const EmailBodyViewer: React.FC<EmailBodyViewerProps> = ({
  html,
  text,
  defaultMode = "html",
  className = "",
  minHeight = 160,
}) => {
  const hasHtml = Boolean(html && html.trim().length > 0);
  const hasText = Boolean(text && text.trim().length > 0);

  const [viewMode, setViewMode] = useState<"html" | "text">(() => {
    if (defaultMode === "html" && hasHtml) return "html";
    if (defaultMode === "text" && hasText) return "text";
    return hasHtml ? "html" : "text";
  });

  const [iframeHeight, setIframeHeight] = useState<number>(minHeight);
  const iframeRef = useRef<HTMLIFrameElement>(null);

  // Prepare sanitized, encapsulated HTML document
  const preparedDocHtml = useMemo(() => {
    if (!html) return "";

    // Sanitize with rich email tag & attribute preservation
    const cleanBody = DOMPurify.sanitize(html, {
      ADD_TAGS: [
        "style",
        "table",
        "tbody",
        "thead",
        "tfoot",
        "tr",
        "td",
        "th",
        "div",
        "span",
        "p",
        "a",
        "img",
        "br",
        "hr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "ul",
        "ol",
        "li",
        "b",
        "strong",
        "i",
        "em",
        "u",
        "s",
        "strike",
        "blockquote",
        "pre",
        "code",
        "font",
        "center",
      ],
      ADD_ATTR: [
        "target",
        "rel",
        "style",
        "class",
        "id",
        "cellspacing",
        "cellpadding",
        "border",
        "valign",
        "align",
        "bgcolor",
        "width",
        "height",
        "itemscope",
        "itemtype",
        "itemprop",
        "data-o-mail-quote",
      ],
      ALLOW_DATA_ATTR: true,
      FORCE_BODY: false,
    });

    return `<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base target="_blank">
  <style>
    /* Gmail/Standard Webmail Baseline Styles */
    *, *:before, *:after {
      box-sizing: border-box;
    }
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #202124;
      background-color: #ffffff;
      word-wrap: break-word;
      overflow-wrap: break-word;
      -webkit-text-size-adjust: 100%;
    }
    body {
      padding: 2px 0 16px 0;
    }
    img {
      max-width: 100%;
      height: auto;
    }
    table {
      border-collapse: separate;
    }
    a {
      color: #1a73e8;
      text-decoration: underline;
    }
    a:hover {
      color: #174ea6;
    }
    /* Suppress invisible preheader tracking blocks */
    div[style*="display: none"], div[style*="display:none"],
    span[style*="display: none"], span[style*="display:none"] {
      display: none !important;
      height: 0 !important;
      max-height: 0 !important;
      line-height: 0 !important;
      font-size: 0 !important;
      overflow: hidden !important;
    }
    /* Muted quote / thread styling */
    [data-o-mail-quote="1"], .gmail_quote, .gmail_signature {
      color: #5f6368;
    }
  </style>
</head>
<body>
  ${cleanBody}
</body>
</html>`;
  }, [html]);

  // Dynamic Auto-Resize calculation
  const updateIframeHeight = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe || !iframe.contentWindow || !iframe.contentDocument) return;

    try {
      const doc = iframe.contentDocument;
      const body = doc.body;
      const htmlEl = doc.documentElement;

      if (!body || !htmlEl) return;

      const measuredHeight = Math.max(
        body.scrollHeight,
        body.offsetHeight,
        htmlEl.clientHeight,
        htmlEl.scrollHeight,
        htmlEl.offsetHeight
      );

      if (measuredHeight > 0) {
        setIframeHeight(Math.max(measuredHeight + 20, minHeight));
      }
    } catch {
      // Access errors ignored in constrained environments
    }
  }, [minHeight]);

  useEffect(() => {
    if (viewMode !== "html") return;

    const iframe = iframeRef.current;
    if (!iframe) return;

    const handleLoad = () => {
      updateIframeHeight();

      try {
        const doc = iframe.contentDocument;
        if (!doc) return;

        // Force all links to target _blank and open safely
        doc.querySelectorAll("a").forEach((anchor) => {
          anchor.setAttribute("target", "_blank");
          anchor.setAttribute("rel", "noopener noreferrer");
        });

        // Watch for image loads that change dimensions
        doc.querySelectorAll("img").forEach((img) => {
          img.addEventListener("load", updateIframeHeight);
        });

        // Watch DOM mutations and size changes
        if (typeof ResizeObserver !== "undefined" && doc.body) {
          const resizeObserver = new ResizeObserver(() => {
            updateIframeHeight();
          });
          resizeObserver.observe(doc.body);
        }
      } catch {
        // Ignored
      }
    };

    iframe.addEventListener("load", handleLoad);
    return () => {
      iframe.removeEventListener("load", handleLoad);
    };
  }, [viewMode, preparedDocHtml, updateIframeHeight]);

  return (
    <div className={`space-y-3 ${className}`}>
      {/* Top Format Selector (Only displayed if both HTML and Plain Text are available) */}
      {hasHtml && hasText && (
        <div className="flex items-center justify-end">
          <div className="inline-flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200/60 text-xs">
            <button
              type="button"
              onClick={() => setViewMode("html")}
              className={`px-2.5 py-1 rounded-md font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                viewMode === "html"
                  ? "bg-white text-slate-900 shadow-2xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <Code className="h-3 w-3" />
              <span>Formatted</span>
            </button>
            <button
              type="button"
              onClick={() => setViewMode("text")}
              className={`px-2.5 py-1 rounded-md font-semibold transition-all flex items-center gap-1.5 cursor-pointer ${
                viewMode === "text"
                  ? "bg-white text-slate-900 shadow-2xs font-semibold"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              <FileText className="h-3 w-3" />
              <span>Plain Text</span>
            </button>
          </div>
        </div>
      )}

      {/* Email Body Canvas */}
      <div className="w-full bg-white rounded-xl border border-slate-200/80 p-4 sm:p-6 shadow-2xs transition-all overflow-hidden">
        {viewMode === "html" && hasHtml ? (
          <iframe
            ref={iframeRef}
            title="Email Message Body"
            sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
            srcDoc={preparedDocHtml}
            className="w-full border-0 overflow-hidden block"
            style={{
              height: `${iframeHeight}px`,
              minHeight: `${minHeight}px`,
            }}
          />
        ) : (
          renderFormattedPlainText(text || html || "")
        )}
      </div>
    </div>
  );
};
