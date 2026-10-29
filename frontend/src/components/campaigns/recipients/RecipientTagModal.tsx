import React, { useState } from "react";
import { X, Tag, Plus, Loader2 } from "lucide-react";
import type { CampaignRecipient } from "../../../types/campaign";

interface RecipientTagModalProps {
  isOpen: boolean;
  onClose: () => void;
  recipient: CampaignRecipient | null;
  onUpdateTags: (recipientId: number, tags: string[]) => Promise<void>;
}

const TAG_REGEX = /^[a-zA-Z0-9_\-\.]{1,50}$/;

export const RecipientTagModal: React.FC<RecipientTagModalProps> = ({
  isOpen,
  onClose,
  recipient,
  onUpdateTags,
}) => {
  const [tags, setTags] = useState<string[]>([]);
  const [newTagInput, setNewTagInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Sync tags state when recipient changes
  React.useEffect(() => {
    if (recipient) {
      setTags(recipient.tags || []);
      setNewTagInput("");
      setError(null);
    }
  }, [recipient]);

  if (!isOpen || !recipient) return null;

  const handleAddTag = () => {
    const trimmed = newTagInput.trim().toLowerCase();
    if (!trimmed) return;

    if (!TAG_REGEX.test(trimmed)) {
      setError(
        "Tag must be 1-50 characters (letters, numbers, hyphens, underscores, dots only)."
      );
      return;
    }

    if (tags.includes(trimmed)) {
      setError(`Tag "${trimmed}" is already added.`);
      return;
    }

    setTags([...tags, trimmed]);
    setNewTagInput("");
    setError(null);
  };

  const handleRemoveTag = (tagToRemove: string) => {
    setTags(tags.filter((t) => t !== tagToRemove));
  };

  const handleSave = async () => {
    try {
      setIsSubmitting(true);
      setError(null);
      await onUpdateTags(recipient.id, tags);
      onClose();
    } catch (err: any) {
      setError(err?.response?.data?.detail || "Failed to update tags.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 overflow-y-auto">
      <div className="flex min-h-full items-center justify-center p-4 text-center">
        {/* Backdrop */}
        <div
          className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs transition-opacity"
          onClick={onClose}
        />

        {/* Modal Dialog */}
        <div className="relative transform overflow-hidden rounded-xl bg-white text-left shadow-xl transition-all sm:my-8 sm:w-full sm:max-w-md p-6">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <Tag className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Manage Recipient Tags
                </h3>
                <p className="text-xs text-slate-500 truncate max-w-[260px]">
                  {recipient.email}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={onClose}
              className="text-slate-400 hover:text-slate-600 p-1 rounded-lg hover:bg-slate-50 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="py-4 space-y-4">
            {/* Tag input */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Add Tag
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g. vip, lead, enterprise"
                  value={newTagInput}
                  onChange={(e) => {
                    setNewTagInput(e.target.value);
                    if (error) setError(null);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAddTag();
                    }
                  }}
                  className="flex-1 px-3 py-1.5 text-xs border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500"
                />
                <button
                  type="button"
                  onClick={handleAddTag}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition-colors cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add</span>
                </button>
              </div>
            </div>

            {error && (
              <p className="text-xs text-rose-600 bg-rose-50 p-2 rounded-lg border border-rose-100">
                {error}
              </p>
            )}

            {/* Current Tags Chips */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1.5">
                Current Tags ({tags.length})
              </label>
              <div className="flex flex-wrap gap-1.5 p-3 min-h-[60px] max-h-[140px] overflow-y-auto border border-slate-200 rounded-lg bg-slate-50/50">
                {tags.length > 0 ? (
                  tags.map((t) => (
                    <span
                      key={t}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200"
                    >
                      <span>#{t}</span>
                      <button
                        type="button"
                        onClick={() => handleRemoveTag(t)}
                        className="hover:text-indigo-900 cursor-pointer p-0.5 ml-0.5"
                        title={`Remove tag ${t}`}
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </span>
                  ))
                ) : (
                  <p className="text-xs text-slate-400 italic self-center mx-auto">
                    No tags assigned to this recipient.
                  </p>
                )}
              </div>
            </div>
          </div>

          {/* Modal Footer */}
          <div className="flex justify-end gap-2 pt-3 border-t border-slate-100">
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              className="px-3.5 py-1.5 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isSubmitting}
              className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-2xs transition-colors cursor-pointer disabled:opacity-50"
            >
              {isSubmitting && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              <span>Save Changes</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

