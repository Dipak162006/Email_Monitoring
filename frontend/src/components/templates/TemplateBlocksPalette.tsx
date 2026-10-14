import React, { useState } from "react";
import {
  MousePointerClick,
  Heading,
  Image as ImageIcon,
  Columns,
  Info,
  Minus,
  Share2,
  ShieldCheck,
  Plus,
  GripVertical,
  Layers,
  Sparkles,
  Tag,
} from "lucide-react";
import { EMAIL_BLOCKS, type EmailBlockItem } from "./emailBlocksData";
import { STARTER_TEMPLATES, type StarterTemplate } from "./starterTemplatesData";

export interface TemplateBlocksPaletteProps {
  onInsertHtml: (html: string) => void;
  onInsertVariable: (variable: string) => void;
  onApplyTemplate: (template: StarterTemplate) => void;
  onOpenStarterModal: () => void;
}

const DYNAMIC_VARIABLES = [
  { tag: "{{customer_name}}", label: "Customer Name", desc: "Recipient's display or first name" },
  { tag: "{{customer_email}}", label: "Customer Email", desc: "Recipient's email address" },
  { tag: "{{company_name}}", label: "Company Name", desc: "Your workspace / brand name" },
  { tag: "{{sender_name}}", label: "Sender Name", desc: "Display name of dispatch mailbox" },
  { tag: "{{login_url}}", label: "Login URL", desc: "Secure dashboard sign-in link" },
  { tag: "{{unsubscribe_url}}", label: "Unsubscribe URL", desc: "Opt-out link placeholder" },
  { tag: "{{ticket_id}}", label: "Ticket / Order ID", desc: "Reference transaction identifier" },
];

