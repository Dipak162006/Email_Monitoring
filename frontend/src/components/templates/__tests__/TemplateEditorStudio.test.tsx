import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { STARTER_TEMPLATES } from "../starterTemplatesData";
import { EMAIL_BLOCKS } from "../emailBlocksData";
import { StarterTemplatesModal } from "../StarterTemplatesModal";
import { TemplateBlocksPalette } from "../TemplateBlocksPalette";
import { TemplatePreviewModal, resolvePreviewVariables } from "../TemplatePreviewModal";

describe("Template Studio & Modular Blocks System", () => {
  describe("1. Starter Templates Data", () => {
    it("provides 5 pre-designed industry-standard starter templates", () => {
      expect(STARTER_TEMPLATES).toHaveLength(5);
      const ids = STARTER_TEMPLATES.map((t) => t.id);
      expect(ids).toContain("welcome_onboarding");
      expect(ids).toContain("product_announcement");
      expect(ids).toContain("weekly_newsletter");
      expect(ids).toContain("promotional_offer");
      expect(ids).toContain("transactional_receipt");
    });

    it("ensures each template has a subject, non-empty HTML, and valid category", () => {
      STARTER_TEMPLATES.forEach((tpl) => {
        expect(tpl.name).toBeTruthy();
        expect(tpl.subject).toBeTruthy();
        expect(tpl.bodyHtml).toContain("max-width: 600px");
        expect(tpl.category).toMatch(/^(Onboarding|Marketing|Newsletter|Promotional|Transactional)$/);
      });
    });
  });

  describe("2. Modular Email Blocks Data", () => {
    it("provides 8 modular drag-and-drop email blocks", () => {
      expect(EMAIL_BLOCKS.length).toBeGreaterThanOrEqual(8);
      const titles = EMAIL_BLOCKS.map((b) => b.title);
      expect(titles).toContain("CTA Button");
      expect(titles).toContain("Hero Header");
      expect(titles).toContain("Image Banner");
      expect(titles).toContain("2-Column Cards");
      expect(titles).toContain("Callout / Notice Box");
      expect(titles).toContain("Divider Line");
      expect(titles).toContain("Social Links Bar");
      expect(titles).toContain("Unsubscribe Footer");
    });

    it("each block produces inline email-friendly HTML", () => {
      EMAIL_BLOCKS.forEach((block) => {
        expect(block.html).toBeTruthy();
        expect(block.html).toContain("style=");
      });
    });
  });

  describe("3. StarterTemplatesModal", () => {
    it("renders starter templates modal and filters by category", () => {
      const handleSelect = vi.fn();
      const handleClose = vi.fn();

      render(
        <StarterTemplatesModal
          isOpen={true}
          onClose={handleClose}
          onSelectTemplate={handleSelect}
        />
      );

      expect(screen.getByText("Industry Starter Templates")).toBeTruthy();
      expect(screen.getByText("Customer Welcome & Onboarding")).toBeTruthy();

      // Filter to Transactional
      const transactionalFilter = screen.getByRole("button", { name: "Transactional" });
      fireEvent.click(transactionalFilter);

      expect(screen.getByText("Order Confirmation & Receipt")).toBeTruthy();
      expect(screen.queryByText("Customer Welcome & Onboarding")).toBeNull();

      // Click Apply Template
      const useButtons = screen.getAllByRole("button", { name: /Use Template/i });
      fireEvent.click(useButtons[0]);
      expect(handleSelect).toHaveBeenCalled();
    });
  });

  describe("4. TemplateBlocksPalette", () => {
    it("allows switching between Blocks, Variables, and Presets tabs", () => {
      const onInsertHtml = vi.fn();
      const onInsertVariable = vi.fn();
      const onApplyTemplate = vi.fn();
      const onOpenStarterModal = vi.fn();

      render(
        <TemplateBlocksPalette
          onInsertHtml={onInsertHtml}
          onInsertVariable={onInsertVariable}
          onApplyTemplate={onApplyTemplate}
          onOpenStarterModal={onOpenStarterModal}
        />
      );

      // Default Blocks tab
      expect(screen.getByText("CTA Button")).toBeTruthy();
      const insertButton = screen.getByTitle("Insert CTA Button");
      fireEvent.click(insertButton);
      expect(onInsertHtml).toHaveBeenCalled();

      // Switch to Variables tab
      fireEvent.click(screen.getByRole("button", { name: /Variables/i }));
      expect(screen.getByText("{{customer_name}}")).toBeTruthy();
      fireEvent.click(screen.getByText("{{customer_name}}"));
      expect(onInsertVariable).toHaveBeenCalledWith("{{customer_name}}");

      // Switch to Presets tab
      fireEvent.click(screen.getByRole("button", { name: /Presets/i }));
      expect(screen.getByText("Customer Welcome & Onboarding")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: /View all/i }));
      expect(onOpenStarterModal).toHaveBeenCalled();
    });
  });

  describe("5. TemplatePreviewModal", () => {
    it("resolves dynamic variables accurately", () => {
      const input = "Hello {{customer_name}}, welcome to {{company_name}}!";
      const resolved = resolvePreviewVariables(input);
      expect(resolved).toBe("Hello Alex Vance, welcome to Acme Global Corp!");
    });

    it("renders preview with Desktop (600px) and Mobile (375px) switcher", () => {
      const handleClose = vi.fn();
      render(
        <TemplatePreviewModal
          isOpen={true}
          onClose={handleClose}
          subject="Special Promo for {{customer_name}}"
          bodyHtml="<p>Test body message</p>"
        />
      );

      expect(screen.getByText("Email Live Preview")).toBeTruthy();
      expect(screen.getByText("Special Promo for Alex Vance")).toBeTruthy();

      // Switch to mobile mode
      const mobileBtn = screen.getByRole("button", { name: /Mobile \(375px\)/i });
      fireEvent.click(mobileBtn);

      expect(screen.getByText("10:42 AM")).toBeTruthy();
    });
  });
});
