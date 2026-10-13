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
 * Isolates email stylesheets, prevents CSS pollution, eliminates inner scrollbars, and resizes dynamically.
 */
export const EmailBodyViewer: React.FC<EmailBodyViewerProps> = ({
  html,
  text,
  defaultMode = "html",
  className = "",
  minHeight = 200,
}) => {
  const hasHtml = Boolean(html && html.trim().length > 0);
  const hasText = Boolean(text && text.trim().length > 0);

  const [viewMode, setViewMode] = useState<"html" | "text">(() => {
    if (defaultMode === "html" && hasHtml) return "html";
    if (defaultMode === "text" && hasText) return "text";
    return hasHtml ? "html" : "text";
  });

  const [iframeHeight, setIframeHeight] = useState<number>(minHeight);
  const [isReady, setIsReady] = useState<boolean>(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const resizeObserverRef = useRef<ResizeObserver | null>(null);
  const mutationObserverRef = useRef<MutationObserver | null>(null);

  // Prepare sanitized, encapsulated HTML document preserving original <style> and media queries
  const preparedDocHtml = useMemo(() => {
    if (!html) return "";

    // Sanitize with whole-document preservation so <head> and <style> tags (media queries, responsive hiding) are preserved
    const sanitized = DOMPurify.sanitize(html, {
      WHOLE_DOCUMENT: true,
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
        "meta",
        "title",
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
        "content",
        "http-equiv",
        "name",
      ],
      ALLOW_DATA_ATTR: true,
    });

    const baselineHead = `
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <base target="_blank">
  <style id="pulsemail-baseline-reset">
    /* Gmail/Standard Webmail Baseline Styles */
    *, *:before, *:after {
      box-sizing: border-box;
    }
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: auto !important;
      min-height: 0 !important;
      overflow-y: hidden !important;
      overflow-x: auto;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      font-size: 14px;
      line-height: 1.5;
      color: #202124;
      background-color: #ffffff;
      word-wrap: break-word;
      overflow-wrap: break-word;
      -webkit-text-size-adjust: 100%;
    }
    /* Suppress scrollbars inside the iframe */
    ::-webkit-scrollbar {
      width: 0px;
      height: 4px;
      background: transparent;
    }
    ::-webkit-scrollbar-thumb {
      background: #cbd5e1;
      border-radius: 4px;
    }
    body {
      padding: 4px 0 16px 0;
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
    span[style*="display: none"], span[style*="display:none"],
    div[style*="display: none !important"], span[style*="display: none !important"] {
      display: none !important;
      height: 0 !important;
      max-height: 0 !important;
      line-height: 0 !important;
      font-size: 0 !important;
      overflow: hidden !important;
      visibility: hidden !important;
      mso-hide: all !important;
    }
    /* Muted quote / thread styling */
    [data-o-mail-quote="1"], .gmail_quote, .gmail_signature {
      color: #5f6368;
    }
  </style>`;

    let finalDoc = sanitized;
    if (finalDoc.includes("<head>")) {
      finalDoc = finalDoc.replace("<head>", `<head>${baselineHead}`);
    } else if (/<head[^>]*>/i.test(finalDoc)) {
      finalDoc = finalDoc.replace(/<head[^>]*>/i, (m) => `${m}${baselineHead}`);
    } else if (finalDoc.includes("<html>")) {
      finalDoc = finalDoc.replace("<html>", `<html><head>${baselineHead}</head>`);
    } else {
      finalDoc = `<!DOCTYPE html><html><head>${baselineHead}</head><body>${finalDoc}</body></html>`;
    }

    if (!finalDoc.toLowerCase().startsWith("<!doctype")) {
      finalDoc = `<!DOCTYPE html>\n${finalDoc}`;
    }

    return finalDoc;
  }, [html]);

  // Reset ready state on new email HTML content
  useEffect(() => {
    setIsReady(false);
    setIframeHeight(minHeight);
  }, [preparedDocHtml, minHeight]);

  // Dynamic Auto-Resize calculation with child bounding box & scroll height
  const measureAndSetHeight = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    try {
      const doc = iframe.contentDocument;
      if (!doc) return;
      const body = doc.body;
      const htmlEl = doc.documentElement;
      if (!body || !htmlEl) return;

      // 1. Calculate bottom coordinate of all top-level children
      let maxChildBottom = 0;
      try {
        const children = body.children;
        for (let i = 0; i < children.length; i++) {
          const child = children[i] as HTMLElement;
          if (child && typeof child.getBoundingClientRect === "function") {
            const rect = child.getBoundingClientRect();
            if (rect.bottom > maxChildBottom) {
              maxChildBottom = rect.bottom;
            }
          }
        }
      } catch {
        // Fallback
      }

      // 2. Comprehensive measurement across scrollHeight, offsetHeight, and child bounds
      const measured = Math.ceil(
        Math.max(
          body.scrollHeight || 0,
          body.offsetHeight || 0,
          htmlEl.scrollHeight || 0,
          htmlEl.offsetHeight || 0,
          maxChildBottom
        )
      );

      if (measured > 0) {
        // Add a 16px bottom padding cushion to ensure no subpixel cutoffs
        const targetHeight = Math.max(measured + 16, minHeight);
        setIframeHeight((prev) => {
          if (Math.abs(prev - targetHeight) > 2) {
            return targetHeight;
          }
          return prev;
        });
        setIsReady(true);
      }
    } catch {
      // In restricted environments, reveal content safely
      setIsReady(true);
    }
  }, [minHeight]);

  // Setup listeners and observers inside the iframe document
  const setupIframeDocument = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe) return;

    try {
      const doc = iframe.contentDocument;
      if (!doc) {
        setIsReady(true);
        return;
      }

      // Ensure all links open securely in new tabs
      doc.querySelectorAll("a").forEach((anchor) => {
        anchor.setAttribute("target", "_blank");
        anchor.setAttribute("rel", "noopener noreferrer");
      });

      // Immediate measurement
      measureAndSetHeight();

      // Clean up previous observers
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      if (mutationObserverRef.current) {
        mutationObserverRef.current.disconnect();
        mutationObserverRef.current = null;
      }

      // Observe element resizing (body & documentElement)
      if (typeof ResizeObserver !== "undefined" && doc.body) {
        const ro = new ResizeObserver(() => {
          measureAndSetHeight();
        });
        ro.observe(doc.body);
        if (doc.documentElement) {
          ro.observe(doc.documentElement);
        }
        resizeObserverRef.current = ro;
      }

      // Observe DOM mutations
      if (typeof MutationObserver !== "undefined" && doc.body) {
        const mo = new MutationObserver(() => {
          measureAndSetHeight();
        });
        mo.observe(doc.body, { childList: true, subtree: true, attributes: true });
        mutationObserverRef.current = mo;
      }

      // Watch all images for load/error events to re-measure on image completion
      doc.querySelectorAll("img").forEach((img) => {
        if (!img.complete) {
          img.addEventListener("load", measureAndSetHeight, { once: true });
          img.addEventListener("error", measureAndSetHeight, { once: true });
        }
      });

      // Trigger on font loading resolution
      if (doc.fonts && doc.fonts.ready) {
        doc.fonts.ready.then(measureAndSetHeight).catch(() => {});
      }

      // Staggered interval passes for delayed layouts / CSS reflows / remote image loads
      const timers = [40, 120, 250, 500, 1000, 2000].map((ms) =>
        setTimeout(measureAndSetHeight, ms)
      );

      return () => {
        timers.forEach(clearTimeout);
      };
    } catch {
      setIsReady(true);
    }
  }, [measureAndSetHeight]);

  useEffect(() => {
    if (viewMode !== "html") return;

    const iframe = iframeRef.current;
    if (!iframe) return;

    // If the document is already parsed and ready, run setup immediately
    if (
      iframe.contentDocument &&
      (iframe.contentDocument.readyState === "complete" ||
        iframe.contentDocument.readyState === "interactive")
    ) {
      setupIframeDocument();
    }

    return () => {
      if (resizeObserverRef.current) {
        resizeObserverRef.current.disconnect();
        resizeObserverRef.current = null;
      }
      if (mutationObserverRef.current) {
        mutationObserverRef.current.disconnect();
        mutationObserverRef.current = null;
      }
    };
  }, [viewMode, preparedDocHtml, setupIframeDocument]);

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
      <div className="w-full bg-white rounded-xl border border-slate-200/80 p-4 sm:p-6 shadow-2xs transition-all overflow-x-auto overflow-y-visible">
        {viewMode === "html" && hasHtml ? (
          <div className="relative w-full" style={{ minHeight: `${minHeight}px` }}>
            {/* Sleek Skeleton Loading state while iframe calculates initial layout */}
            {!isReady && (
              <div
                className="absolute inset-0 bg-white z-10 space-y-4 animate-pulse py-2 pointer-events-none"
                aria-hidden="true"
              >
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 bg-slate-100 rounded-full shrink-0" />
                  <div className="space-y-1.5 flex-1">
                    <div className="h-3.5 bg-slate-200/70 rounded w-1/4" />
                    <div className="h-2.5 bg-slate-100 rounded w-1/3" />
                  </div>
                </div>
                <div className="space-y-2.5 pt-1">
                  <div className="h-3 bg-slate-200/60 rounded w-3/4" />
                  <div className="h-3 bg-slate-100 rounded w-full" />
                  <div className="h-3 bg-slate-100 rounded w-5/6" />
                  <div className="h-3 bg-slate-100 rounded w-2/3" />
                </div>
                <div className="pt-2">
                  <div className="h-28 bg-slate-100/70 rounded-xl w-full" />
                </div>
              </div>
            )}

            {/* Sandboxed Iframe (Strictly no inner vertical scrollbar, smoothly synced height) */}
            <iframe
              ref={iframeRef}
              title="Email Message Body"
              scrolling="no"
              sandbox="allow-popups allow-popups-to-escape-sandbox allow-same-origin"
              srcDoc={preparedDocHtml}
              onLoad={setupIframeDocument}
              className={`w-full border-0 block transition-opacity duration-200 ${
                isReady ? "opacity-100" : "opacity-0"
              }`}
              style={{
                height: `${iframeHeight}px`,
                minHeight: `${minHeight}px`,
                transition: "height 0.15s ease-out, opacity 0.2s ease-in-out",
              }}
            />
          </div>
        ) : (
          renderFormattedPlainText(text || html || "")
        )}
      </div>
    </div>
  );
};