export const TemplateBlocksPalette: React.FC<TemplateBlocksPaletteProps> = ({
  onInsertHtml,
  onInsertVariable,
  onApplyTemplate,
  onOpenStarterModal,
}) => {
  const [activeTab, setActiveTab] = useState<"blocks" | "tags" | "templates">("blocks");

  const getBlockIcon = (iconName: string) => {
    switch (iconName) {
      case "MousePointerClick": return <MousePointerClick className="h-4 w-4 text-indigo-600" />;
      case "Heading": return <Heading className="h-4 w-4 text-blue-600" />;
      case "Image": return <ImageIcon className="h-4 w-4 text-emerald-600" />;
      case "Columns": return <Columns className="h-4 w-4 text-amber-600" />;
      case "Info": return <Info className="h-4 w-4 text-sky-600" />;
      case "Minus": return <Minus className="h-4 w-4 text-slate-500" />;
      case "Share2": return <Share2 className="h-4 w-4 text-purple-600" />;
      case "ShieldCheck": return <ShieldCheck className="h-4 w-4 text-teal-600" />;
      default: return <Layers className="h-4 w-4 text-indigo-600" />;
    }
  };

  const handleDragStart = (e: React.DragEvent, block: EmailBlockItem) => {
    e.dataTransfer.setData("application/x-email-block-html", block.html);
    e.dataTransfer.setData("text/html", block.html);
    e.dataTransfer.effectAllowed = "copy";
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-xs flex flex-col h-full overflow-hidden">
      {/* Palette Navigation Tabs */}
      <div className="flex border-b border-slate-200 bg-slate-50/70 p-1 gap-1 text-xs font-semibold">
        <button
          type="button"
          onClick={() => setActiveTab("blocks")}
          className={`flex-1 py-1.5 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
            activeTab === "blocks"
              ? "bg-white text-indigo-600 shadow-2xs font-bold"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Layers className="h-3.5 w-3.5" />
          <span>Blocks</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("tags")}
          className={`flex-1 py-1.5 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
            activeTab === "tags"
              ? "bg-white text-indigo-600 shadow-2xs font-bold"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Tag className="h-3.5 w-3.5" />
          <span>Variables</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("templates")}
          className={`flex-1 py-1.5 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-all ${
            activeTab === "templates"
              ? "bg-white text-indigo-600 shadow-2xs font-bold"
              : "text-slate-600 hover:text-slate-900"
          }`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          <span>Presets</span>
        </button>
      </div>

      {/* Tab Panels */}
      <div className="p-3.5 overflow-y-auto flex-1 space-y-2.5 max-h-[620px]">
        {/* Tab 1: Layout Blocks */}
        {activeTab === "blocks" && (
          <div className="space-y-2">
            <div className="px-1 pb-1 flex items-center justify-between text-[11px] text-slate-400 font-medium">
              <span>Drag block into canvas or click &apos;+&apos;</span>
              <span className="font-mono">{EMAIL_BLOCKS.length} blocks</span>
            </div>

            {EMAIL_BLOCKS.map((block) => (
              <div
                key={block.id}
                draggable
                onDragStart={(e) => handleDragStart(e, block)}
                className="group border border-slate-200/90 hover:border-indigo-300 bg-white hover:bg-indigo-50/30 p-2.5 rounded-lg transition-all cursor-grab active:cursor-grabbing shadow-2xs flex items-center justify-between gap-2"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <div className="text-slate-300 group-hover:text-indigo-400 shrink-0">
                    <GripVertical className="h-3.5 w-3.5" />
                  </div>
                  <div className="p-1.5 bg-slate-50 border border-slate-100 rounded-md group-hover:bg-white group-hover:border-indigo-100 transition-colors shrink-0">
                    {getBlockIcon(block.iconName)}
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-1.5">
                      <h4 className="text-xs font-bold text-slate-800 group-hover:text-indigo-900 truncate">
                        {block.title}
                      </h4>
                      {block.badge && (
                        <span className="text-[9px] font-semibold px-1.5 py-0.2 rounded bg-indigo-50 text-indigo-700 border border-indigo-100 shrink-0">
                          {block.badge}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-slate-500 truncate leading-snug">
                      {block.description}
                    </p>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onInsertHtml(block.html)}
                  title={`Insert ${block.title}`}
                  className="p-1.5 rounded-md border border-slate-200 hover:border-indigo-400 bg-slate-50 hover:bg-indigo-600 text-slate-600 hover:text-white transition-colors shrink-0 cursor-pointer"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Tab 2: Merge Tags */}
        {activeTab === "tags" && (
          <div className="space-y-2">
            <div className="px-1 pb-1 text-[11px] text-slate-400 font-medium">
              Click to insert dynamic variable tag into template:
            </div>

            {DYNAMIC_VARIABLES.map((v) => (
              <div
                key={v.tag}
                onClick={() => onInsertVariable(v.tag)}
                className="group border border-slate-200/90 hover:border-indigo-300 bg-white hover:bg-indigo-50/40 p-2.5 rounded-lg transition-all cursor-pointer shadow-2xs flex items-center justify-between gap-2"
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 mb-0.5">
                    <code className="text-xs font-mono font-bold text-indigo-700 bg-indigo-50 px-1 rounded">
                      {v.tag}
                    </code>
                  </div>
                  <p className="text-[11px] text-slate-500 truncate leading-snug">
                    {v.desc}
                  </p>
                </div>

                <span className="text-xs font-semibold text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                  + Add
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Tab 3: Starter Templates */}
        {activeTab === "templates" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] text-slate-400 font-medium">Pre-designed responsive layouts</span>
              <button
                type="button"
                onClick={onOpenStarterModal}
                className="text-[11px] font-semibold text-indigo-600 hover:text-indigo-800"
              >
                View all &rarr;
              </button>
            </div>

            {STARTER_TEMPLATES.map((tmpl) => (
              <div
                key={tmpl.id}
                className="border border-slate-200 hover:border-indigo-300 bg-white p-3 rounded-xl shadow-2xs transition-all space-y-2"
              >
                <div>
                  <span className="text-[9px] font-bold text-indigo-600 uppercase tracking-wider block">
                    {tmpl.category}
                  </span>
                  <h4 className="text-xs font-bold text-slate-900 leading-snug">
                    {tmpl.name}
                  </h4>
                  <p className="text-[11px] text-slate-500 line-clamp-2 mt-0.5">
                    {tmpl.description}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={() => onApplyTemplate(tmpl)}
                  className="w-full py-1.5 px-2 bg-slate-50 hover:bg-indigo-600 hover:text-white border border-slate-200 hover:border-indigo-600 rounded-lg text-xs font-semibold text-slate-700 transition-colors flex items-center justify-center gap-1.5"
                >
                  <Sparkles className="h-3 w-3" />
                  <span>Apply Layout</span>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
