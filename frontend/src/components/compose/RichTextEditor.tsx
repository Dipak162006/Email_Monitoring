import React, { useRef, useEffect, useState, useCallback, useImperativeHandle, useContext } from "react";
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
  Image as ImageIcon,
  Upload,
  Globe,
  Trash2,
  X,
  Check,
  Loader2,
  Palette,
  Type,
  MousePointerClick,
} from "lucide-react";
import { uploadMedia } from "../../services/api";
import { WorkspaceContext } from "../../context/WorkspaceContext";

export interface RichTextEditorRef {
  insertHtml: (html: string) => void;
  insertBlockHtml: (html: string) => void;
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
  companyId?: number | null;
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
  value: string;
  style: string;
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

export interface StyleOption {
  label: string;
  value: string;
  fontSize: string;
  fontWeight: string;
}

const STYLE_OPTIONS: StyleOption[] = [
  { label: "Normal", value: "p", fontSize: "15px", fontWeight: "normal" },
  { label: "Small", value: "small", fontSize: "12px", fontWeight: "normal" },
  { label: "Large", value: "large", fontSize: "18px", fontWeight: "600" },
  { label: "Heading 1", value: "h1", fontSize: "28px", fontWeight: "800" },
  { label: "Heading 2", value: "h2", fontSize: "24px", fontWeight: "700" },
  { label: "Heading 3", value: "h3", fontSize: "20px", fontWeight: "700" },
];

const BUTTON_COLOR_PRESETS = [
  { name: "Indigo", hex: "#4f46e5" },
  { name: "Slate", hex: "#0f172a" },
  { name: "Blue", hex: "#2563eb" },
  { name: "Emerald", hex: "#059669" },
  { name: "Rose", hex: "#e11d48" },
  { name: "Amber", hex: "#d97706" },
];

/**
 * Normalizes raw image URLs, extracting direct image targets from Google Images redirects
 * and ensuring valid protocols and clean strings.
 */
export function normalizeImageUrl(rawUrl: string): string {
  if (!rawUrl) return "";
  let url = rawUrl.trim().replace(/&amp;/g, "&");

  // Check if it's a Google Images redirect URL containing ?imgurl= or &imgurl= or ?url=
  if (url.includes("google.") && (url.includes("imgurl=") || url.includes("url="))) {
    try {
      const fullUrl = /^https?:\/\//i.test(url) ? url : `https://${url}`;
      const parsed = new URL(fullUrl);
      const imgurlParam = parsed.searchParams.get("imgurl") || parsed.searchParams.get("url");
      if (imgurlParam) {
        url = decodeURIComponent(imgurlParam);
      }
    } catch {
      const match = url.match(/[?&](?:imgurl|url)=([^&]+)/i);
      if (match && match[1]) {
        try {
          url = decodeURIComponent(match[1]);
        } catch {
          url = match[1];
        }
      }
    }
  }

  // Prepend https:// if not starting with protocol, relative path, or data URI
  if (
    !url.startsWith("http://") &&
    !url.startsWith("https://") &&
    !url.startsWith("data:") &&
    !url.startsWith("/") &&
    !url.startsWith("blob:")
  ) {
    url = `https://${url}`;
  }

  return url;
}

/**
 * Cleans pasted email HTML (such as Google One / Uber emails from Gmail):
 * - Strips Gmail chrome offsets (.gmail_quote margin-left).
 * - Constrains all tables to max-width: 100% and max-width: 600px with center auto-margins.
 * - Collapses layout tables and clears unwanted faint borders.
 * - Adds referrerpolicy="no-referrer" and max-width: 100% to all images.
 */
export function cleanPastedHtml(html: string): string {
  if (!html || !html.trim()) return html;

  try {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");

    // 1. Strip Gmail-specific chrome & margin offsets
    const gmailQuotes = doc.querySelectorAll(".gmail_quote, .gmail_default, .gmail_extra");
    gmailQuotes.forEach((el) => {
      const htmlEl = el as HTMLElement;
      if (htmlEl.style.marginLeft) htmlEl.style.marginLeft = "0";
      if (htmlEl.style.paddingLeft) htmlEl.style.paddingLeft = "0";
      if (htmlEl.style.borderLeft) htmlEl.style.borderLeft = "none";
    });

    // Strip outer divs with excessive margin-left that push content off-screen
    const allDivs = doc.querySelectorAll("div");
    allDivs.forEach((div) => {
      const htmlDiv = div as HTMLElement;
      if (htmlDiv.style.marginLeft) {
        const ml = parseInt(htmlDiv.style.marginLeft, 10);
        if (!isNaN(ml) && ml > 20) {
          htmlDiv.style.marginLeft = "auto";
          htmlDiv.style.marginRight = "auto";
        }
      }
    });

    // 2. Normalize <table> elements
    const tables = doc.querySelectorAll("table");
    tables.forEach((table) => {
      const htmlTable = table as HTMLElement;
      htmlTable.style.maxWidth = "100%";
      htmlTable.style.boxSizing = "border-box";

      // If no explicit border is set, collapse cleanly without faint cell lines
      if (!table.getAttribute("border") || table.getAttribute("border") === "0") {
        htmlTable.style.borderCollapse = "collapse";
      }

      const attrWidth = table.getAttribute("width");
      const numAttrWidth = attrWidth ? parseInt(attrWidth, 10) : 0;
      const styleWidth = htmlTable.style.width ? parseInt(htmlTable.style.width, 10) : 0;

      if (numAttrWidth > 600 || styleWidth > 600) {
        htmlTable.style.width = "100%";
        htmlTable.style.maxWidth = "600px";
        htmlTable.style.marginLeft = "auto";
        htmlTable.style.marginRight = "auto";
        table.setAttribute("width", "100%");
      }
    });

    // 3. Normalize table cells (remove faint borders from layout tables)
    const cells = doc.querySelectorAll("td, th");
    cells.forEach((cell) => {
      const htmlCell = cell as HTMLElement;
      htmlCell.style.boxSizing = "border-box";
      const table = htmlCell.closest("table");
      if (table && (!table.getAttribute("border") || table.getAttribute("border") === "0")) {
        if (!htmlCell.style.border && !htmlCell.style.borderWidth) {
          htmlCell.style.borderColor = "transparent";
        }
      }
    });

    // 4. Normalize <img> elements
    const images = doc.querySelectorAll("img");
    images.forEach((img) => {
      const htmlImg = img as HTMLElement;
      img.setAttribute("referrerpolicy", "no-referrer");
      htmlImg.style.maxWidth = "100%";
      if (!htmlImg.style.height || htmlImg.style.height === "auto") {
        htmlImg.style.height = "auto";
      }
    });

    return doc.body.innerHTML;
  } catch (err) {
    console.warn("Failed to clean pasted HTML:", err);
    return html;
  }
}

export const RichTextEditor = React.forwardRef<RichTextEditorRef, RichTextEditorProps>(({
  initialHtml = "",
  onChange,
  placeholder = "Write your email message here...",
  minHeightClass = "min-h-[360px]",
  companyId,
}, ref) => {
  const workspace = useContext(WorkspaceContext);
  const effectiveCompanyId = companyId !== undefined ? companyId : (workspace?.currentCompanyId ?? null);

  const editorRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const replaceImgInputRef = useRef<HTMLInputElement>(null);
  const savedRangeRef = useRef<Range | null>(null);
  const isInitialized = useRef(false);
  const lastReportedHtmlRef = useRef<string>(initialHtml);

  // Dropdown states
  const [isFontDropdownOpen, setIsFontDropdownOpen] = useState(false);
  const [isStyleDropdownOpen, setIsStyleDropdownOpen] = useState(false);
  const [selectedFontLabel, setSelectedFontLabel] = useState("Sans Serif");
  const [selectedStyleLabel, setSelectedStyleLabel] = useState("Normal");

  // Drag and drop feedback
  const [isDraggingOver, setIsDraggingOver] = useState(false);

  // Media upload & replacement states
  const [isUploading, setIsUploading] = useState(false);

  // Image insertion modal state
  const [isImageModalOpen, setIsImageModalOpen] = useState(false);
  const [imageTab, setImageTab] = useState<"upload" | "url">("upload");
  const [imageUrl, setImageUrl] = useState("");
  const [imageAlt, setImageAlt] = useState("");
  const [imageWidth, setImageWidth] = useState<"100%" | "75%" | "50%" | "25%">("100%");
  const [imageAlign, setImageAlign] = useState<"left" | "center" | "right">("center");
  const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);

  // Docked Image Inspector state on clicked <img> in editor
  const [selectedImgEl, setSelectedImgEl] = useState<HTMLImageElement | null>(null);
  const [imgEditUrl, setImgEditUrl] = useState("");
  const [imgEditAlt, setImgEditAlt] = useState("");
  const [imgActiveWidth, setImgActiveWidth] = useState<"25%" | "50%" | "75%" | "100%">("100%");
  const [imgActiveAlign, setImgActiveAlign] = useState<"left" | "center" | "right">("center");
  const [imgError, setImgError] = useState<string | null>(null);

  // Docked Link/CTA Button Inspector state on clicked <a> in editor
  const [selectedLinkEl, setSelectedLinkEl] = useState<HTMLAnchorElement | null>(null);
  const [linkEditHref, setLinkEditHref] = useState("");
  const [linkEditText, setLinkEditText] = useState("");
  const [linkEditBgColor, setLinkEditBgColor] = useState("#4f46e5");
  const [linkActiveAlign, setLinkActiveAlign] = useState<"left" | "center" | "right">("center");
  const [isLinkButton, setIsLinkButton] = useState(false);

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

  // Sync initial content or external programmatic updates
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
    if (sel && sel.rangeCount > 0 && editorRef.current.contains(sel.anchorNode)) {
      savedRangeRef.current = sel.getRangeAt(0).cloneRange();
    }

    try {
      let bold = document.queryCommandState("bold");
      let italic = document.queryCommandState("italic");
      let underline = document.queryCommandState("underline");
      let strikeThrough = document.queryCommandState("strikeThrough");
      const unorderedList = document.queryCommandState("insertUnorderedList");
      const orderedList = document.queryCommandState("insertOrderedList");
      const justifyCenter = document.queryCommandState("justifyCenter");
      const justifyRight = document.queryCommandState("justifyRight");

      let node: Node | null = sel?.anchorNode ?? null;
      if (node && node.nodeType === Node.TEXT_NODE) {
        node = node.parentNode;
      }
      const el = node as HTMLElement | null;

      const blockquote = !!el?.closest("blockquote");
      const code = !!el?.closest("pre, code");

      let currentStyle = "p";
      let styleLabel = "Normal";

      if (selectedLinkEl) {
        bold = selectedLinkEl.style.fontWeight === "bold" || parseInt(selectedLinkEl.style.fontWeight || "0", 10) >= 700;
        italic = selectedLinkEl.style.fontStyle === "italic";
        underline = !!selectedLinkEl.style.textDecoration?.includes("underline");
        strikeThrough = !!selectedLinkEl.style.textDecoration?.includes("line-through");

        const fs = selectedLinkEl.style.fontSize;
        const matchedStyle = STYLE_OPTIONS.find((s) => s.fontSize === fs);
        if (matchedStyle) {
          currentStyle = matchedStyle.value;
          styleLabel = matchedStyle.label;
        }
      } else {
        const heading = el?.closest("h1, h2, h3, h4, h5, h6") as HTMLElement | null;
        if (heading) {
          const tag = heading.tagName.toLowerCase();
          currentStyle = tag;
          const matched = STYLE_OPTIONS.find((s) => s.value === tag);
          styleLabel = matched ? matched.label : `Heading ${tag.replace("h", "")}`;
        } else if (el) {
          const block = el.closest("p, div, td, [data-email-block]") as HTMLElement | null;
          const fs = block?.style.fontSize || el.style.fontSize;
          const matchedStyle = STYLE_OPTIONS.find((s) => s.fontSize === fs);
          if (matchedStyle) {
            currentStyle = matchedStyle.value;
            styleLabel = matchedStyle.label;
          }
        }
      }
      setSelectedStyleLabel(styleLabel);

      let rawFont = document.queryCommandValue("fontName") || "";
      if (selectedLinkEl && selectedLinkEl.style.fontFamily) {
        rawFont = selectedLinkEl.style.fontFamily;
      } else if (!rawFont && el) {
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
      } else if (!cleanFont || cleanFont.includes("sans") || cleanFont.includes("system-ui")) {
        setSelectedFontLabel("Sans Serif");
      }

      let activeAlign: "left" | "center" | "right" = justifyRight ? "right" : justifyCenter ? "center" : "left";
      if (selectedImgEl) {
        activeAlign = imgActiveAlign;
      } else if (selectedLinkEl) {
        activeAlign = linkActiveAlign;
      } else if (el) {
        const block = el.closest("p, h1, h2, h3, h4, h5, h6, div, td, th, [data-email-block]") as HTMLElement | null;
        if (block?.style.textAlign) {
          const t = block.style.textAlign.toLowerCase();
          if (t === "left" || t === "center" || t === "right") activeAlign = t as any;
        }
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
        align: activeAlign,
        style: currentStyle,
        font: rawFont,
      });
    } catch {
      // Ignored for detached ranges
    }
  }, [selectedLinkEl, selectedImgEl, imgActiveAlign, linkActiveAlign]);

  // Insert modular block or image HTML cleanly
  const insertBlockHtmlInternal = useCallback((htmlToInsert: string) => {
    if (!editorRef.current) return;
    editorRef.current.focus();
    restoreSelection();

    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editorRef.current.contains(sel.anchorNode)) {
      const range = sel.getRangeAt(0);
      range.deleteContents();

      const tempDiv = document.createElement("div");
      tempDiv.innerHTML = htmlToInsert;
      const frag = document.createDocumentFragment();
      let node: Node | null;
      let lastNode: Node | null = null;
      while ((node = tempDiv.firstChild)) {
        lastNode = frag.appendChild(node);
      }
      range.insertNode(frag);

      if (lastNode) {
        range.setStartAfter(lastNode);
        range.collapse(true);
        sel.removeAllRanges();
        sel.addRange(range);
        savedRangeRef.current = range.cloneRange();
      }
    } else {
      editorRef.current.innerHTML += htmlToInsert;
    }

    handleInput();
    updateActiveStates();
  }, [restoreSelection, handleInput, updateActiveStates]);

  useImperativeHandle(ref, () => ({
    insertHtml: (html: string) => {
      restoreSelection();
      editorRef.current?.focus();
      restoreSelection();
      document.execCommand("insertHTML", false, html);
      handleInput();
      updateActiveStates();
    },
    insertBlockHtml: (html: string) => {
      insertBlockHtmlInternal(html);
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
  }), [restoreSelection, handleInput, updateActiveStates, insertBlockHtmlInternal]);

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

  // Close dropdowns & docked inspectors on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (containerRef.current && !containerRef.current.contains(target)) {
        setIsFontDropdownOpen(false);
        setIsStyleDropdownOpen(false);
        setSelectedImgEl(null);
        setSelectedLinkEl(null);
        setImgError(null);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Close inspectors on Escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSelectedImgEl(null);
        setSelectedLinkEl(null);
        setImgError(null);
        setIsFontDropdownOpen(false);
        setIsStyleDropdownOpen(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
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

  // Unified formatting toggle (B, I, U, S)
  const toggleFormat = (format: "bold" | "italic" | "underline" | "strikeThrough") => {
    if (selectedLinkEl) {
      if (format === "bold") {
        const isBold = selectedLinkEl.style.fontWeight === "bold" || parseInt(selectedLinkEl.style.fontWeight || "0", 10) >= 700;
        selectedLinkEl.style.fontWeight = isBold ? "normal" : "bold";
      } else if (format === "italic") {
        selectedLinkEl.style.fontStyle = selectedLinkEl.style.fontStyle === "italic" ? "normal" : "italic";
      } else if (format === "underline") {
        selectedLinkEl.style.textDecoration = selectedLinkEl.style.textDecoration?.includes("underline") ? "none" : "underline";
      } else if (format === "strikeThrough") {
        selectedLinkEl.style.textDecoration = selectedLinkEl.style.textDecoration?.includes("line-through") ? "none" : "line-through";
      }
      handleInput();
      updateActiveStates();
      return;
    }

    exec(format);

    // If inside a block with hardcoded font-weight, override it on the element
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      let node: Node | null = sel.anchorNode;
      if (node?.nodeType === Node.TEXT_NODE) node = node.parentNode;
      const parentEl = node as HTMLElement | null;
      if (parentEl && parentEl.style.fontWeight && format === "bold") {
        const isBold = parentEl.style.fontWeight === "bold" || parseInt(parentEl.style.fontWeight || "0", 10) >= 700;
        parentEl.style.fontWeight = isBold ? "normal" : "bold";
        handleInput();
      }
    }
  };

  // Unified Alignment Function: Works on images, CTA buttons, Hero Headers, and text blocks
  const applyAlignment = useCallback((align: "left" | "center" | "right") => {
    restoreSelection();

    // 1. If an Image is selected
    if (selectedImgEl && editorRef.current?.contains(selectedImgEl)) {
      selectedImgEl.style.display = "block";
      if (align === "left") {
        selectedImgEl.style.margin = "0 auto 0 0";
        selectedImgEl.style.marginLeft = "0";
        selectedImgEl.style.marginRight = "auto";
      } else if (align === "center") {
        selectedImgEl.style.margin = "0 auto";
        selectedImgEl.style.marginLeft = "auto";
        selectedImgEl.style.marginRight = "auto";
      } else {
        selectedImgEl.style.margin = "0 0 0 auto";
        selectedImgEl.style.marginLeft = "auto";
        selectedImgEl.style.marginRight = "0";
      }

      const parent = (selectedImgEl.closest('[data-email-block="image"]') || selectedImgEl.parentElement) as HTMLElement | null;
      if (parent) {
        parent.style.textAlign = align;
      }
      setImgActiveAlign(align);
      setImageAlign(align);
      handleInput();
      updateActiveStates();
      return;
    }

    // 2. If a CTA Button or Link is selected
    if (selectedLinkEl && editorRef.current?.contains(selectedLinkEl)) {
      const btnContainer = (selectedLinkEl.closest('[data-email-block="button"]') || selectedLinkEl.parentElement) as HTMLElement | null;
      if (btnContainer) {
        btnContainer.style.textAlign = align;
      }
      setLinkActiveAlign(align);
      handleInput();
      updateActiveStates();
      return;
    }

    // 3. Text or Block element in selection
    const sel = window.getSelection();
    let blockEl: HTMLElement | null = null;

    if (sel && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      let node: Node | null = sel.anchorNode;
      if (node && node.nodeType === Node.TEXT_NODE) {
        node = node.parentNode;
      }
      blockEl = (node as HTMLElement | null)?.closest?.("p, h1, h2, h3, h4, h5, h6, div, td, th, li, [data-email-block]") as HTMLElement | null;
    }

    if (blockEl && editorRef.current?.contains(blockEl) && blockEl !== editorRef.current) {
      blockEl.style.textAlign = align;

      // Handle auto-margins (e.g. Hero Header subtitle or constrained max-width blocks)
      const styleAttr = blockEl.getAttribute("style") || "";
      if (styleAttr.includes("margin-left") || styleAttr.includes("margin: 0 auto") || blockEl.style.maxWidth) {
        if (align === "left") {
          blockEl.style.marginLeft = "0";
          blockEl.style.marginRight = "auto";
        } else if (align === "center") {
          blockEl.style.marginLeft = "auto";
          blockEl.style.marginRight = "auto";
        } else if (align === "right") {
          blockEl.style.marginLeft = "auto";
          blockEl.style.marginRight = "0";
        }
      }
    }

    // Fallback execCommand for text nodes
    const cmd = align === "left" ? "justifyLeft" : align === "center" ? "justifyCenter" : "justifyRight";
    document.execCommand(cmd, false);

    handleInput();
    updateActiveStates();
  }, [selectedImgEl, selectedLinkEl, restoreSelection, handleInput, updateActiveStates]);

  // Font family handler
  const handleSelectFont = (fontValue: string, fontLabel: string) => {
    restoreSelection();
    editorRef.current?.focus();
    restoreSelection();

    if (selectedLinkEl) {
      selectedLinkEl.style.fontFamily = fontValue;
      setSelectedFontLabel(fontLabel);
      setIsFontDropdownOpen(false);
      handleInput();
      updateActiveStates();
      return;
    }

    document.execCommand("styleWithCSS", false, "true");

    const sel = window.getSelection();
    if (sel && !sel.isCollapsed && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      document.execCommand("fontName", false, fontValue);
    } else if (sel && sel.isCollapsed && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
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

    // Also update parent block if it has an inline font-family
    if (sel && sel.rangeCount > 0) {
      let node: Node | null = sel.anchorNode;
      if (node?.nodeType === Node.TEXT_NODE) node = node.parentNode;
      const block = (node as HTMLElement)?.closest("h1, h2, h3, p, div, td, [data-email-block]") as HTMLElement | null;
      if (block && block !== editorRef.current && block.style?.fontFamily) {
        block.style.fontFamily = fontValue;
      }
    }

    setSelectedFontLabel(fontLabel);
    setIsFontDropdownOpen(false);
    handleInput();
    updateActiveStates();
  };

  // Text style / Size handler (p, small, large, h1, h2, h3)
  const handleSelectStyle = (styleValue: string, styleLabel: string) => {
    restoreSelection();
    editorRef.current?.focus();
    restoreSelection();

    const opt = STYLE_OPTIONS.find((s) => s.value === styleValue) || STYLE_OPTIONS[0];

    if (selectedLinkEl) {
      selectedLinkEl.style.fontSize = opt.fontSize;
      selectedLinkEl.style.fontWeight = opt.fontWeight;
      setSelectedStyleLabel(styleLabel);
      setIsStyleDropdownOpen(false);
      handleInput();
      updateActiveStates();
      return;
    }

    const sel = window.getSelection();
    let block: HTMLElement | null = null;
    if (sel && sel.rangeCount > 0 && editorRef.current?.contains(sel.anchorNode)) {
      let node: Node | null = sel.anchorNode;
      if (node?.nodeType === Node.TEXT_NODE) node = node.parentNode;
      block = (node as HTMLElement)?.closest("h1, h2, h3, h4, h5, h6, p, div, td, [data-email-block]");
    }

    if (block && editorRef.current?.contains(block) && block !== editorRef.current) {
      if (["h1", "h2", "h3"].includes(styleValue)) {
        if (block.tagName.toLowerCase() !== styleValue && !["td", "div"].includes(block.tagName.toLowerCase())) {
          const newEl = document.createElement(styleValue);
          Array.from(block.attributes).forEach((attr) => newEl.setAttribute(attr.name, attr.value));
          newEl.innerHTML = block.innerHTML;
          newEl.style.fontSize = opt.fontSize;
          newEl.style.fontWeight = opt.fontWeight;
          block.parentNode?.replaceChild(newEl, block);
        } else {
          block.style.fontSize = opt.fontSize;
          block.style.fontWeight = opt.fontWeight;
        }
      } else {
        if (["h1", "h2", "h3", "h4", "h5", "h6"].includes(block.tagName.toLowerCase())) {
          const newP = document.createElement("p");
          Array.from(block.attributes).forEach((attr) => newP.setAttribute(attr.name, attr.value));
          newP.innerHTML = block.innerHTML;
          newP.style.fontSize = opt.fontSize;
          newP.style.fontWeight = opt.fontWeight;
          block.parentNode?.replaceChild(newP, block);
        } else {
          block.style.fontSize = opt.fontSize;
          block.style.fontWeight = opt.fontWeight;
        }
      }
    } else {
      if (["h1", "h2", "h3"].includes(styleValue)) {
        document.execCommand("formatBlock", false, `<${styleValue}>`);
      } else {
        document.execCommand("formatBlock", false, "<p>");
      }
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

  // Top toolbar Link button handler
  const handleToolbarLinkClick = () => {
    if (selectedLinkEl) {
      return;
    }

    restoreSelection();
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || !editorRef.current?.contains(sel.anchorNode)) {
      editorRef.current?.focus();
    }

    restoreSelection();
    const activeSel = window.getSelection();

    if (activeSel && !activeSel.isCollapsed && activeSel.rangeCount > 0) {
      const range = activeSel.getRangeAt(0);
      const existingAnchor = (range.commonAncestorContainer as HTMLElement)?.closest?.("a");
      if (existingAnchor) {
        setSelectedLinkEl(existingAnchor);
        setLinkEditHref(existingAnchor.getAttribute("href") || "");
        setLinkEditText(existingAnchor.textContent || "");
        return;
      }

      const linkNode = document.createElement("a");
      linkNode.href = "https://";
      linkNode.style.color = "#4f46e5";
      linkNode.style.textDecoration = "underline";
      try {
        range.surroundContents(linkNode);
      } catch {
        document.execCommand("createLink", false, "https://");
        const anchor = activeSel.anchorNode?.parentElement?.closest("a");
        if (anchor) {
          setSelectedLinkEl(anchor);
          setLinkEditHref(anchor.getAttribute("href") || "https://");
          setLinkEditText(anchor.textContent || "");
          return;
        }
      }
      setSelectedLinkEl(linkNode);
      setLinkEditHref("https://");
      setLinkEditText(linkNode.textContent || "");
      handleInput();
    } else {
      const url = prompt("Enter hyperlink URL:", "https://");
      if (!url || !url.trim()) return;
      const cleanUrl = url.trim().match(/^https?:\/\//i) ? url.trim() : `https://${url.trim()}`;
      const range = activeSel && activeSel.rangeCount > 0 ? activeSel.getRangeAt(0) : null;
      const linkNode = document.createElement("a");
      linkNode.href = cleanUrl;
      linkNode.textContent = cleanUrl;
      linkNode.style.color = "#4f46e5";
      linkNode.style.textDecoration = "underline";
      if (range) {
        range.insertNode(linkNode);
        range.setStartAfter(linkNode);
        range.collapse(true);
        activeSel?.removeAllRanges();
        activeSel?.addRange(range);
      } else {
        editorRef.current?.appendChild(linkNode);
      }
      setSelectedLinkEl(linkNode);
      setLinkEditHref(cleanUrl);
      setLinkEditText(cleanUrl);
      handleInput();
    }
  };

  // Canvas Drag & Drop Event Handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
    if (!isDraggingOver) {
      setIsDraggingOver(true);
    }
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.currentTarget === e.target) {
      setIsDraggingOver(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDraggingOver(false);

    // Position caret at drop location if supported
    if (document.caretRangeFromPoint) {
      const dropRange = document.caretRangeFromPoint(e.clientX, e.clientY);
      if (dropRange && editorRef.current?.contains(dropRange.startContainer)) {
        const sel = window.getSelection();
        if (sel) {
          sel.removeAllRanges();
          sel.addRange(dropRange);
          savedRangeRef.current = dropRange.cloneRange();
        }
      }
    }

    // 1. Check for dropped image file(s)
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      if (file.type.startsWith("image/")) {
        uploadImageFile(file).then((res) => {
          if (res) {
            const imageBlock = `<div data-email-block="image" style="text-align: center; margin: 20px 0;"><img src="${res.url}" alt="${res.fileName}" style="max-width: 100%; height: auto; border-radius: 8px; display: inline-block; border: 0;" /></div><p><br/></p>`;
            insertBlockHtmlInternal(imageBlock);
          }
        });
        return;
      }
    }

    // 2. Check for modular email block payload
    const blockHtml =
      e.dataTransfer.getData("application/x-email-block-html") ||
      e.dataTransfer.getData("text/html");

    if (blockHtml) {
      insertBlockHtmlInternal(blockHtml + "<p><br/></p>");
      return;
    }

    // 3. Plain text fallback
    const textData = e.dataTransfer.getData("text/plain");
    if (textData) {
      document.execCommand("insertText", false, textData);
      handleInput();
    }
  };

  // Upload helper for local images via backend media endpoint
  const uploadImageFile = useCallback(async (file: File): Promise<{ url: string; fileName: string } | null> => {
    const allowedRasterTypes = ["image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp"];
    if (!allowedRasterTypes.includes(file.type.toLowerCase())) {
      alert("Invalid image type. Please select a PNG, JPG, GIF, or WebP image.");
      return null;
    }
    const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5MB limit
    if (file.size > MAX_FILE_SIZE) {
      alert("Image file size exceeds the 5MB limit.");
      return null;
    }

    if (effectiveCompanyId) {
      try {
        setIsUploading(true);
        const res = await uploadMedia(effectiveCompanyId, file);
        return { url: res.url, fileName: res.file_name };
      } catch (err: any) {
        console.error("Media upload failed:", err);
        alert(err?.response?.data?.detail || "Failed to upload image. Please try again.");
        return null;
      } finally {
        setIsUploading(false);
      }
    } else {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (uploadEvent) => {
          resolve({
            url: uploadEvent.target?.result as string,
            fileName: file.name.replace(/[&<>"']/g, ""),
          });
        };
        reader.readAsDataURL(file);
      });
    }
  }, [effectiveCompanyId]);

  // Clipboard paste handler: intercept pasted image files or clean copied HTML emails (Gmail, Google One, Uber)
  const handlePaste = (e: React.ClipboardEvent) => {
    // 1. Raw image file paste
    if (e.clipboardData?.files && e.clipboardData.files.length > 0) {
      const file = e.clipboardData.files[0];
      if (file.type.startsWith("image/")) {
        e.preventDefault();
        uploadImageFile(file).then((res) => {
          if (res) {
            const imgHtml = `<img src="${res.url}" alt="${res.fileName}" referrerpolicy="no-referrer" style="max-width: 100%; height: auto; border-radius: 8px; display: inline-block;" />`;
            document.execCommand("insertHTML", false, imgHtml);
            handleInput();
            updateActiveStates();
          }
        });
        return;
      }
    }

    // 2. HTML text paste (e.g. from Gmail, Google One, Uber)
    const rawHtml = e.clipboardData?.getData("text/html");
    if (rawHtml) {
      e.preventDefault();
      const cleaned = cleanPastedHtml(rawHtml);
      document.execCommand("insertHTML", false, cleaned);
      handleInput();
      updateActiveStates();
      return;
    }
  };

  // Handle clicking on image or link inside editor to activate docked inspectors
  const handleEditorClick = (e: React.MouseEvent) => {
    const target = e.target as HTMLElement;

    // 1. Clicked an <img>
    if (target.tagName.toLowerCase() === "img") {
      const img = target as HTMLImageElement;
      setSelectedImgEl(img);
      setImgEditUrl(img.getAttribute("src") || "");
      setImgEditAlt(img.getAttribute("alt") || "");
      setImgError(null);

      // Current width
      const curW = img.style.width || img.style.maxWidth || img.getAttribute("width") || "";
      if (curW.includes("25%") || curW === "140") setImgActiveWidth("25%");
      else if (curW.includes("50%") || curW === "280") setImgActiveWidth("50%");
      else if (curW.includes("75%") || curW === "420") setImgActiveWidth("75%");
      else setImgActiveWidth("100%");

      // Current align
      const margin = img.style.margin || "";
      const ml = img.style.marginLeft || "";
      const mr = img.style.marginRight || "";
      const parentAlign = ((img.closest('[data-email-block="image"]') || img.parentElement) as HTMLElement)?.style.textAlign;
      let align: "left" | "center" | "right" = "center";
      if (margin.includes("0 auto 0 0") || (ml === "0px" && mr === "auto") || ml === "0" || parentAlign === "left") {
        align = "left";
      } else if (margin.includes("0 0 0 auto") || (ml === "auto" && (mr === "0px" || mr === "0")) || parentAlign === "right") {
        align = "right";
      } else {
        align = "center";
      }
      setImgActiveAlign(align);

      setSelectedLinkEl(null);
      return;
    }

    // 2. Clicked an <a> or CTA Button inside editor
    const anchor = target.closest("a");
    if (anchor && editorRef.current?.contains(anchor)) {
      e.preventDefault();
      setSelectedImgEl(null);
      setImgError(null);
      const anchorEl = anchor as HTMLAnchorElement;
      setSelectedLinkEl(anchorEl);
      setLinkEditHref(anchorEl.getAttribute("href") || "");
      setLinkEditText(anchorEl.textContent || "");

      const isBtn = !!anchorEl.closest('[data-email-block="button"]') ||
        anchorEl.classList.contains("button") ||
        (!!anchorEl.style.backgroundColor && anchorEl.style.backgroundColor !== "transparent");
      setIsLinkButton(isBtn);
      setLinkEditBgColor(anchorEl.style.backgroundColor || "#4f46e5");

      const parentContainer = (anchorEl.closest('[data-email-block="button"]') || anchorEl.parentElement) as HTMLElement | null;
      const align = (parentContainer?.style.textAlign || "center") as "left" | "center" | "right";
      setLinkActiveAlign(["left", "center", "right"].includes(align) ? align : "center");
      return;
    }

    // Otherwise clear selections
    setSelectedImgEl(null);
    setSelectedLinkEl(null);
    setImgError(null);
  };

  // Keep selected image highlighted with outline
  useEffect(() => {
    if (selectedImgEl) {
      selectedImgEl.classList.add("pulsemail-selected-img");
      return () => {
        selectedImgEl.classList.remove("pulsemail-selected-img");
      };
    }
  }, [selectedImgEl]);

  // Docked Inspector Actions for Images
  const handleResizeImage = (pctStr: string) => {
    if (!selectedImgEl) return;
    const pct = parseInt(pctStr.replace("%", ""), 10) || 100;
    selectedImgEl.style.width = `${pct}%`;
    selectedImgEl.style.maxWidth = `${pct}%`;
    selectedImgEl.style.height = "auto";
    selectedImgEl.setAttribute("width", String(Math.round((560 * pct) / 100)));
    setImgActiveWidth(`${pct}%` as "25%" | "50%" | "75%" | "100%");
    handleInput();
    updateActiveStates();
  };

  const handleDeleteImage = () => {
    if (!selectedImgEl) return;
    const parent = (selectedImgEl.closest('[data-email-block="image"]') || selectedImgEl.parentElement) as HTMLElement | null;
    if (parent && (parent.getAttribute("data-email-block") === "image" || (parent.children.length === 1 && parent !== editorRef.current))) {
      parent.remove();
    } else {
      selectedImgEl.remove();
    }
    setSelectedImgEl(null);
    setImgError(null);
    handleInput();
    updateActiveStates();
  };

  const handleReplaceImageFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !selectedImgEl) return;
    const res = await uploadImageFile(file);
    if (res) {
      selectedImgEl.src = res.url;
      selectedImgEl.removeAttribute("srcset");
      selectedImgEl.setAttribute("referrerpolicy", "no-referrer");
      selectedImgEl.alt = res.fileName;
      setImgEditUrl(res.url);
      setImgEditAlt(res.fileName);
      setImgError(null);
      handleInput();
      updateActiveStates();
    }
    if (replaceImgInputRef.current) replaceImgInputRef.current.value = "";
  };

  const handleApplyImageUrl = () => {
    if (!selectedImgEl) return;
    const trimmed = imgEditUrl.trim();
    if (!trimmed) return;
    const normalized = normalizeImageUrl(trimmed);
    setImgEditUrl(normalized);
    setImgError(null);

    // Verify image loading
    const testImg = new Image();
    testImg.referrerPolicy = "no-referrer";
    testImg.onload = () => {
      if (selectedImgEl) {
        selectedImgEl.src = normalized;
        selectedImgEl.removeAttribute("srcset");
        selectedImgEl.setAttribute("referrerpolicy", "no-referrer");
        setImgError(null);
        handleInput();
        updateActiveStates();
      }
    };
    testImg.onerror = () => {
      setImgError("Could not load image from this URL. Make sure it is a direct image link (ending in .png, .jpg, .webp) or use 'Upload' to pick from your computer.");
      if (selectedImgEl) {
        selectedImgEl.src = normalized;
        selectedImgEl.setAttribute("referrerpolicy", "no-referrer");
        handleInput();
        updateActiveStates();
      }
    };
    testImg.src = normalized;
  };

  const handleApplyImageAlt = (newAlt: string) => {
    setImgEditAlt(newAlt);
    if (selectedImgEl) {
      selectedImgEl.alt = newAlt;
      handleInput();
      updateActiveStates();
    }
  };

  // Link & CTA Button inspector actions
  const handleApplyLinkText = (newText: string) => {
    setLinkEditText(newText);
    if (selectedLinkEl) {
      selectedLinkEl.textContent = newText;
      handleInput();
      updateActiveStates();
    }
  };

  const handleApplyLinkHref = () => {
    if (!selectedLinkEl) return;
    const trimmed = linkEditHref.trim();
    if (!trimmed) {
      handleRemoveLink();
      return;
    }
    selectedLinkEl.setAttribute("href", trimmed);
    handleInput();
    updateActiveStates();
  };

  const handleApplyButtonColor = (color: string) => {
    setLinkEditBgColor(color);
    if (selectedLinkEl) {
      selectedLinkEl.style.backgroundColor = color;
      handleInput();
      updateActiveStates();
    }
  };

  const handleRemoveLink = () => {
    if (!selectedLinkEl) return;
    const parent = selectedLinkEl.parentNode;
    while (selectedLinkEl.firstChild) {
      parent?.insertBefore(selectedLinkEl.firstChild, selectedLinkEl);
    }
    selectedLinkEl.remove();
    setSelectedLinkEl(null);
    handleInput();
    updateActiveStates();
  };

  // Image Modal: File change handler
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const res = await uploadImageFile(file);
    if (res) {
      setImagePreviewUrl(res.url);
      if (!imageAlt) setImageAlt(res.fileName);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // Insert Image from modal
  const handleConfirmInsertImage = () => {
    let safeSrc = "";
    if (imageTab === "upload") {
      if (!imagePreviewUrl) return;
      safeSrc = imagePreviewUrl;
    } else {
      const trimmed = imageUrl.trim();
      if (!trimmed) return;
      const normalized = normalizeImageUrl(trimmed);

      try {
        const parsed = new URL(normalized);
        if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
          alert("Only http:// and https:// image URLs are allowed.");
          return;
        }
        safeSrc = parsed.href;
      } catch {
        alert("Please enter a valid image web URL.");
        return;
      }
    }

    const safeAlt = imageAlt.trim().replace(/[&<>"']/g, "") || "Image";
    const imageHtml = `<div data-email-block="image" style="text-align: ${imageAlign}; margin: 20px 0;"><img src="${safeSrc}" alt="${safeAlt}" referrerpolicy="no-referrer" style="max-width: ${imageWidth}; width: ${imageWidth}; height: auto; border-radius: 8px; display: inline-block; border: 0;" /></div><p><br/></p>`;

    insertBlockHtmlInternal(imageHtml);

    // Reset modal state
    setIsImageModalOpen(false);
    setImagePreviewUrl(null);
    setImageUrl("");
    setImageAlt("");
    setImageWidth("100%");
    setImageAlign("center");
  };

  const getButtonClass = (isActive: boolean) =>
    `p-1.5 rounded transition-all select-none ${
      isActive
        ? "bg-indigo-100 text-indigo-700 font-semibold ring-1 ring-indigo-300 shadow-2xs"
        : "text-slate-600 hover:text-slate-900 hover:bg-slate-200/70"
    }`;

  return (
    <div
      ref={containerRef}
      className="relative flex flex-col border border-slate-200 rounded-xl overflow-hidden bg-white shadow-2xs"
    >
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
        .compose-editor img {
          cursor: pointer;
          transition: outline 0.15s ease;
        }
        .compose-editor img:hover {
          outline: 2px dashed #6366f1;
          outline-offset: 2px;
        }
        .compose-editor img.pulsemail-selected-img {
          outline: 2px solid #6366f1 !important;
          outline-offset: 2px !important;
        }
        .compose-editor table,
        .pulsemail-editor-canvas table {
          max-width: 100% !important;
          border-collapse: collapse;
        }
        .compose-editor td,
        .compose-editor th,
        .pulsemail-editor-canvas td,
        .pulsemail-editor-canvas th {
          border-color: transparent;
          box-sizing: border-box;
        }
        .compose-editor img,
        .pulsemail-editor-canvas img {
          max-width: 100%;
          height: auto;
        }
      `}</style>

      {/* Formatting Toolbar */}
      <div
        role="toolbar"
        aria-label="Formatting controls"
        className="px-4 py-2 bg-slate-50/80 border-b border-slate-200 flex flex-wrap items-center gap-1 text-slate-600 text-xs select-none"
      >
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
            onClick={() => toggleFormat("bold")}
            className={getButtonClass(activeStates.bold)}
            title="Bold (Ctrl+B)"
            aria-label="Bold"
          >
            <Bold className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => toggleFormat("italic")}
            className={getButtonClass(activeStates.italic)}
            title="Italic (Ctrl+I)"
            aria-label="Italic"
          >
            <Italic className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => toggleFormat("underline")}
            className={getButtonClass(activeStates.underline)}
            title="Underline (Ctrl+U)"
            aria-label="Underline"
          >
            <Underline className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => toggleFormat("strikeThrough")}
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
            onClick={() => applyAlignment("left")}
            className={getButtonClass(activeStates.align === "left")}
            title="Align Left"
            aria-label="Align left"
          >
            <AlignLeft className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => applyAlignment("center")}
            className={getButtonClass(activeStates.align === "center")}
            title="Align Center"
            aria-label="Align center"
          >
            <AlignCenter className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => applyAlignment("right")}
            className={getButtonClass(activeStates.align === "right")}
            title="Align Right"
            aria-label="Align right"
          >
            <AlignRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Media & Links: Link, Image */}
        <div className="flex items-center gap-0.5 pl-2">
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={handleToolbarLinkClick}
            className="p-1.5 hover:bg-slate-200/70 rounded text-slate-700 hover:text-slate-900 transition-colors"
            title="Insert or Edit Link / Button"
            aria-label="Insert link"
          >
            <LinkIcon className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onMouseDown={(e) => {
              e.preventDefault();
              saveSelection();
            }}
            onClick={() => setIsImageModalOpen(true)}
            className="p-1.5 hover:bg-indigo-100 hover:text-indigo-700 rounded text-slate-700 transition-colors flex items-center gap-1 font-medium"
            title="Insert Image (Upload or URL)"
            aria-label="Insert image"
          >
            <ImageIcon className="h-3.5 w-3.5" />
            <span className="hidden sm:inline text-[11px]">Image</span>
          </button>
        </div>
      </div>

      {/* Docked Sticky Context Inspector Bar for Active Image */}
      {selectedImgEl && (
        <div
          role="region"
          aria-label="Image inspector"
          className="sticky top-0 z-20 px-4 py-2 bg-slate-900 text-white border-b border-slate-800 shadow-md flex flex-wrap items-center justify-between gap-2.5 text-xs select-none animate-in fade-in duration-150"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-bold text-[10px] uppercase tracking-wider border border-indigo-500/30">
              Image Selected
            </span>

            {/* Upload / Replace Image Button */}
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => replaceImgInputRef.current?.click()}
              disabled={isUploading}
              className="flex items-center gap-1.5 px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-lg text-xs font-medium transition-colors"
              title="Upload / Replace image from computer"
            >
              {isUploading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Upload className="h-3.5 w-3.5" />
              )}
              <span>Replace</span>
            </button>

            {/* Direct Image URL input */}
            <div className="flex items-center gap-1 border-l border-slate-700 pl-2">
              <Globe className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <input
                type="text"
                value={imgEditUrl}
                onChange={(e) => {
                  setImgEditUrl(e.target.value);
                  if (imgError) setImgError(null);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleApplyImageUrl();
                  }
                }}
                placeholder="Direct or Google Images URL..."
                className="w-36 sm:w-52 bg-slate-800 text-slate-100 px-2 py-1 rounded-md text-[11px] outline-none focus:ring-1 focus:ring-indigo-400 font-mono"
              />
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={handleApplyImageUrl}
                className="px-2 py-1 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-md text-xs font-medium transition-colors flex items-center gap-1"
                title="Apply URL"
              >
                <Check className="h-3.5 w-3.5" />
                <span>Apply</span>
              </button>
            </div>

            {/* Alt Text Input */}
            <div className="flex items-center gap-1 border-l border-slate-700 pl-2">
              <Type className="h-3.5 w-3.5 text-slate-400 shrink-0" />
              <input
                type="text"
                value={imgEditAlt}
                onChange={(e) => handleApplyImageAlt(e.target.value)}
                placeholder="Alt text..."
                className="w-24 sm:w-32 bg-slate-800 text-slate-100 px-2 py-1 rounded-md text-[11px] outline-none focus:ring-1 focus:ring-indigo-400"
                title="Image description (Alt text)"
              />
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Sizing Pills */}
            <div className="flex items-center gap-1 border-l sm:border-l-0 border-slate-700 pl-2 sm:pl-0">
              <span className="text-[10px] uppercase font-semibold text-slate-500 mr-0.5">Size:</span>
              {(["25%", "50%", "75%", "100%"] as const).map((pct) => (
                <button
                  key={pct}
                  type="button"
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => handleResizeImage(pct)}
                  className={`px-2 py-0.5 text-[11px] rounded font-semibold transition-all ${
                    imgActiveWidth === pct
                      ? "bg-indigo-600 text-white shadow-xs ring-1 ring-indigo-400"
                      : "bg-slate-800/80 text-slate-300 hover:bg-slate-800 hover:text-white"
                  }`}
                  title={`${pct} Width`}
                >
                  {pct}
                </button>
              ))}
            </div>

            {/* Align Buttons */}
            <div className="flex items-center gap-1 border-l border-slate-700 pl-2.5">
              <span className="text-[10px] uppercase font-semibold text-slate-500 mr-0.5">Align:</span>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("left")}
                className={`p-1 rounded transition-colors ${
                  imgActiveAlign === "left"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Left"
              >
                <AlignLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("center")}
                className={`p-1 rounded transition-colors ${
                  imgActiveAlign === "center"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Center"
              >
                <AlignCenter className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("right")}
                className={`p-1 rounded transition-colors ${
                  imgActiveAlign === "right"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Right"
              >
                <AlignRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Delete Image */}
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={handleDeleteImage}
              className="p-1.5 hover:bg-rose-900/60 rounded-lg text-rose-400 hover:text-rose-200 transition-colors ml-1"
              title="Remove Image"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>

            {/* Close */}
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                setSelectedImgEl(null);
                setImgError(null);
              }}
              className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors"
              title="Close Inspector"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Inline Error State */}
          {imgError && (
            <div className="w-full mt-1 px-3 py-1.5 bg-rose-950/80 border border-rose-800 rounded-lg text-rose-200 text-xs flex items-center justify-between gap-2 animate-in fade-in">
              <span className="flex-1">{imgError}</span>
              <button
                type="button"
                onClick={() => setImgError(null)}
                className="text-rose-400 hover:text-rose-200 p-0.5"
                title="Dismiss error"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )}
        </div>
      )}

      {/* Docked Sticky Context Inspector Bar for Active Link / CTA Button */}
      {selectedLinkEl && (
        <div
          role="region"
          aria-label="Link inspector"
          className="sticky top-0 z-20 px-4 py-2 bg-slate-900 text-white border-b border-slate-800 shadow-md flex flex-wrap items-center justify-between gap-2.5 text-xs select-none animate-in fade-in duration-150"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-bold text-[10px] uppercase tracking-wider border border-indigo-500/30 flex items-center gap-1">
              {isLinkButton ? (
                <MousePointerClick className="h-3 w-3" />
              ) : (
                <LinkIcon className="h-3 w-3" />
              )}
              <span>{isLinkButton ? "CTA Button" : "Link"}</span>
            </span>

            {/* Display Text Input */}
            <input
              type="text"
              value={linkEditText}
              onChange={(e) => handleApplyLinkText(e.target.value)}
              placeholder="Button text..."
              className="w-28 sm:w-36 bg-slate-800 text-slate-100 px-2 py-1 rounded-md text-xs outline-none focus:ring-1 focus:ring-indigo-400"
              title="Button/Link display text"
            />

            {/* URL Input */}
            <input
              type="text"
              value={linkEditHref}
              onChange={(e) => setLinkEditHref(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleApplyLinkHref();
                }
              }}
              placeholder="https://... or {{login_url}}"
              className="w-40 sm:w-60 bg-slate-800 text-slate-100 px-2 py-1 rounded-md text-xs outline-none focus:ring-1 focus:ring-indigo-400 font-mono"
              title="Hyperlink URL"
            />

            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={handleApplyLinkHref}
              className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-md text-xs font-medium transition-colors flex items-center gap-1 shrink-0"
              title="Apply URL"
            >
              <Check className="h-3.5 w-3.5" />
              <span>Apply</span>
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Alignment Buttons */}
            <div className="flex items-center gap-1">
              <span className="text-[10px] uppercase font-semibold text-slate-500 mr-0.5">Align:</span>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("left")}
                className={`p-1 rounded transition-colors ${
                  linkActiveAlign === "left"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Left"
              >
                <AlignLeft className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("center")}
                className={`p-1 rounded transition-colors ${
                  linkActiveAlign === "center"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Center"
              >
                <AlignCenter className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => applyAlignment("right")}
                className={`p-1 rounded transition-colors ${
                  linkActiveAlign === "right"
                    ? "bg-indigo-600 text-white"
                    : "hover:bg-slate-800 text-slate-300 hover:text-white"
                }`}
                title="Align Right"
              >
                <AlignRight className="h-3.5 w-3.5" />
              </button>
            </div>

            {/* Color Swatches if CTA Button */}
            {isLinkButton && (
              <div className="flex items-center gap-1.5 border-l border-slate-700 pl-2.5">
                <Palette className="h-3.5 w-3.5 text-slate-400 shrink-0" />
                <span className="text-[10px] uppercase font-semibold text-slate-500">Color:</span>
                <div className="flex items-center gap-1">
                  {BUTTON_COLOR_PRESETS.map((color) => (
                    <button
                      key={color.hex}
                      type="button"
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => handleApplyButtonColor(color.hex)}
                      style={{ backgroundColor: color.hex }}
                      className={`w-4 h-4 rounded-full border transition-transform hover:scale-110 ${
                        linkEditBgColor.toLowerCase() === color.hex.toLowerCase()
                          ? "border-white ring-2 ring-indigo-400 scale-110"
                          : "border-slate-600"
                      }`}
                      title={color.hex}
                    />
                  ))}
                  <input
                    type="color"
                    value={linkEditBgColor.startsWith("#") ? linkEditBgColor : "#4f46e5"}
                    onChange={(e) => handleApplyButtonColor(e.target.value)}
                    className="w-4 h-4 rounded cursor-pointer border-0 p-0 bg-transparent"
                    title="Custom button color"
                  />
                </div>
              </div>
            )}

            {/* Remove Link */}
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={handleRemoveLink}
              className="p-1.5 hover:bg-rose-900/60 rounded-md text-rose-400 hover:text-rose-200 transition-colors ml-1"
              title="Remove Link"
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>

            {/* Close */}
            <button
              type="button"
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => setSelectedLinkEl(null)}
              className="p-1 hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors"
              title="Close Inspector"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Writing Canvas / ContentEditable */}
      <div className="relative">
        {/* Hidden replacement file input for existing images */}
        <input
          ref={replaceImgInputRef}
          type="file"
          accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
          onChange={handleReplaceImageFile}
          className="hidden"
        />

        <div
          ref={editorRef}
          contentEditable
          onInput={handleInput}
          onKeyUp={updateActiveStates}
          onMouseUp={updateActiveStates}
          onClick={handleEditorClick}
          onPaste={handlePaste}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          data-placeholder={placeholder}
          className={`compose-editor pulsemail-editor-canvas p-6 sm:p-8 ${minHeightClass} max-h-[600px] overflow-y-auto text-slate-800 text-sm sm:text-base leading-relaxed outline-none focus:ring-0 transition-colors ${
            isDraggingOver ? "bg-indigo-50/40 ring-2 ring-indigo-400 ring-dashed" : ""
          }`}
        />

        {/* Drag Over Overlay Prompt */}
        {isDraggingOver && (
          <div className="absolute inset-0 bg-indigo-50/80 backdrop-blur-2xs flex flex-col items-center justify-center pointer-events-none z-20 border-2 border-dashed border-indigo-400 rounded-b-xl animate-in fade-in duration-100">
            <div className="p-3 bg-indigo-600 text-white rounded-full shadow-lg mb-2">
              <Upload className="h-6 w-6" />
            </div>
            <p className="font-bold text-sm text-indigo-900">Drop Image or Block Here</p>
            <p className="text-xs text-indigo-600">Release mouse to insert directly into email template</p>
          </div>
        )}
      </div>

      {/* Image Insertion Dialog Modal */}
      {isImageModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-md w-full overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
            {/* Header */}
            <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
              <div className="flex items-center gap-2">
                <div className="p-1.5 bg-indigo-50 text-indigo-600 rounded-lg">
                  <ImageIcon className="h-4 w-4" />
                </div>
                <h3 className="font-bold text-sm text-slate-900">Insert Email Image</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsImageModalOpen(false)}
                className="text-slate-400 hover:text-slate-700 rounded p-1 transition-colors"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-5 space-y-4">
              {/* Tab Selector */}
              <div className="flex bg-slate-100 p-1 rounded-lg text-xs font-semibold text-slate-600">
                <button
                  type="button"
                  onClick={() => setImageTab("upload")}
                  className={`flex-1 py-1.5 rounded-md flex items-center justify-center gap-1.5 transition-all ${
                    imageTab === "upload"
                      ? "bg-white text-indigo-700 shadow-2xs font-bold"
                      : "hover:text-slate-900"
                  }`}
                >
                  <Upload className="h-3.5 w-3.5" />
                  <span>Upload Image</span>
                </button>
                <button
                  type="button"
                  onClick={() => setImageTab("url")}
                  className={`flex-1 py-1.5 rounded-md flex items-center justify-center gap-1.5 transition-all ${
                    imageTab === "url"
                      ? "bg-white text-indigo-700 shadow-2xs font-bold"
                      : "hover:text-slate-900"
                  }`}
                >
                  <Globe className="h-3.5 w-3.5" />
                  <span>Image URL</span>
                </button>
              </div>

              {/* Upload Tab */}
              {imageTab === "upload" && (
                <div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/jpg,image/gif,image/webp"
                    onChange={handleFileChange}
                    className="hidden"
                  />
                  {imagePreviewUrl ? (
                    <div className="relative border border-slate-200 rounded-xl overflow-hidden bg-slate-50 flex items-center justify-center p-2 group">
                      <img
                        src={imagePreviewUrl}
                        alt="Preview"
                        className="max-h-48 max-w-full rounded object-contain"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          setImagePreviewUrl(null);
                          if (fileInputRef.current) fileInputRef.current.value = "";
                        }}
                        className="absolute top-2 right-2 bg-slate-900/80 hover:bg-slate-900 text-white p-1.5 rounded-full shadow transition-colors"
                        title="Remove chosen image"
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="w-full border-2 border-dashed border-slate-300 hover:border-indigo-500 hover:bg-indigo-50/20 rounded-xl p-6 flex flex-col items-center justify-center text-center transition-all group"
                    >
                      <div className="p-3 bg-slate-100 group-hover:bg-indigo-100 text-slate-500 group-hover:text-indigo-600 rounded-full mb-2 transition-colors">
                        <Upload className="h-6 w-6" />
                      </div>
                      <span className="text-xs font-semibold text-slate-800 mb-1">
                        Click to browse image from computer
                      </span>
                      <span className="text-[11px] text-slate-500">
                        PNG, JPG, GIF, WebP • Max 2MB
                      </span>
                    </button>
                  )}
                  <p className="mt-2 text-[10px] text-slate-400 leading-normal">
                    💡 Tip: For 100% email client compatibility (e.g. Gmail &amp; Outlook), hosted HTTPS URLs are recommended over Base64.
                  </p>
                </div>
              )}

              {/* URL Tab */}
              {imageTab === "url" && (
                <div className="space-y-2">
                  <label className="block text-xs font-semibold text-slate-700">
                    Image Web URL
                  </label>
                  <input
                    type="url"
                    value={imageUrl}
                    onChange={(e) => setImageUrl(e.target.value)}
                    placeholder="https://example.com/images/banner.png"
                    className="w-full bg-slate-50 focus:bg-white border border-slate-200 rounded-lg px-3 py-2 text-xs text-slate-900 font-sans focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition-all"
                  />
                  {imageUrl.trim() && (
                    <div className="border border-slate-200 rounded-lg overflow-hidden bg-slate-50 p-2 flex items-center justify-center">
                      <img
                        src={imageUrl.trim()}
                        alt="URL Preview"
                        className="max-h-36 max-w-full rounded object-contain"
                        onError={(e) => {
                          (e.target as HTMLElement).style.display = "none";
                        }}
                      />
                    </div>
                  )}
                </div>
              )}

              {/* Alt Text & Sizing Options */}
              <div className="space-y-3 pt-2 border-t border-slate-100 text-xs">
                <div>
                  <label className="block font-semibold text-slate-700 mb-1">
                    Alt Text (Accessibility)
                  </label>
                  <input
                    type="text"
                    value={imageAlt}
                    onChange={(e) => setImageAlt(e.target.value)}
                    placeholder="e.g. Promotional summer sale banner"
                    className="w-full bg-slate-50 focus:bg-white border border-slate-200 rounded-lg px-3 py-1.5 text-xs text-slate-900 outline-none focus:border-indigo-500 transition-all"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Display Width
                    </label>
                    <select
                      value={imageWidth}
                      onChange={(e) => setImageWidth(e.target.value as "100%" | "75%" | "50%" | "25%")}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 outline-none font-medium"
                    >
                      <option value="100%">100% (Full banner)</option>
                      <option value="75%">75% (Large)</option>
                      <option value="50%">50% (Medium card)</option>
                      <option value="25%">25% (Logo / Icon)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-700 mb-1">
                      Alignment
                    </label>
                    <select
                      value={imageAlign}
                      onChange={(e) => setImageAlign(e.target.value as "left" | "center" | "right")}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 outline-none font-medium"
                    >
                      <option value="center">Centered</option>
                      <option value="left">Left Aligned</option>
                      <option value="right">Right Aligned</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>

            {/* Footer Buttons */}
            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50/70 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsImageModalOpen(false)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:text-slate-800 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!(imageTab === "upload" ? imagePreviewUrl : imageUrl.trim())}
                onClick={handleConfirmInsertImage}
                className="px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-lg transition-all shadow-xs flex items-center gap-1.5"
              >
                <Check className="h-3.5 w-3.5" />
                <span>Insert Image</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
});

RichTextEditor.displayName = "RichTextEditor";
