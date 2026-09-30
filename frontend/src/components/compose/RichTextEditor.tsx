import React, { useRef, useEffect, useState, useCallback, useImperativeHandle } from "react";
import {
  Bold,
  Italic,
  Underline,
  Strikethrough,
  List,
  ListOrdered,
  Quote,
  Code,
  AlignLeft,
  AlignCenter,
  AlignRight,
  Link as LinkIcon,
  ChevronDown,
} from "lucide-react";

export interface RichTextEditorRef {
  insertHtml: (html: string) => void;
  insertText: (text: string) => void;
  focus: () => void;
  getHtml: () => string;
  getText: () => string;
  setHtml: (html: string) => void;
}

export interface RichTextEditorProps {
  initialHtml?: string;
  onChange: (html: string, text: string) => void;
  placeholder?: string;
  minHeightClass?: string;
}

interface ActiveStates {
  bold: boolean;
  italic: boolean;
  underline: boolean;
  strikeThrough: boolean;
  unorderedList: boolean;
  orderedList: boolean;
  blockquote: boolean;
  code: boolean;
  align: "left" | "center" | "right";
  style: string;
  font: string;
}

interface FontOption {
  label: string;
  value: string; // Single font family face for document.execCommand
  style: string; // CSS fallback stack for display styling
}

const FONT_OPTIONS: FontOption[] = [
  { label: "Sans Serif", value: "sans-serif", style: "ui-sans-serif, system-ui, sans-serif" },
  { label: "Serif", value: "serif", style: "Georgia, Cambria, serif" },
  { label: "Monospace", value: "monospace", style: "ui-monospace, monospace" },
  { label: "Arial", value: "Arial", style: "Arial, Helvetica, sans-serif" },
  { label: "Georgia", value: "Georgia", style: "Georgia, serif" },
  { label: "Verdana", value: "Verdana", style: "Verdana, Geneva, sans-serif" },
  { label: "Inter", value: "Inter", style: "'Inter', sans-serif" },
];

const STYLE_OPTIONS = [
  { label: "Normal", value: "p" },
  { label: "Heading 1", value: "h1" },
  { label: "Heading 2", value: "h2" },
  { label: "Heading 3", value: "h3" },
];

