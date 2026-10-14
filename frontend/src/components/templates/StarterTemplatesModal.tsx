import React, { useState } from "react";
import { X, Sparkles, Megaphone, Newspaper, Tag, Receipt, ArrowRight, Check, Eye } from "lucide-react";
import { STARTER_TEMPLATES, type StarterTemplate } from "./starterTemplatesData";

export interface StarterTemplatesModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectTemplate: (template: StarterTemplate) => void;
}

export const StarterTemplatesModal: React.FC<StarterTemplatesModalProps> = ({
  isOpen,
  onClose,
  onSelectTemplate,
}) => {
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [previewTemplate, setPreviewTemplate] = useState<StarterTemplate | null>(null);

  if (!isOpen) return null;

  const categories = ["ALL", "Onboarding", "Marketing", "Newsletter", "Promotional", "Transactional"];

  const filteredTemplates = selectedCategory === "ALL"
    ? STARTER_TEMPLATES
    : STARTER_TEMPLATES.filter((t) => t.category === selectedCategory);

  const getTemplateIcon = (iconName: string) => {
    switch (iconName) {
      case "Sparkles": return <Sparkles className="h-5 w-5 text-indigo-600" />;
      case "Megaphone": return <Megaphone className="h-5 w-5 text-blue-600" />;
      case "Newspaper": return <Newspaper className="h-5 w-5 text-amber-600" />;
      case "Tag": return <Tag className="h-5 w-5 text-pink-600" />;
      case "Receipt": return <Receipt className="h-5 w-5 text-emerald-600" />;
      default: return <Sparkles className="h-5 w-5 text-indigo-600" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-hidden flex flex-col animate-in fade-in zoom-in-95 duration-150">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50/70">
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-indigo-50 text-indigo-700 rounded-lg">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-slate-900">Industry Starter Templates</h3>
              <p className="text-xs text-slate-500">
                Choose a pre-designed, bulletproof responsive email layout to kickstart your template.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 rounded-lg p-1.5 transition-colors"
            title="Close"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Category Filter Pills */}
        <div className="px-6 py-2.5 bg-white border-b border-slate-100 flex items-center gap-1.5 overflow-x-auto text-xs">
          {categories.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setSelectedCategory(cat)}
              className={`px-3 py-1 rounded-full font-medium transition-colors shrink-0 ${
                selectedCategory === cat
                  ? "bg-indigo-600 text-white shadow-2xs"
                  : "bg-slate-100 text-slate-600 hover:bg-slate-200"
              }`}
            >
              {cat === "ALL" ? "All Templates" : cat}
            </button>
          ))}
        </div>

        {/* Templates Grid Content */}
        <div className="p-6 overflow-y-auto flex-1 bg-slate-50/50">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {filteredTemplates.map((template) => (
              <div
                key={template.id}
                className="bg-white border border-slate-200 hover:border-indigo-300 rounded-xl p-5 shadow-2xs hover:shadow-md transition-all flex flex-col justify-between group"
              >
                <div>
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-center gap-2.5">
                      <div className="p-2.5 bg-slate-50 rounded-lg border border-slate-100 group-hover:bg-indigo-50 group-hover:border-indigo-100 transition-colors">
                        {getTemplateIcon(template.iconName)}
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-indigo-600 uppercase tracking-wider block">
                          {template.category}
                        </span>
                        <h4 className="font-bold text-sm text-slate-900 group-hover:text-indigo-600 transition-colors">
                          {template.name}
                        </h4>
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-slate-600 line-clamp-2 mb-3 leading-relaxed">
                    {template.description}
                  </p>

                  <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-100 mb-4">
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider block mb-0.5">
                      Sample Subject Line:
                    </span>
                    <p className="text-xs font-mono text-slate-700 truncate">
                      {template.subject}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setPreviewTemplate(template)}
                    className="flex-1 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-semibold transition-colors flex items-center justify-center gap-1.5"
                  >
                    <Eye className="h-3.5 w-3.5 text-slate-400" />
                    <span>Quick Preview</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      onSelectTemplate(template);
                      onClose();
                    }}
                    className="flex-1 px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold transition-all flex items-center justify-center gap-1.5 shadow-2xs"
                  >
                    <span>Use Template</span>
                    <ArrowRight className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Mini Preview Dialog */}
      {previewTemplate && (
        <div className="fixed inset-0 z-60 bg-slate-950/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-2xl w-full max-h-[85vh] overflow-hidden flex flex-col">
            <div className="px-5 py-3.5 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <span className="font-bold text-sm text-slate-900">{previewTemplate.name} Preview</span>
              <button
                type="button"
                onClick={() => setPreviewTemplate(null)}
                className="text-slate-400 hover:text-slate-700 p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>
            <div className="p-6 overflow-y-auto bg-slate-100 flex-1">
              <div
                className="bg-white rounded-xl shadow-xs border border-slate-200 p-4 sm:p-6 text-xs max-w-[660px] mx-auto overflow-x-auto pulsemail-preview-canvas"
                dangerouslySetInnerHTML={{ __html: previewTemplate.bodyHtml }}
              />
            </div>
            <div className="px-5 py-3 border-t border-slate-200 bg-white flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={() => setPreviewTemplate(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs font-semibold"
              >
                Back
              </button>
              <button
                type="button"
                onClick={() => {
                  onSelectTemplate(previewTemplate);
                  setPreviewTemplate(null);
                  onClose();
                }}
                className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5"
              >
                <Check className="h-3.5 w-3.5" />
                <span>Use This Template</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