export const RichTextEditor = React.forwardRef<RichTextEditorRef, RichTextEditorProps>(({
  initialHtml = "",
  onChange,
  placeholder = "Write your email message here...",
  minHeightClass = "min-h-[360px]",
}, ref) => {
  const editorRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const savedRangeRef = useRef<Range | null>(null);
  const isInitialized = useRef(false);
  const lastReportedHtmlRef = useRef<string>(initialHtml);

  // Dropdown states
  const [isFontDropdownOpen, setIsFontDropdownOpen] = useState(false);
  const [isStyleDropdownOpen, setIsStyleDropdownOpen] = useState(false);
  const [selectedFontLabel, setSelectedFontLabel] = useState("Sans Serif");
  const [selectedStyleLabel, setSelectedStyleLabel] = useState("Normal");

  // Active toolbar states
  const [activeStates, setActiveStates] = useState<ActiveStates>({
    bold: false,
    italic: false,
    underline: false,
    strikeThrough: false,
    unorderedList: false,
    orderedList: false,
    blockquote: false,
    code: false,
    align: "left",
    style: "p",
    font: "sans-serif",
  });

  // Save current selection range inside the editor
  const saveSelection = useCallback(() => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      savedRangeRef.current = sel.getRangeAt(0).cloneRange();
    }
  }, []);

  // Restore saved selection range
  const restoreSelection = useCallback(() => {
    if (savedRangeRef.current) {
      const sel = window.getSelection();
      if (sel) {
        sel.removeAllRanges();
        sel.addRange(savedRangeRef.current);
      }
    }
  }, []);

  // Sync initial content or external programmatic updates (templates, reply quote, drafts)
  useEffect(() => {
    if (!editorRef.current) return;

    if (!isInitialized.current) {
      if (initialHtml) {
        editorRef.current.innerHTML = initialHtml;
        lastReportedHtmlRef.current = initialHtml;
        isInitialized.current = true;
      }
      return;
    }

    // Only update innerHTML when the prop change was NOT caused by the user typing
    if (initialHtml !== lastReportedHtmlRef.current) {
      editorRef.current.innerHTML = initialHtml;
      lastReportedHtmlRef.current = initialHtml;
    }
  }, [initialHtml]);

  const handleInput = useCallback(() => {
    if (editorRef.current) {
      const html = editorRef.current.innerHTML;
      const text = editorRef.current.innerText;
      lastReportedHtmlRef.current = html;
      isInitialized.current = true;
      onChange(html, text);
    }
  }, [onChange]);

  // Query and update active states of toolbar buttons
  const updateActiveStates = useCallback(() => {
    if (!editorRef.current) return;
    const sel = window.getSelection();
    if (!sel || !sel.anchorNode || !editorRef.current.contains(sel.anchorNode)) {
      return;
    }

    // Always update saved selection range when active inside editor
    if (sel.rangeCount > 0) {
      savedRangeRef.current = sel.getRangeAt(0).cloneRange();
    }

    try {
      const bold = document.queryCommandState("bold");
      const italic = document.queryCommandState("italic");
      const underline = document.queryCommandState("underline");
      const strikeThrough = document.queryCommandState("strikeThrough");
      const unorderedList = document.queryCommandState("insertUnorderedList");
      const orderedList = document.queryCommandState("insertOrderedList");
      const justifyCenter = document.queryCommandState("justifyCenter");
      const justifyRight = document.queryCommandState("justifyRight");

      // Inspect ancestor elements for blockquote, pre, code, and headings
      let node: Node | null = sel.anchorNode;
      if (node.nodeType === Node.TEXT_NODE) {
        node = node.parentNode;
      }
      const el = node as HTMLElement | null;

      const blockquote = !!el?.closest("blockquote");
      const code = !!el?.closest("pre, code");

      let currentStyle = "p";
      let styleLabel = "Normal";
      if (el?.closest("h1")) {
        currentStyle = "h1";
        styleLabel = "Heading 1";
      } else if (el?.closest("h2")) {
        currentStyle = "h2";
        styleLabel = "Heading 2";
      } else if (el?.closest("h3")) {
        currentStyle = "h3";
        styleLabel = "Heading 3";
      }
      setSelectedStyleLabel(styleLabel);

      // Detect current font family via queryCommandValue or enclosing element style
      let rawFont = document.queryCommandValue("fontName") || "";
      if (!rawFont && el) {
        const fontEl = el.closest("[style*='font-family']") as HTMLElement | null;
        if (fontEl) {
          rawFont = fontEl.style.fontFamily;
        }
      }
      const cleanFont = rawFont.replace(/['"]/g, "").trim().toLowerCase();
      const matchedFont = FONT_OPTIONS.find((f) =>
        cleanFont === f.value.toLowerCase() ||
        cleanFont === f.label.toLowerCase() ||
        cleanFont.startsWith(f.value.toLowerCase()) ||
        cleanFont.includes(f.value.toLowerCase())
      );
      if (matchedFont) {
        setSelectedFontLabel(matchedFont.label);
      } else if (!cleanFont || cleanFont.includes("jakarta")) {
        setSelectedFontLabel("Sans Serif");
      }

      setActiveStates({
        bold,
        italic,
        underline,
        strikeThrough,
        unorderedList,
        orderedList,
        blockquote,
        code,
        align: justifyRight ? "right" : justifyCenter ? "center" : "left",
        style: currentStyle,
        font: rawFont,
      });
    } catch {
      // Ignored for detached ranges
    }
  }, []);

  useImperativeHandle(ref, () => ({
    insertHtml: (html: string) => {
      restoreSelection();
      editorRef.current?.focus();
      restoreSelection();
      document.execCommand("insertHTML", false, html);
      handleInput();
      updateActiveStates();
    },
    insertText: (text: string) => {
      restoreSelection();
      editorRef.current?.focus();
      restoreSelection();
      document.execCommand("insertText", false, text);
      handleInput();
      updateActiveStates();
    },
    focus: () => {
      editorRef.current?.focus();
    },
    getHtml: () => editorRef.current?.innerHTML || "",
    getText: () => editorRef.current?.innerText || "",
    setHtml: (html: string) => {
      if (editorRef.current) {
        editorRef.current.innerHTML = html;
        lastReportedHtmlRef.current = html;
        handleInput();
      }
    },
  }), [restoreSelection, handleInput, updateActiveStates]);

  // Listen to selection changes across the document
  useEffect(() => {
    const handleSelectionChange = () => {
      updateActiveStates();
    };
    document.addEventListener("selectionchange", handleSelectionChange);
    return () => {
      document.removeEventListener("selectionchange", handleSelectionChange);
    };
  }, [updateActiveStates]);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsFontDropdownOpen(false);
        setIsStyleDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Core execution helper
  const exec = (command: string, value: string | undefined = undefined) => {
    restoreSelection();
    editorRef.current?.focus();
    restoreSelection();
    document.execCommand("styleWithCSS", false, "true");
    document.execCommand(command, false, value);
    handleInput();
    updateActiveStates();
  };

  // Font family handler
  const handleSelectFont = (fontValue: string, fontLabel: string) => {
    restoreSelection();
    editorRef.current?.focus();
    restoreSelection();

    document.execCommand("styleWithCSS", false, "true");

    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      // Formats selected text in place with the chosen font face
      document.execCommand("fontName", false, fontValue);
    } else if (sel && sel.isCollapsed && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      // Collapsed caret: insert zero-width space styled with chosen font so subsequent typing immediately uses this font
      const range = sel.getRangeAt(0);
      const span = document.createElement("span");
      span.style.fontFamily = fontValue;
      const zws = document.createTextNode("\u200B");
      span.appendChild(zws);
      range.insertNode(span);
      range.setStart(zws, 1);
      range.setEnd(zws, 1);
      sel.removeAllRanges();
      sel.addRange(range);
      savedRangeRef.current = range.cloneRange();
    } else {
      document.execCommand("fontName", false, fontValue);
    }

    setSelectedFontLabel(fontLabel);
    setIsFontDropdownOpen(false);
    handleInput();
    updateActiveStates();
  };

  // Text style handler (p, h1, h2, h3)
  const handleSelectStyle = (styleValue: string, styleLabel: string) => {
    editorRef.current?.focus();
    restoreSelection();
    if (styleValue === "p") {
      document.execCommand("formatBlock", false, "<p>");
    } else {
      document.execCommand("formatBlock", false, `<${styleValue}>`);
    }
    setSelectedStyleLabel(styleLabel);
    setIsStyleDropdownOpen(false);
    handleInput();
    updateActiveStates();
  };

  // Toggle blockquote
  const toggleBlockquote = () => {
    editorRef.current?.focus();
    restoreSelection();
    if (activeStates.blockquote) {
      document.execCommand("formatBlock", false, "<p>");
    } else {
      document.execCommand("formatBlock", false, "<blockquote>");
    }
    handleInput();
    updateActiveStates();
  };

  // Toggle code block
  const toggleCode = () => {
    editorRef.current?.focus();
    restoreSelection();
    if (activeStates.code) {
      document.execCommand("formatBlock", false, "<p>");
    } else {
      document.execCommand("formatBlock", false, "<pre>");
    }
    handleInput();
    updateActiveStates();
  };

  // Insert or edit hyperlink
  const handleInsertLink = () => {
    editorRef.current?.focus();
    restoreSelection();
    const sel = window.getSelection();
    let existingUrl = "";
    let anchorEl: HTMLAnchorElement | null = null;

    if (sel && sel.anchorNode) {
      const parent = sel.anchorNode.nodeType === Node.TEXT_NODE ? sel.anchorNode.parentNode : sel.anchorNode;
      anchorEl = (parent as HTMLElement)?.closest("a");
      if (anchorEl) {
        existingUrl = anchorEl.getAttribute("href") || "";
      }
    }

    const url = prompt("Enter hyperlink URL:", existingUrl || "https://");
    if (url === null) return;
    if (!url.trim()) {
      if (anchorEl) {
        document.execCommand("unlink", false);
      }
      handleInput();
      updateActiveStates();
      return;
    }

    const cleanUrl = url.trim().match(/^https?:\/\//i) ? url.trim() : `https://${url.trim()}`;
    if (sel && sel.isCollapsed) {
      const range = sel.getRangeAt(0);
      const linkNode = document.createElement("a");
      linkNode.href = cleanUrl;
      linkNode.textContent = cleanUrl;
      linkNode.target = "_blank";
      linkNode.rel = "noopener noreferrer";
      linkNode.style.color = "#4f46e5";
      linkNode.style.textDecoration = "underline";
      range.insertNode(linkNode);
      range.setStartAfter(linkNode);
      range.collapse(true);
      sel.removeAllRanges();
      sel.addRange(range);
    } else {
      document.execCommand("createLink", false, cleanUrl);
    }
    handleInput();
    updateActiveStates();
  };

  const getButtonClass = (isActive: boolean) =>
    `p-1.5 rounded transition-all select-none ${
      isActive
        ? "bg-indigo-100 text-indigo-700 font-semibold ring-1 ring-indigo-300 shadow-2xs"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/70"
    }`;

  return (
    <div ref={containerRef} className="flex flex-col border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs">
      <style>{`
        .compose-editor blockquote {
          border-left: 3px solid #6366f1;
          padding: 6px 14px;
          margin: 10px 0;
          color: #475569;
          font-style: italic;
          background: #f8fafc;
          border-radius: 0 6px 6px 0;
        }
        .compose-editor pre {
          background-color: #f1f5f9;
          color: #0f172a;
          padding: 10px 14px;
          border-radius: 8px;
          font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
          font-size: 13px;
          margin: 10px 0;
          overflow-x: auto;
          border: 1px solid #e2e8f0;
          white-space: pre-wrap;
        }
        .compose-editor code {
          background-color: #f1f5f9;
          color: #e11d48;
          padding: 2px 5px;
          border-radius: 4px;
          font-family: monospace;
          font-size: 12px;
        }
        .compose-editor ul {
          list-style-type: disc !important;
          margin: 8px 0 8px 24px !important;
          padding-left: 0 !important;
        }
        .compose-editor ol {
          list-style-type: decimal !important;
          margin: 8px 0 8px 24px !important;
          padding-left: 0 !important;
        }
        .compose-editor li {
          margin-bottom: 4px;
        }
        .compose-editor h1 {
          font-size: 1.5rem;
          font-weight: 700;
          margin: 14px 0 6px;
          color: #0f172a;
        }
        .compose-editor h2 {
          font-size: 1.25rem;
          font-weight: 600;
          margin: 12px 0 6px;
          color: #0f172a;
        }
        .compose-editor h3 {
          font-size: 1.125rem;
          font-weight: 600;
          margin: 10px 0 4px;
          color: #0f172a;
        }
        .compose-editor a {
          color: #4f46e5;
          text-decoration: underline;
        }
        .compose-editor a:hover {
          color: #3730a3;
        }
        .compose-editor p {
          margin: 4px 0;
        }
      `}</style>

      {/* Formatting Toolbar */}
      <div className="px-4 py-2 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center gap-1 text-slate-600 text-xs select-none">
        {/* Font Family Dropdown */}
        <div className="flex items-center gap-1 pr-2 border-r border-slate-200">
          <div className="relative">
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                saveSelection();
              }}
              onClick={() => {
                setIsFontDropdownOpen((prev) => !prev);
                setIsStyleDropdownOpen(false);
              }}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-200/60 text-xs font-medium text-slate-700 transition-colors"
              title="Font Family"
              aria-label="Font family"
            >
              <span>{selectedFontLabel}</span>
              <ChevronDown className="h-3 w-3 text-slate-400" />
            </button>

            {isFontDropdownOpen && (
              <div className="absolute left-0 top-full mt-1 w-36 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-30">
                {FONT_OPTIONS.map((opt) => (
                  <button
                    key={opt.label}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleSelectFont(opt.value, opt.label)}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center justify-between ${
                      selectedFontLabel === opt.label
                        ? "bg-indigo-50 text-indigo-700 font-semibold"
                        : "text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <span style={{ fontFamily: opt.style }}>{opt.label}</span>
                    {selectedFontLabel === opt.label && <span className="text-indigo-600 font-bold">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Text Style Dropdown (Normal, H1, H2, H3) */}
          <div className="relative">
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                saveSelection();
              }}
              onClick={() => {
                setIsStyleDropdownOpen((prev) => !prev);
                setIsFontDropdownOpen(false);
              }}
              className="flex items-center gap-1 px-2 py-1 rounded hover:bg-slate-200/60 text-xs font-medium text-slate-700 transition-colors"
              title="Text Style"
              aria-label="Text style"
            >
              <span>{selectedStyleLabel}</span>
              <ChevronDown className="h-3 w-3 text-slate-400" />
            </button>

            {isStyleDropdownOpen && (
              <div className="absolute left-0 top-full mt-1 w-32 bg-white border border-slate-200 rounded-lg shadow-lg py-1 z-30">
                {STYLE_OPTIONS.map((opt) => (
                  <button
                    key={opt.label}
                    type="button"
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => handleSelectStyle(opt.value, opt.label)}
                    className={`w-full text-left px-3 py-1.5 text-xs transition-colors flex items-center justify-between ${
                      selectedStyleLabel === opt.label
                        ? "bg-indigo-50 text-indigo-700 font-semibold"
                        : "text-slate-700 hover:bg-slate-100"
                    }`}
                  >
                    <span>{opt.label}</span>
                    {selectedStyleLabel === opt.label && <span className="text-indigo-600 font-bold">✓</span>}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Basic Styles: Bold, Italic, Underline, Strikethrough */}
        <div className="flex items-center gap-0.5 px-2 border-r border-slate-200">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("bold")}
            className={getButtonClass(activeStates.bold)}
            title="Bold (Ctrl+B)"
            aria-label="Bold"
          >
            <Bold className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("italic")}
            className={getButtonClass(activeStates.italic)}
            title="Italic (Ctrl+I)"
            aria-label="Italic"
          >
            <Italic className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("underline")}
            className={getButtonClass(activeStates.underline)}
            title="Underline (Ctrl+U)"
            aria-label="Underline"
          >
            <Underline className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("strikeThrough")}
            className={getButtonClass(activeStates.strikeThrough)}
            title="Strikethrough"
            aria-label="Strikethrough"
          >
            <Strikethrough className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Lists & Blocks: Unordered, Ordered, Blockquote, Code Block */}
        <div className="flex items-center gap-0.5 px-2 border-r border-slate-200">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("insertUnorderedList")}
            className={getButtonClass(activeStates.unorderedList)}
            title="Bulleted List"
            aria-label="Bullet list"
          >
            <List className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("insertOrderedList")}
            className={getButtonClass(activeStates.orderedList)}
            title="Numbered List"
            aria-label="Numbered list"
          >
            <ListOrdered className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={toggleBlockquote}
            className={getButtonClass(activeStates.blockquote)}
            title="Blockquote"
            aria-label="Blockquote"
          >
            <Quote className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={toggleCode}
            className={getButtonClass(activeStates.code)}
            title="Code Block"
            aria-label="Code block"
          >
            <Code className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Alignment: Left, Center, Right */}
        <div className="flex items-center gap-0.5 px-2 border-r border-slate-200">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("justifyLeft")}
            className={getButtonClass(activeStates.align === "left")}
            title="Align Left"
            aria-label="Align left"
          >
            <AlignLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("justifyCenter")}
            className={getButtonClass(activeStates.align === "center")}
            title="Align Center"
            aria-label="Align center"
          >
            <AlignCenter className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => exec("justifyRight")}
            className={getButtonClass(activeStates.align === "right")}
            title="Align Right"
            aria-label="Align right"
          >
            <AlignRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Hyperlink */}
        <div className="flex items-center gap-0.5 pl-2">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleInsertLink}
            className="p-1.5 hover:bg-slate-200/70 rounded text-slate-700 hover:text-slate-900 transition-colors"
            title="Insert Link"
            aria-label="Insert link"
          >
            <LinkIcon className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Writing Canvas / ContentEditable */}
      <div
        ref={editorRef}
        contentEditable
        onInput={handleInput}
        onKeyUp={updateActiveStates}
        onMouseUp={updateActiveStates}
        data-placeholder={placeholder}
        className={`compose-editor p-6 sm:p-8 ${minHeightClass} max-h-[600px] overflow-y-auto text-slate-800 text-sm sm:text-base leading-relaxed outline-none focus:ring-0`}
      />
    </div>
  );
});

RichTextEditor.displayName = "RichTextEditor";
